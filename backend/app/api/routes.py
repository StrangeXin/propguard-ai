"""
REST API routes for PropGuard.
"""

from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Header, HTTPException
from pydantic import BaseModel

from app.services.auth import register_user, login_user, verify_token, update_user, link_telegram, get_user_by_id
from app.services.payments import create_checkout_session, handle_stripe_webhook

from app.rules.engine import evaluate_compliance, list_available_firms, load_firm_rules
from app.services.broker import BrokerAPIClient
from app.services.alerts import process_compliance_alerts
from app.services.telegram_bot import (
    handle_telegram_message,
    get_recent_signals,
    get_top_signals,
    format_signal_response,
)
from app.services.ai_scorer import register_source, get_source_stats
from app.models.signal import SignalSource
from app.services.briefing import generate_ai_briefing, generate_template_briefing
from app.services.tradingview_webhook import handle_tradingview_webhook
from app.services.kline_data import get_kline_data
from app.services.alert_history import get_alert_history
from app.services.tier import (
    get_user_tier, set_user_tier, get_tier_limits, check_feature_access,
    check_account_limit, check_signal_source_limit, Tier,
)
from app.services.position_calculator import calculate_position
from app.websocket.manager import ws_manager

router = APIRouter()
broker = BrokerAPIClient()


@router.get("/api/firms")
async def get_firms():
    """List all available prop firm rule sets."""
    return {"firms": list_available_firms()}


@router.get("/api/firms/{firm_name}/rules")
async def get_firm_rules(firm_name: str):
    """Get detailed rules for a specific prop firm."""
    rules = load_firm_rules(firm_name)
    return rules


@router.get("/api/accounts/{account_id}/compliance")
async def get_compliance(account_id: str, firm_name: str, account_size: int):
    """
    Get current compliance status for an account.
    This is the core endpoint — fetches account state from broker API,
    runs it through the rule engine, and returns the compliance report.
    """
    try:
        account_state = await broker.get_account_state(account_id, firm_name, account_size)
        if account_state is None:
            return {
                "status": "connecting",
                "message": "Connecting to broker... Please wait.",
                "broker_status": {
                    "metaapi": broker.is_metaapi_ready,
                    "okx": broker.is_okx_ready,
                },
            }

        report = evaluate_compliance(account_state)

        import json as _json
        return _json.loads(_json.dumps({
            "account": account_state.model_dump(),
            "compliance": report.model_dump(),
        }, default=str))
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/api/accounts/{account_id}/alerts/test")
async def test_alert(account_id: str, firm_name: str, account_size: int, chat_id: str = ""):
    """Send a test compliance alert to Telegram."""
    account_state = await broker.get_account_state(account_id, firm_name, account_size)
    if account_state is None:
        return {"status": "connecting", "message": "Broker not connected yet."}
    report = evaluate_compliance(account_state)
    messages = await process_compliance_alerts(report, telegram_chat_id=chat_id or None)

    return {"alerts_triggered": len(messages), "messages": messages}


@router.websocket("/ws/compliance/{account_id}")
async def websocket_compliance(websocket: WebSocket, account_id: str, firm_name: str = "ftmo", account_size: int = 100000):
    """
    WebSocket endpoint for real-time compliance monitoring.
    Client connects and receives compliance updates every 2 seconds.
    """
    await ws_manager.connect(websocket, account_id)

    try:
        while True:
            account_state = await broker.get_account_state(account_id, firm_name, account_size)

            import json
            if account_state is None:
                # Broker not connected yet — send status
                await websocket.send_text(json.dumps({
                    "type": "broker_connecting",
                    "message": "Connecting to broker...",
                    "metaapi_ready": broker.is_metaapi_ready,
                    "okx_ready": broker.is_okx_ready,
                }))
            else:
                report = evaluate_compliance(account_state)
                payload = json.dumps({
                    "type": "compliance_update",
                    "account": account_state.model_dump(),
                    "compliance": report.model_dump(),
                }, default=str)
                await websocket.send_text(payload)
                await process_compliance_alerts(report)

            # Wait before next update
            # In production: event-driven from broker WebSocket, not polling
            import asyncio
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, account_id)
    except Exception as e:
        ws_manager.disconnect(websocket, account_id)
        raise


## ── Signal Routes ──────────────────────────────────────────────


class SignalInput(BaseModel):
    text: str
    source_name: str = "Manual"
    chat_id: str = ""
    forward_from: str | None = None


@router.post("/api/signals/parse")
async def parse_and_score_signal(body: SignalInput):
    """
    Parse a raw text message into a structured signal and score it.
    This is the main endpoint for Telegram bot webhook and manual testing.
    """
    scored = await handle_telegram_message(
        text=body.text,
        chat_id=body.chat_id,
        forward_from=body.forward_from,
    )
    if scored is None:
        return {"parsed": False, "message": "Could not parse a trading signal from this text."}

    return {
        "parsed": True,
        "signal": scored.signal.model_dump(),
        "score": scored.score.model_dump() if scored.score else None,
        "formatted": format_signal_response(scored),
    }


@router.get("/api/signals/recent")
async def recent_signals(limit: int = 20):
    """Get recent scored signals."""
    signals = get_recent_signals(limit)
    return {
        "signals": [
            {
                "signal": s.signal.model_dump(),
                "score": s.score.model_dump() if s.score else None,
            }
            for s in signals
        ]
    }


@router.get("/api/signals/top")
async def top_signals(limit: int = 5):
    """Get top-scored signals."""
    signals = get_top_signals(limit)
    return {
        "signals": [
            {
                "signal": s.signal.model_dump(),
                "score": s.score.model_dump() if s.score else None,
            }
            for s in signals
        ]
    }


class SourceStatsInput(BaseModel):
    source_id: str
    source_name: str
    source_type: str = "telegram"
    win_rate: float | None = None
    avg_rr: float | None = None
    sample_size: int = 0


@router.post("/api/signals/sources")
async def register_signal_source(body: SourceStatsInput):
    """Register or update a signal source's stats (admin endpoint for beta)."""
    source = SignalSource(**body.model_dump())
    register_source(source)
    return {"registered": True, "source": source.model_dump()}


@router.get("/api/signals/sources/{source_id}")
async def get_signal_source(source_id: str):
    """Get stats for a signal source."""
    source = get_source_stats(source_id)
    if source is None:
        return {"found": False}
    return {"found": True, "source": source.model_dump()}


## ── Briefing ────────────────────────────────────────────────────


@router.get("/api/accounts/{account_id}/briefing")
async def get_briefing(account_id: str, firm_name: str, account_size: int):
    """Generate a pre-market AI briefing for an account."""
    account_state = await broker.get_account_state(account_id, firm_name, account_size)
    if account_state is None:
        return {"status": "connecting", "message": "Broker not connected yet. Please wait."}

    report = evaluate_compliance(account_state)
    top = get_top_signals(5)

    briefing = await generate_ai_briefing(account_state, report, top)

    import json as _json
    return _json.loads(_json.dumps(briefing, default=str))


## ── Position Calculator ─────────────────────────────────────────


class PositionCalcInput(BaseModel):
    equity: float
    entry_price: float
    stop_loss: float
    contract_size: float = 100000.0
    source_win_rate: float | None = None
    source_avg_rr: float | None = None
    source_sample_size: int = 0
    daily_loss_remaining: float | None = None
    max_dd_remaining: float | None = None


@router.post("/api/position/calculate")
async def calc_position(body: PositionCalcInput):
    """Calculate recommended position size based on risk parameters."""
    result = calculate_position(
        equity=body.equity,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        contract_size=body.contract_size,
        source_win_rate=body.source_win_rate,
        source_avg_rr=body.source_avg_rr,
        source_sample_size=body.source_sample_size,
        daily_loss_remaining=body.daily_loss_remaining,
        max_dd_remaining=body.max_dd_remaining,
    )
    return {
        "recommended_size": result.recommended_size,
        "stop_loss_price": result.stop_loss_price,
        "risk_amount": result.risk_amount,
        "risk_pct": result.risk_pct,
        "max_allowed_size": result.max_allowed_size,
        "kelly_size": result.kelly_size,
        "kelly_note": result.kelly_note,
        "warnings": result.warnings,
    }


## ── TradingView Webhook ─────────────────────────────────────────


@router.post("/api/webhook/tradingview")
async def tradingview_webhook(request: Request, source_name: str = "Default"):
    """
    TradingView webhook endpoint.
    Configure in TradingView: POST https://your-domain/api/webhook/tradingview?source_name=MyAlert
    Body can be JSON or plain text.
    """
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        body = await request.json()
    else:
        body = (await request.body()).decode("utf-8")

    scored = await handle_tradingview_webhook(body, source_name)
    if scored is None:
        return {"parsed": False, "message": "Could not parse TradingView alert"}

    return {
        "parsed": True,
        "signal": scored.signal.model_dump(),
        "score": scored.score.model_dump() if scored.score else None,
    }


## ── K-Line Data ─────────────────────────────────────────────────


@router.get("/api/kline/{symbol}")
async def get_kline(symbol: str, period: str = "1h", count: int = 200):
    """Get candlestick / K-line data from public sources (Binance, forex APIs)."""
    bars, source = await get_kline_data(symbol=symbol, period=period, count=min(count, 1000))
    return {"symbol": symbol, "period": period, "source": source, "count": len(bars), "bars": bars}


## ── Tier Management ─────────────────────────────────────────────


@router.get("/api/tier/{user_id}")
async def get_tier(user_id: str):
    """Get user's current tier and limits."""
    tier = get_user_tier(user_id)
    limits = get_tier_limits(tier)
    return {
        "user_id": user_id,
        "tier": tier.value,
        "limits": {
            "max_accounts": limits.max_accounts,
            "max_signal_sources": limits.max_signal_sources,
            "ai_scoring": limits.ai_scoring,
            "ai_briefing": limits.ai_briefing,
            "position_calculator": limits.position_calculator,
            "history_access": limits.history_access,
            "alert_channels": limits.alert_channels,
        },
    }


@router.post("/api/tier/{user_id}")
async def update_tier(user_id: str, tier: str):
    """Update user tier (admin/payment webhook endpoint)."""
    try:
        t = Tier(tier)
    except ValueError:
        return {"error": f"Invalid tier: {tier}. Use free/pro/premium."}
    set_user_tier(user_id, t)
    return {"user_id": user_id, "tier": t.value, "updated": True}


@router.get("/api/tier/{user_id}/check/{feature}")
async def check_feature(user_id: str, feature: str):
    """Check if user can access a specific feature."""
    return check_feature_access(user_id, feature)


## ── Alert History ────────────────────────────────────────────────


@router.get("/api/alerts/history")
async def alerts_history(account_id: str | None = None, limit: int = 50):
    """Get alert history, optionally filtered by account."""
    return {"alerts": get_alert_history(account_id=account_id, limit=limit)}


## ── Account Management ──────────────────────────────────────────

# In-memory account registry (in production: Supabase)
_registered_accounts: list[dict] = []


class AccountRegisterInput(BaseModel):
    account_id: str
    firm_name: str
    account_size: int
    broker_type: str = "mock"  # "metaapi", "okx", "mock"
    label: str = ""


@router.post("/api/accounts/register")
async def register_account(body: AccountRegisterInput):
    """Register a trading account for monitoring."""
    acc = body.model_dump()
    acc["created_at"] = datetime.now().isoformat()
    # Avoid duplicates
    _registered_accounts[:] = [a for a in _registered_accounts if a["account_id"] != acc["account_id"]]
    _registered_accounts.append(acc)
    return {"registered": True, "account": acc}


@router.get("/api/accounts")
async def list_accounts():
    """List all registered accounts."""
    return {"accounts": _registered_accounts}


@router.delete("/api/accounts/{account_id}")
async def remove_account(account_id: str):
    """Remove a registered account."""
    before = len(_registered_accounts)
    _registered_accounts[:] = [a for a in _registered_accounts if a["account_id"] != account_id]
    return {"removed": before > len(_registered_accounts)}


## ── Auth ────────────────────────────────────────────────────────


class RegisterInput(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginInput(BaseModel):
    email: str
    password: str


@router.post("/api/auth/register")
async def auth_register(body: RegisterInput):
    try:
        user = register_user(body.email, body.password, body.name)
        # Auto-login after register
        result = login_user(body.email, body.password)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/auth/login")
async def auth_login(body: LoginInput):
    try:
        return login_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/api/auth/me")
async def auth_me(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "")
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"user": user}


class LinkTelegramInput(BaseModel):
    chat_id: str


@router.post("/api/auth/link-telegram")
async def auth_link_telegram(body: LinkTelegramInput, authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "")
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    link_telegram(user["id"], body.chat_id)
    return {"linked": True}


## ── Payments ────────────────────────────────────────────────────


@router.post("/api/payments/checkout")
async def payment_checkout(tier: str, authorization: str = Header(default="")):
    """Create a Stripe Checkout session for upgrading."""
    token = authorization.replace("Bearer ", "")
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    if tier not in ("pro", "premium"):
        raise HTTPException(status_code=400, detail="Invalid tier. Use pro or premium.")

    result = await create_checkout_session(user["id"], user["email"], tier)
    return result


@router.post("/api/payments/webhook")
async def payment_webhook(request: Request):
    """Stripe webhook endpoint — handles payment events."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = await handle_stripe_webhook(payload, sig)
    return result


## ── Health ──────────────────────────────────────────────────────


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "PropGuard AI",
        "version": "0.1.0",
        "ws_connections": ws_manager.connection_count(),
        "active_accounts": ws_manager.active_accounts,
    }
