"""
MetaApiBroker — wraps existing live_trading.py functions so they satisfy
BrokerBase. Zero logic change from before; just a class-shaped interface.

The account_id passed in is the MetaApi account to route through — but
the current live_trading module is process-global (it picks the first
ready connection). For PR 2a we keep that behavior; future work will
make connection selection per-account.
"""

from datetime import datetime, timezone

from app.services.broker_base import BrokerBase  # noqa: F401 — for protocol check
from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)
from app.services.live_trading import (
    mt5_place_order,
    mt5_create_pending_order,
    mt5_close_position,
    mt5_close_position_partially,
    mt5_modify_position,
    mt5_cancel_order,
    mt5_get_positions,
    mt5_get_orders,
    mt5_get_trade_history,
    mt5_get_account_info,
    mt5_get_symbol_spec,
)


def _to_result(raw: dict) -> OrderResult:
    return OrderResult(
        success=bool(raw.get("success")),
        order_id=raw.get("order_id") or raw.get("orderId"),
        message=raw.get("error") or raw.get("message"),
    )


def _parse_deal_time(raw) -> datetime:
    """Parse MetaApi deal time (ISO8601 string or datetime) into aware UTC.
    Falls back to "now" only if raw is missing/unparsable."""
    if raw is None or raw == "":
        return datetime.now(timezone.utc)
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class MetaApiBroker:
    """BrokerBase implementation routing through live_trading → MetaApi SDK."""

    def __init__(self, metaapi_account_id: str):
        self._account_id = metaapi_account_id

    async def account_info(self) -> AccountInfo:
        data = await mt5_get_account_info() or {}
        return AccountInfo(
            balance=float(data.get("balance", 0)),
            equity=float(data.get("equity", 0)),
            margin=float(data.get("margin", 0)),
            free_margin=float(data.get("freeMargin", data.get("free_margin", 0))),
            currency=str(data.get("currency", "USD")),
        )

    async def positions(self) -> list[PositionDTO]:
        # live_trading.mt5_get_positions() already normalizes MetaApi's raw
        # shape (POSITION_TYPE_BUY → "long", openPrice → entry_price, etc.),
        # so read the normalized field names here, not the raw MetaApi ones.
        raw = await mt5_get_positions() or []
        out: list[PositionDTO] = []
        for p in raw:
            side_val = p.get("side", "long")
            out.append(PositionDTO(
                id=str(p.get("id", "")),
                symbol=str(p.get("symbol", "")),
                side=side_val if side_val in ("long", "short") else "long",
                size=float(p.get("volume", 0)),
                entry_price=float(p.get("entry_price", 0)),
                current_price=float(p.get("current_price", 0)),
                unrealized_pnl=float(p.get("profit", 0)),
                stop_loss=float(p["stop_loss"]) if p.get("stop_loss") else None,
                take_profit=float(p["take_profit"]) if p.get("take_profit") else None,
                opened_at=_parse_deal_time(p.get("time")),
            ))
        return out

    async def pending_orders(self) -> list[OrderDTO]:
        # mt5_get_orders() passes `type` through raw and renames openPrice→price
        # and stopLoss→stop_loss / takeProfit→take_profit.
        raw = await mt5_get_orders() or []
        out: list[OrderDTO] = []
        for o in raw:
            t = str(o.get("type", "")).upper()
            out.append(OrderDTO(
                id=str(o.get("id", "")),
                symbol=str(o.get("symbol", "")),
                side="buy" if "BUY" in t else "sell",
                size=float(o.get("volume", 0)),
                order_type="limit" if "LIMIT" in t else "stop",
                price=float(o.get("price", 0)),
                stop_loss=float(o["stop_loss"]) if o.get("stop_loss") else None,
                take_profit=float(o["take_profit"]) if o.get("take_profit") else None,
                status="pending",
                created_at=_parse_deal_time(o.get("time")),
            ))
        return out

    async def place_market_order(self, symbol: str, side: str, volume: float,
                                  sl: float | None = None,
                                  tp: float | None = None) -> OrderResult:
        return _to_result(await mt5_place_order(symbol, side, volume, sl, tp))

    async def place_pending_order(self, symbol: str, side: str, volume: float,
                                   order_type: str, price: float,
                                   sl: float | None = None,
                                   tp: float | None = None) -> OrderResult:
        return _to_result(await mt5_create_pending_order(
            symbol, side, volume, price, order_type, sl, tp,
        ))

    async def close_position(self, position_id: str) -> OrderResult:
        return _to_result(await mt5_close_position(position_id))

    async def close_position_partial(self, position_id: str, volume: float) -> OrderResult:
        return _to_result(await mt5_close_position_partially(position_id, volume))

    async def modify_position(self, position_id: str,
                               sl: float | None = None,
                               tp: float | None = None) -> OrderResult:
        return _to_result(await mt5_modify_position(position_id, sl, tp))

    async def cancel_order(self, order_id: str) -> OrderResult:
        return _to_result(await mt5_cancel_order(order_id))

    async def history(self, limit: int = 50) -> list[ClosedTrade]:
        raw = await mt5_get_trade_history() or []
        out: list[ClosedTrade] = []
        for d in raw[:limit]:
            try:
                deal_time = _parse_deal_time(d.get("time"))
                out.append(ClosedTrade(
                    id=str(d.get("id", "")),
                    symbol=str(d.get("symbol", "")),
                    side="long" if d.get("side") == "buy" else "short",
                    size=float(d.get("volume", 0)),
                    entry_price=float(d.get("price", 0)),
                    exit_price=float(d.get("price", 0)),
                    pnl=float(d.get("profit", 0)),
                    opened_at=deal_time,
                    closed_at=deal_time,
                    order_id=str(d.get("orderId")) if d.get("orderId") else None,
                    position_id=str(d.get("positionId")) if d.get("positionId") else None,
                ))
            except Exception:
                continue
        return out

    async def symbol_info(self, symbol: str) -> dict:
        return await mt5_get_symbol_spec(symbol) or {}

    async def reset(self) -> None:
        raise NotImplementedError("MetaApi accounts cannot be reset programmatically")
