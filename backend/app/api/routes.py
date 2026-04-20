"""
REST API routes for PropGuard.
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends

logger = logging.getLogger(__name__)
from pydantic import BaseModel

from app.services.auth import register_user, login_user, update_user, link_telegram, get_user_by_id
from app.services.owner_resolver import get_owner, require_user
from app.services.quota import require_quota
from app.models.owner import Owner
from app.services.payments import create_checkout_session, handle_stripe_webhook
from app.services.live_trading import (
    mt5_get_symbol_spec,
    mt5_get_symbol_price,
)
from app.services.broker_factory import get_broker
from app.services.broker_types import (
    OrderResult, PositionDTO, OrderDTO, ClosedTrade,
)
from app.services.ai_trader import (
    ai_analyze_and_trade, start_trading_session, stop_trading_session,
    get_session_status, list_sessions,
)

from app.rules.engine import evaluate_compliance, list_available_firms, load_firm_rules
from app.services.trading_stats import calculate_challenge_progress
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
from app.config import get_settings
from app.services.attribution import record_attribution, freeze_user_label

router = APIRouter()
broker = BrokerAPIClient()


# ── Broker DTO → frontend-shape dict helpers ─────────────────────────
# The frontend TradingPanel reads these exact field names (side, volume,
# entry_price, current_price, profit, stop_loss, take_profit, price).
# Preserve them so migrating endpoints from mt5_* → BrokerBase is a no-op
# for the UI.


def _position_to_dict(p: PositionDTO, user_label: str | None = None) -> dict:
    return {
        "id": p.id,
        "symbol": p.symbol,
        "side": p.side,
        "volume": p.size,
        "entry_price": p.entry_price,
        "current_price": p.current_price,
        "profit": p.unrealized_pnl,
        "stop_loss": p.stop_loss,
        "take_profit": p.take_profit,
        "user_label": user_label,
    }


def _order_to_dict(o: OrderDTO, user_label: str | None = None) -> dict:
    return {
        "id": o.id,
        "symbol": o.symbol,
        "type": f"ORDER_TYPE_{o.side.upper()}_{o.order_type.upper()}",
        "side": o.side,
        "volume": o.size,
        "price": o.price,
        "stop_loss": o.stop_loss,
        "take_profit": o.take_profit,
        "user_label": user_label,
    }


def _trade_to_dict(t: ClosedTrade, user_label: str | None = None) -> dict:
    side = "buy" if t.side == "long" else "sell"
    return {
        "id": t.id,
        "symbol": t.symbol,
        "side": side,
        "type": "DEAL_TYPE_BUY" if t.side == "long" else "DEAL_TYPE_SELL",
        "volume": t.size,
        "price": t.exit_price,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "profit": t.pnl,
        "user_label": user_label,
    }


def _result_to_dict(r) -> dict:
    if isinstance(r, dict):
        return {"success": r.get("success"), "order_id": r.get("order_id"), "error": r.get("message") or r.get("error")}
    return {"success": r.success, "order_id": r.order_id, "error": r.message}


def _record_order_attribution(
    owner: Owner, result, symbol: str, side: str, volume: float,
) -> None:
    """Write an attribution row when a logged-in user places on the shared account.

    Skips when: order was rejected, owner is on their own bound account, or DB
    write fails (logged). Never raises — the order is already live at broker.
    """
    if not getattr(result, "success", False):
        return
    order_id = getattr(result, "order_id", None)
    if not order_id:
        return
    if owner.metaapi_account_id is not None:
        return  # user on their own account — no shared-account attribution
    settings = get_settings()
    if not settings.metaapi_account_id:
        return  # local dev without MetaApi — skip
    user = get_user_by_id(owner.id)
    if not user:
        logger.warning("attribution: user %s not found", owner.id)
        return
    record_attribution(
        broker_order_id=str(order_id),
        broker_position_id=None,  # market order — position id backfilled in history reads
        account_id=settings.metaapi_account_id,
        user_id=owner.id,
        user_label=freeze_user_label(user),
        symbol=symbol,
        side=side,
        volume=volume,
    )


def _shared_account_configured() -> bool:
    return bool(get_settings().metaapi_account_id)


def _labels_for_positions(owner: Owner, position_ids: list[str]) -> dict:
    """Return {position_id: user_label} for the shared-account read path.

    Accepts a list of position id strings directly.
    Returns empty dict for bound users — they're on their own MetaApi account
    and attribution does not apply. Frontend hides the By column when the map
    is empty AND all positions lack user_label.
    """
    if owner.metaapi_account_id is not None:
        return {}
    from app.services.attribution import fetch_labels_by_positions
    return fetch_labels_by_positions([pid for pid in position_ids if pid])


def _labels_for_orders(owner: Owner, order_ids: list) -> dict:
    if owner.metaapi_account_id is not None:
        return {}
    from app.services.attribution import fetch_labels_by_orders
    return fetch_labels_by_orders([oid for oid in order_ids if oid])


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
async def get_compliance(account_id: str, firm_name: str, account_size: int, evaluation_type: str | None = None):
    """
    Get current compliance status for an account.
    This is the core endpoint — fetches account state from broker API,
    runs it through the rule engine, and returns the compliance report.
    """
    try:
        account_state = await broker.get_account_state(account_id, firm_name, account_size)

        # If broker not connected, use a placeholder account state so rules still show
        if account_state is None:
            from app.models.account import AccountState
            account_state = AccountState(
                account_id=account_id,
                firm_name=firm_name,
                account_size=account_size,
                initial_balance=float(account_size),
                current_balance=float(account_size),
                current_equity=float(account_size),
                daily_pnl=0,
                total_pnl=0,
                equity_high_watermark=float(account_size),
                broker_connected=False,
            )

        report = evaluate_compliance(account_state, evaluation_type)

        import json as _json
        return _json.loads(_json.dumps({
            "account": account_state.model_dump(),
            "compliance": report.model_dump(),
            "evaluation_type": evaluation_type or "default",
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
async def websocket_compliance(websocket: WebSocket, account_id: str, firm_name: str = "ftmo", account_size: int = 100000, evaluation_type: str | None = None):
    """
    WebSocket endpoint for real-time compliance monitoring.
    Client connects and receives compliance updates every 2 seconds.
    """
    await ws_manager.connect(websocket, account_id)

    import json
    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    try:
        while True:
            try:
                account_state = await broker.get_account_state(account_id, firm_name, account_size)

                if account_state is None:
                    await websocket.send_text(json.dumps({
                        "type": "broker_connecting",
                        "message": "Connecting to broker...",
                        "metaapi_ready": broker.is_metaapi_ready,
                        "okx_ready": broker.is_okx_ready,
                    }))
                else:
                    report = evaluate_compliance(account_state, evaluation_type)
                    payload = json.dumps({
                        "type": "compliance_update",
                        "account": account_state.model_dump(),
                        "compliance": report.model_dump(),
                    }, default=str)
                    await websocket.send_text(payload)
                    await process_compliance_alerts(report)

            except WebSocketDisconnect:
                raise
            except Exception as e:
                # Don't crash WS on data fetch errors — send error status and retry
                logger.warning(f"WS data error: {e}")
                try:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": str(e),
                    }))
                except Exception:
                    break

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, account_id)


## ── Signal Routes ──────────────────────────────────────────────


class SignalInput(BaseModel):
    text: str
    source_name: str = "Manual"
    chat_id: str = ""
    forward_from: str | None = None


@router.post("/api/signals/parse")
async def parse_and_score_signal(
    body: SignalInput,
    owner: Owner = Depends(require_quota("ai_score")),
):
    """
    Parse a raw text message into a structured signal and score it.
    This is the main endpoint for Telegram bot webhook and manual testing.
    """
    scored = await handle_telegram_message(
        text=body.text,
        chat_id=body.chat_id,
        forward_from=body.forward_from,
        owner=owner,
        consume_quota=False,  # already consumed by @require_quota dep
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
async def get_briefing(
    account_id: str, firm_name: str, account_size: int,
    _user: Owner = Depends(require_user),  # briefing requires login
    owner: Owner = Depends(require_quota("briefing")),
):
    """Generate a pre-market AI briefing for an account."""
    account_state = await broker.get_account_state(account_id, firm_name, account_size)
    if account_state is None:
        return {"status": "connecting", "message": "Broker not connected yet. Please wait."}

    report = evaluate_compliance(account_state)
    top = get_top_signals(5)

    briefing = await generate_ai_briefing(
        account_state, report, top, owner=owner, consume_quota=False,
    )

    import json as _json
    return _json.loads(_json.dumps(briefing, default=str))


@router.get("/api/accounts/{account_id}/challenge-progress")
async def get_challenge_progress(account_id: str, firm_name: str, account_size: int):
    """Get challenge progress: profit target, drawdown usage, trading days."""
    account_state = await broker.get_account_state(account_id, firm_name, account_size)
    if account_state is None:
        return {"status": "connecting"}

    try:
        firm_rules = load_firm_rules(firm_name)
    except FileNotFoundError:
        return {"error": f"Unknown firm: {firm_name}"}

    progress = calculate_challenge_progress(account_state, firm_rules)

    import json as _json
    return _json.loads(_json.dumps(progress, default=str))


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
async def auth_register(body: RegisterInput, request: Request):
    try:
        user = register_user(body.email, body.password, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Claim any anon-session data for this new user before logging in, so the
    # dashboard they land on already shows their sandbox history.
    claimed: dict[str, int] = {}
    total_claimed = 0
    from app.services.owner_resolver import ANON_COOKIE
    from app.services.claim import claim_anon_data
    anon_id = request.cookies.get(ANON_COOKIE)
    if anon_id:
        claimed = claim_anon_data(anon_id, user["id"])
        total_claimed = sum(claimed.values())

    login_result = login_user(body.email, body.password)
    return {
        **login_result,
        "claimed": claimed,
        "total_claimed": total_claimed,
    }


@router.post("/api/auth/login")
async def auth_login(body: LoginInput):
    try:
        return login_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/api/auth/me")
async def auth_me(owner: Owner = Depends(require_user)):
    return {"user": get_user_by_id(owner.id)}


class LinkTelegramInput(BaseModel):
    chat_id: str


@router.post("/api/auth/link-telegram")
async def auth_link_telegram(body: LinkTelegramInput, owner: Owner = Depends(require_user)):
    link_telegram(owner.id, body.chat_id)
    return {"linked": True}


class BrokerConnectInput(BaseModel):
    metaapi_account_id: str
    metaapi_user_token: str  # ownership proof; user-level API token


@router.post("/api/user/broker/connect")
async def user_broker_connect(
    body: BrokerConnectInput, owner: Owner = Depends(require_user),
):
    """Validate + persist a user's MetaApi account binding.

    Ownership proof: the user provides their own MetaApi API token. We use
    that token (not the server admin token) to fetch the account. If the
    SDK call succeeds, the user demonstrably controls the token. The
    token is encrypted at rest (AES-GCM) via app.services.crypto.
    """
    acct_id = body.metaapi_account_id.strip()
    user_tok = body.metaapi_user_token.strip()
    if not acct_id or len(acct_id) < 20:
        raise HTTPException(400, "Invalid MetaApi account ID format.")

    from app.services.metaapi_admin import verify_with_user_token
    ok, message = await verify_with_user_token(acct_id, user_tok)
    if not ok:
        raise HTTPException(400, message)

    from app.services.crypto import encrypt
    from app.services.auth import update_user
    updated = update_user(owner.id, {
        "metaapi_account_id": acct_id,
        "metaapi_user_token_encrypted": encrypt(user_tok),
    })
    if not updated:
        raise HTTPException(500, "Failed to save account binding.")

    logger.info("metaapi_bind_verified user=%s account=%s", owner.id[:8], acct_id[:8])
    # Never leak the encrypted token in the response.
    safe_user = {k: v for k, v in updated.items() if k != "metaapi_user_token_encrypted"}
    return {"success": True, "message": message, "user": safe_user}


@router.delete("/api/user/broker")
async def user_broker_disconnect(owner: Owner = Depends(require_user)):
    """Unbind — user reverts to sandbox mode on next request."""
    from app.services.auth import update_user
    updated = update_user(owner.id, {"metaapi_account_id": None})
    return {"success": True, "user": updated}


## ── Paper Trading ───────────────────────────────────────────────


class PlaceOrderInput(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    size: float
    order_type: str = "market"
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


class ModifyPositionInput(BaseModel):
    stop_loss: float | None = None
    take_profit: float | None = None


@router.get("/api/trading/account")
async def trading_account(owner: Owner = Depends(get_owner)):
    """Get trading account info + positions."""
    broker_impl = get_broker(owner)
    info = await broker_impl.account_info()
    positions = await broker_impl.positions()
    initial = 100000.0
    pnl = info.equity - initial
    labels = _labels_for_positions(owner, [p.id for p in positions])
    return {
        "balance": info.balance,
        "equity": info.equity,
        "initial_balance": initial,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / initial * 100, 2) if initial > 0 else 0,
        "open_positions": len(positions),
        "total_trades": 0,
        "winning_trades": 0,
        "win_rate": 0,
        "positions": [_position_to_dict(p, labels.get(p.id)) for p in positions],
        "recent_trades": [],
        "source": "metaapi_mt5" if owner.metaapi_account_id or _shared_account_configured() else "sandbox",
    }


@router.post("/api/trading/order")
async def trading_place_order(body: PlaceOrderInput, owner: Owner = Depends(require_user)):
    """Place a market order via the broker."""
    broker_impl = get_broker(owner)
    result = await broker_impl.place_market_order(
        symbol=body.symbol,
        side=body.side,
        volume=body.size,
        sl=body.stop_loss,
        tp=body.take_profit,
    )
    _record_order_attribution(owner, result, body.symbol, body.side, body.size)
    return _result_to_dict(result)


@router.post("/api/trading/position/{position_id}/modify")
async def trading_modify(position_id: str, body: ModifyPositionInput, owner: Owner = Depends(require_user)):
    """Modify SL/TP on an open position."""
    broker_impl = get_broker(owner)
    result = await broker_impl.modify_position(
        position_id, sl=body.stop_loss, tp=body.take_profit,
    )
    return _result_to_dict(result)


@router.post("/api/trading/position/{position_id}/close")
async def trading_close(position_id: str, owner: Owner = Depends(require_user)):
    """Close a position fully."""
    broker_impl = get_broker(owner)
    return _result_to_dict(await broker_impl.close_position(position_id))


@router.post("/api/trading/position/{position_id}/close-partial")
async def trading_close_partial(position_id: str, volume: float, owner: Owner = Depends(require_user)):
    """Partially close a position."""
    broker_impl = get_broker(owner)
    return _result_to_dict(
        await broker_impl.close_position_partial(position_id, volume)
    )


class PendingOrderInput(BaseModel):
    symbol: str
    side: str
    size: float
    price: float
    order_type: str = "limit"  # "limit" or "stop"
    stop_loss: float | None = None
    take_profit: float | None = None


@router.post("/api/trading/pending-order")
async def trading_pending_order(body: PendingOrderInput, owner: Owner = Depends(require_user)):
    """Place a limit or stop order."""
    broker_impl = get_broker(owner)
    result = await broker_impl.place_pending_order(
        symbol=body.symbol,
        side=body.side,
        volume=body.size,
        order_type=body.order_type,
        price=body.price,
        sl=body.stop_loss,
        tp=body.take_profit,
    )
    _record_order_attribution(owner, result, body.symbol, body.side, body.size)
    return _result_to_dict(result)


@router.get("/api/trading/orders")
async def trading_orders(owner: Owner = Depends(get_owner)):
    """Get all pending orders."""
    broker_impl = get_broker(owner)
    orders = await broker_impl.pending_orders()
    labels = _labels_for_orders(owner, [o.id for o in orders])
    return {"orders": [_order_to_dict(o, labels.get(o.id)) for o in orders]}


@router.post("/api/trading/order/{order_id}/cancel")
async def trading_cancel_order(order_id: str, owner: Owner = Depends(require_user)):
    """Cancel a pending order."""
    broker_impl = get_broker(owner)
    return _result_to_dict(await broker_impl.cancel_order(order_id))


@router.get("/api/trading/history")
async def trading_history(days: int = 30, owner: Owner = Depends(get_owner)):
    """Get closed trade history."""
    broker_impl = get_broker(owner)
    trades_typed = await broker_impl.history(limit=100)
    # Collect order_ids and position_ids separately — attribution rows are
    # keyed by these, NOT by ClosedTrade.id (which is the deal_id).
    order_ids = [t.order_id for t in trades_typed if t.order_id]
    position_ids = [t.position_id for t in trades_typed if t.position_id]
    labels_by_order = _labels_for_orders(owner, order_ids)
    labels_by_position = _labels_for_positions(owner, position_ids)

    def _label_for(t):
        if t.order_id and t.order_id in labels_by_order:
            return labels_by_order[t.order_id]
        if t.position_id and t.position_id in labels_by_position:
            return labels_by_position[t.position_id]
        return None

    trades = [_trade_to_dict(t, _label_for(t)) for t in trades_typed]

    # Lazy backfill: attribution rows with known order_id but missing
    # broker_position_id — set it now if we learned it from this deal.
    if owner.metaapi_account_id is None and order_ids:
        from app.services.attribution import fetch_attributions_by_orders, backfill_position_id
        attr_rows = fetch_attributions_by_orders(order_ids)
        # Build order_id → position_id from the trades we just got.
        order_to_pos = {t.order_id: t.position_id for t in trades_typed if t.order_id and t.position_id}
        for row in attr_rows:
            order_id = row.get("broker_order_id")
            if row.get("broker_position_id"):
                continue  # already backfilled
            pos_id = order_to_pos.get(order_id)
            if pos_id:
                asyncio.create_task(asyncio.to_thread(backfill_position_id, order_id, pos_id))

    total = len(trades)
    winners = sum(1 for t in trades if t.get("profit", 0) > 0)
    total_pnl = sum(t.get("profit", 0) for t in trades)
    return {
        "trades": trades,
        "stats": {
            "total_trades": total,
            "winning_trades": winners,
            "win_rate": round(winners / total * 100, 1) if total > 0 else 0,
            "total_pnl": round(total_pnl, 2),
        },
    }


@router.get("/api/trading/symbol/{symbol}")
async def trading_symbol_info(symbol: str):
    """Get symbol specification and current price."""
    spec = await mt5_get_symbol_spec(symbol)
    price = await mt5_get_symbol_price(symbol)
    return {"spec": spec, "price": price}


@router.get("/api/trading/account-info")
async def trading_account_info(owner: Owner = Depends(get_owner)):
    """Get full account information."""
    broker_impl = get_broker(owner)
    info = await broker_impl.account_info()
    return {
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "freeMargin": info.free_margin,
        "free_margin": info.free_margin,
        "currency": info.currency,
    }


@router.post("/api/sandbox/reset")
async def sandbox_reset(owner: Owner = Depends(require_user)):
    """Account reset is disabled — both shared and bound accounts are real
    MetaApi demos. Kept as 403 rather than 410 so the frontend can render a
    tooltip via its existing error handler. See design doc §Broker routing."""
    raise HTTPException(
        status_code=403,
        detail="Account reset is not supported on real broker accounts",
    )


## ── AI Trading ──────────────────────────────────────────────────


class AITradeRequest(BaseModel):
    strategy: dict
    firm_name: str = "ftmo"
    account_size: int = 100000
    evaluation_type: str | None = None
    dry_run: bool = True


class AISessionRequest(BaseModel):
    strategy: dict
    interval: str = "1h"  # 1m, 5m, 15m, 1h, 4h, 1d
    firm_name: str = "ftmo"
    account_size: int = 100000
    evaluation_type: str | None = None
    dry_run: bool = True


INTERVAL_MAP = {
    "1m": 60, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}


@router.post("/api/ai-trade/analyze")
async def ai_trade_analyze(
    body: AITradeRequest,
    owner: Owner = Depends(require_user),
    _q=Depends(require_quota("ai_trade_tick")),
):
    """Run one AI trading cycle: analyze market + return/execute actions."""
    result = await ai_analyze_and_trade(
        strategy=body.strategy,
        firm_name=body.firm_name,
        account_size=body.account_size,
        evaluation_type=body.evaluation_type,
        dry_run=body.dry_run,
        owner=owner,
        consume_quota=False,  # @require_quota already consumed
    )

    # Save to database
    from app.services.database import db_save_ai_trade_log
    db_save_ai_trade_log(
        user_id=owner.id,
        strategy_name=body.strategy.get("name", ""),
        symbols=",".join(body.strategy.get("symbols", [])),
        analysis=result.get("analysis", ""),
        actions_planned=result.get("actions_planned", 0),
        actions_executed=result.get("actions_executed", 0),
        prompt=result.get("prompt", ""),
        result=result,
        dry_run=body.dry_run,
    )

    import json as _json
    return _json.loads(_json.dumps(result, default=str))


class ExecuteActionsInput(BaseModel):
    actions: list[dict]


@router.post("/api/ai-trade/execute")
async def ai_trade_execute(body: ExecuteActionsInput, owner: Owner = Depends(require_user)):
    """Execute specific actions directly (from a previous dry run)."""
    broker_impl = get_broker(owner)
    executed = []
    for action in body.actions:
        action_type = action.get("type")
        symbol = action.get("symbol", "")
        volume = action.get("volume", 0.01)
        sl = action.get("stop_loss")
        tp = action.get("take_profit")
        position_id = action.get("position_id")

        try:
            if action_type in ("buy", "sell"):
                result = await broker_impl.place_market_order(
                    symbol=symbol, side=action_type, volume=volume, sl=sl, tp=tp,
                )
                executed.append({"action": action, "result": _result_to_dict(result)})
            elif action_type == "close" and position_id:
                result = await broker_impl.close_position(position_id)
                executed.append({"action": action, "result": _result_to_dict(result)})
            elif action_type == "modify" and position_id:
                result = await broker_impl.modify_position(position_id, sl=sl, tp=tp)
                executed.append({"action": action, "result": _result_to_dict(result)})
            else:
                executed.append({"action": action, "status": "skipped"})
        except Exception as e:
            executed.append({"action": action, "status": "error", "error": str(e)})

    import json as _json
    return _json.loads(_json.dumps({
        "actions_executed": len(executed),
        "executions": executed,
    }, default=str))


@router.post("/api/ai-trade/start")
async def ai_trade_start(body: AISessionRequest, owner: Owner = Depends(require_user)):
    """Start an automated AI trading session."""
    interval_seconds = INTERVAL_MAP.get(body.interval, 3600)
    session_id = f"{owner.id[:8]}-{body.strategy.get('name', 'unnamed')}"

    # Check if already running
    existing = get_session_status(session_id)
    if existing and existing.get("status") == "running":
        return {"error": "Session already running", "session_id": session_id}

    # Start in background. Each tick inside will consume ai_trade_tick quota.
    import asyncio
    asyncio.create_task(start_trading_session(
        session_id=session_id,
        strategy=body.strategy,
        interval_seconds=interval_seconds,
        firm_name=body.firm_name,
        account_size=body.account_size,
        evaluation_type=body.evaluation_type,
        dry_run=body.dry_run,
        owner=owner,
    ))

    return {"started": True, "session_id": session_id, "interval": body.interval, "dry_run": body.dry_run}


@router.post("/api/ai-trade/tick")
async def ai_trade_tick(
    body: AITradeRequest,
    owner: Owner = Depends(get_owner),
    _q=Depends(require_quota("ai_trade_tick")),
):
    """Single AI trading cycle — allowed for anon/free users who drive the
    loop from the browser. Identical payload/response to /api/ai-trade/analyze
    except this accepts anonymous owners.
    """
    result = await ai_analyze_and_trade(
        strategy=body.strategy,
        firm_name=body.firm_name,
        account_size=body.account_size,
        evaluation_type=body.evaluation_type,
        dry_run=body.dry_run,
        owner=owner,
        consume_quota=False,  # @require_quota already consumed
    )
    # Log to DB for both user and anon owners (PR 3b T6: anon trades now
    # persist under owner_id without an FK to users).
    from app.services.database import db_save_ai_trade_log
    db_save_ai_trade_log(
        strategy_name=body.strategy.get("name", ""),
        symbols=",".join(body.strategy.get("symbols", [])),
        analysis=result.get("analysis", ""),
        actions_planned=result.get("actions_planned", 0),
        actions_executed=result.get("actions_executed", 0),
        prompt=result.get("prompt", ""),
        result=result,
        dry_run=body.dry_run,
        owner_id=owner.id,
        owner_kind=owner.kind,
    )

    import json as _json
    return _json.loads(_json.dumps(result, default=str))


@router.post("/api/ai-trade/stop/{session_id}")
async def ai_trade_stop(session_id: str, owner: Owner = Depends(require_user)):
    """Stop a running AI trading session."""
    stopped = stop_trading_session(session_id)
    return {"stopped": stopped, "session_id": session_id}


@router.get("/api/ai-trade/sessions")
async def ai_trade_sessions(owner: Owner = Depends(require_user)):
    """List all AI trading sessions."""
    return {"sessions": list_sessions()}


@router.get("/api/ai-trade/session/{session_id}")
async def ai_trade_session_detail(session_id: str, owner: Owner = Depends(require_user)):
    """Get detailed status of an AI trading session."""
    status = get_session_status(session_id)
    if not status:
        return {"error": "Session not found"}

    import json as _json
    return _json.loads(_json.dumps(status, default=str))


## ── Strategies ──────────────────────────────────────────────────


class StrategyInput(BaseModel):
    name: str
    symbols: str
    kline_period: str = "1h"
    rules: str


@router.get("/api/strategies")
async def list_strategies(owner: Owner = Depends(require_user)):
    from app.services.database import db_get_strategies
    return {"strategies": db_get_strategies(owner.id)}


@router.post("/api/strategies")
async def save_strategy(body: StrategyInput, owner: Owner = Depends(require_user)):
    from app.services.database import db_save_strategy
    result = db_save_strategy(owner.id, body.model_dump())
    return {"saved": result is not None, "strategy": result}


@router.put("/api/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, body: StrategyInput, owner: Owner = Depends(require_user)):
    from app.services.database import db_update_strategy
    result = db_update_strategy(strategy_id, body.model_dump())
    return {"updated": result is not None, "strategy": result}


@router.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, owner: Owner = Depends(require_user)):
    from app.services.database import db_delete_strategy
    return {"deleted": db_delete_strategy(strategy_id)}


@router.get("/api/ai-trade/logs")
async def ai_trade_logs(limit: int = 20, owner: Owner = Depends(require_user)):
    """Get AI trading analysis history."""
    from app.services.database import db_get_ai_trade_logs
    logs = db_get_ai_trade_logs(user_id=owner.id, limit=min(limit, 50))
    return {"logs": logs}


## ── Payments ────────────────────────────────────────────────────


@router.post("/api/payments/checkout")
async def payment_checkout(tier: str, owner: Owner = Depends(require_user)):
    """Create a Stripe Checkout session for upgrading."""
    if tier not in ("pro", "premium"):
        raise HTTPException(status_code=400, detail="Invalid tier. Use pro or premium.")

    user = get_user_by_id(owner.id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    result = await create_checkout_session(owner.id, user["email"], tier)
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
