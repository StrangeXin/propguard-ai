"""Attribution tracking for shared-account orders.

Records which logged-in user placed each order on the shared public account.
Frontend joins `user_label` into history/positions/orders responses so
anonymous viewers can see activity without exposing emails or user_ids.
"""

import logging

from app.services.database import get_db

logger = logging.getLogger(__name__)


def freeze_user_label(user: dict) -> str:
    """Return a display label frozen at write time.

    Prefers `users.name`; falls back to a masked email like `m***n@host.com`
    when name is absent. Truncates to 32 chars.
    """
    name = (user.get("name") or "").strip()
    if name:
        return name[:32]
    email = user["email"]
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked = local[0] + "*"
    else:
        masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked}@{domain}"


def record_attribution(
    *,
    broker_order_id: str,
    broker_position_id: str | None,
    account_id: str,
    user_id: str,
    user_label: str,
    symbol: str | None,
    side: str | None,
    volume: float | None,
) -> bool:
    """Insert a row. Returns True on success, False otherwise. Never raises —
    the order has already landed at the broker, so we must not fail the request.
    """
    db = get_db()
    if not db:
        logger.warning("attribution: DB unavailable, skipping write for %s", broker_order_id)
        return False
    try:
        result = db.table("order_attributions").insert({
            "broker_order_id": broker_order_id,
            "broker_position_id": broker_position_id,
            "account_id": account_id,
            "user_id": user_id,
            "user_label": user_label,
            "symbol": symbol,
            "side": side,
            "volume": volume,
        }).execute()
        return bool(result.data)
    except Exception as e:
        logger.error("record_attribution failed for %s: %s", broker_order_id, e)
        return False


def fetch_labels_by_orders(order_ids: list[str]) -> dict[str, str]:
    """Return {broker_order_id: user_label} for the given ids. Missing ids
    are omitted from the result. Fails open — returns {} on DB error.
    """
    if not order_ids:
        return {}
    db = get_db()
    if not db:
        return {}
    try:
        result = db.table("order_attributions").select(
            "broker_order_id,user_label"
        ).in_("broker_order_id", order_ids).execute()
        return {row["broker_order_id"]: row["user_label"] for row in (result.data or [])}
    except Exception as e:
        logger.error("fetch_labels_by_orders: %s", e)
        return {}


def fetch_labels_by_positions(position_ids: list[str]) -> dict[str, str]:
    """Return {broker_position_id: user_label}. Same fail-open behavior."""
    if not position_ids:
        return {}
    db = get_db()
    if not db:
        return {}
    try:
        result = db.table("order_attributions").select(
            "broker_position_id,user_label"
        ).in_("broker_position_id", position_ids).execute()
        return {
            row["broker_position_id"]: row["user_label"]
            for row in (result.data or [])
            if row.get("broker_position_id")
        }
    except Exception as e:
        logger.error("fetch_labels_by_positions: %s", e)
        return {}


def backfill_position_id(broker_order_id: str, broker_position_id: str) -> None:
    """Set broker_position_id on an existing attribution row. Fire-and-forget.
    Used lazily from /api/trading/history when a pending order's position id
    wasn't known at placement time.
    """
    db = get_db()
    if not db:
        return
    try:
        db.table("order_attributions").update(
            {"broker_position_id": broker_position_id}
        ).eq("broker_order_id", broker_order_id).execute()
    except Exception as e:
        logger.warning("backfill_position_id(%s → %s): %s", broker_order_id, broker_position_id, e)
