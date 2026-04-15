"""
Stripe payment integration — handles checkout sessions and webhook events.
Upgrades user tier on successful payment.
"""

import logging
from app.config import get_settings
from app.services.database import db_update_user, db_get_user_by_email

logger = logging.getLogger(__name__)

TIER_PRICES = {
    "pro": 2900,  # $29.00 in cents
    "premium": 4900,  # $49.00 in cents
}


async def create_checkout_session(user_id: str, email: str, tier: str) -> dict | None:
    """Create a Stripe Checkout session for upgrading to a paid tier."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        return {"url": None, "message": "Stripe not configured. Contact admin to upgrade."}

    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key

        price_id = settings.stripe_price_pro if tier == "pro" else settings.stripe_price_premium
        if not price_id:
            return {"url": None, "message": f"Stripe price not configured for {tier} tier."}

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url="http://localhost:3001/?upgraded=true",
            cancel_url="http://localhost:3001/?upgraded=false",
            metadata={"user_id": user_id, "tier": tier},
        )

        return {"url": session.url, "session_id": session.id}

    except Exception as e:
        logger.error(f"Stripe checkout failed: {e}")
        return {"url": None, "message": str(e)}


async def handle_stripe_webhook(payload: bytes, sig_header: str) -> dict:
    """Handle Stripe webhook events (payment success, subscription changes)."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        return {"handled": False, "reason": "Stripe not configured"}

    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key

        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = session.get("metadata", {}).get("user_id")
            tier = session.get("metadata", {}).get("tier")

            if user_id and tier:
                db_update_user(user_id, {"tier": tier})
                logger.info(f"User {user_id} upgraded to {tier}")
                return {"handled": True, "user_id": user_id, "tier": tier}

        elif event["type"] == "customer.subscription.deleted":
            # Downgrade to free on cancellation
            session = event["data"]["object"]
            email = session.get("customer_email")
            if email:
                user = db_get_user_by_email(email)
                if user:
                    db_update_user(user["id"], {"tier": "free"})
                    logger.info(f"User {user['id']} downgraded to free")
                    return {"handled": True, "action": "downgrade"}

        return {"handled": True, "event_type": event["type"]}

    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return {"handled": False, "error": str(e)}
