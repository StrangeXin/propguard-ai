"""
SandboxBroker — simulated trading against per-owner DB state.

Prices come from live market data (kline_data). Fills are instant at
midprice ± half-spread. Positions and closed trades persist in Supabase
so state survives process restarts and is isolated per owner.

Paid users with bound MetaApi accounts use MetaApiBroker instead; this
class is only constructed for Owners with metaapi_account_id == None.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.models.owner import Owner
from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)
from app.services.paper_trading import get_current_price
from app.services.sandbox_db import (
    sandbox_get_or_create_account,
    sandbox_update_balance,
    sandbox_insert_position,
    sandbox_list_positions,
    sandbox_get_position,
    sandbox_update_position,
    sandbox_delete_position,
    sandbox_insert_closed_trade,
    sandbox_list_closed_trades,
    sandbox_reset_account,
)

logger = logging.getLogger(__name__)

# data/sandbox_spreads.json is at the project root; this file is in
# backend/app/services/, so go up 3 levels.
_SPREAD_CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "sandbox_spreads.json"


def _load_spreads() -> dict:
    try:
        with _SPREAD_CONFIG_PATH.open() as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"sandbox spread config missing: {e}")
        return {"default_spread_pips": 2, "symbols": {}}


_SPREADS = _load_spreads()


def _symbol_spread(symbol: str) -> tuple[float, float]:
    cfg = _SPREADS.get("symbols", {}).get(symbol.upper())
    if cfg:
        return cfg["pip_size"], cfg["spread_pips"]
    return 0.0001, _SPREADS.get("default_spread_pips", 2)


def _is_supported(symbol: str) -> bool:
    """Only symbols with known PnL contract math are tradable in sandbox v1.

    Non-USD-quote pairs (USDJPY, USDCAD, USDCHF, *JPY crosses) require currency
    conversion that isn't implemented, so we reject them at order time rather
    than silently return wrong PnL.
    """
    return symbol.upper() in _SPREADS.get("symbols", {})


def _apply_spread(mid: float, symbol: str, side: str) -> float:
    """side is 'buy' or 'sell'. Buy fills at ask (mid + half-spread)."""
    pip_size, spread_pips = _symbol_spread(symbol)
    half = pip_size * spread_pips / 2
    return mid + half if side == "buy" else mid - half


def _pnl(side: str, size: float, entry: float, exit: float, symbol: str) -> float:
    """Contract size heuristic: forex 100K per lot, crypto/commodity 1:1."""
    diff = (exit - entry) if side == "long" else (entry - exit)
    sym = symbol.upper()
    if sym.startswith("XAU") or sym.startswith("XAG"):
        contract = 100
    elif sym.endswith("USD") and not sym.startswith(("EUR", "GBP", "AUD", "NZD", "USD")):
        contract = 1
    elif sym in ("NAS100", "US30", "SPX500"):
        contract = 1
    else:
        contract = 100000
    return diff * size * contract


class SandboxBroker:
    def __init__(self, owner: Owner):
        self._owner = owner
        self._account = sandbox_get_or_create_account(owner.id, owner.kind)

    async def account_info(self) -> AccountInfo:
        balance = float(self._account.get("balance", 100000))
        positions_raw = sandbox_list_positions(self._owner.id)
        unrealized = 0.0
        for row in positions_raw:
            price = await get_current_price(row["symbol"])
            if price is None:
                continue
            unrealized += _pnl(
                row["side"], float(row["size"]),
                float(row["entry_price"]), price,
                row["symbol"],
            )
        equity = balance + unrealized
        return AccountInfo(
            balance=round(balance, 2),
            equity=round(equity, 2),
            margin=0.0,
            free_margin=round(equity, 2),
            currency="USD",
        )

    async def positions(self) -> list[PositionDTO]:
        rows = sandbox_list_positions(self._owner.id)
        dtos = []
        for row in rows:
            price = await get_current_price(row["symbol"])
            current = price if price is not None else float(row["entry_price"])
            opened = row["opened_at"]
            if isinstance(opened, str):
                opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            dtos.append(PositionDTO(
                id=row["id"],
                symbol=row["symbol"],
                side=row["side"],
                size=float(row["size"]),
                entry_price=float(row["entry_price"]),
                current_price=current,
                unrealized_pnl=round(_pnl(
                    row["side"], float(row["size"]),
                    float(row["entry_price"]), current,
                    row["symbol"],
                ), 2),
                stop_loss=float(row["stop_loss"]) if row.get("stop_loss") else None,
                take_profit=float(row["take_profit"]) if row.get("take_profit") else None,
                opened_at=opened,
            ))
        return dtos

    async def pending_orders(self) -> list[OrderDTO]:
        return []

    async def place_market_order(
        self, symbol: str, side: str, volume: float,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult:
        if not _is_supported(symbol):
            return OrderResult(
                success=False, order_id=None,
                message=f"Sandbox does not support {symbol} yet. Supported symbols: EURUSD, GBPUSD, AUDUSD, NZDUSD, XAUUSD, XAGUSD, BTCUSD, ETHUSD, SOLUSD, NAS100, US30, SPX500.",
            )
        mid = await get_current_price(symbol)
        if mid is None:
            return OrderResult(success=False, order_id=None,
                               message=f"Cannot get price for {symbol}")
        fill = _apply_spread(mid, symbol, side)
        dir_ = "long" if side == "buy" else "short"
        pid = sandbox_insert_position(
            self._owner.id, self._owner.kind,
            symbol=symbol.upper(), side=dir_, size=volume,
            entry_price=fill, stop_loss=sl, take_profit=tp,
        )
        if not pid:
            return OrderResult(success=False, order_id=None,
                               message="Sandbox persistence failed")
        return OrderResult(success=True, order_id=pid, message=None)

    async def place_pending_order(self, *_, **__) -> OrderResult:
        return OrderResult(False, None, "not implemented yet")

    async def close_position(self, position_id: str) -> OrderResult:
        row = sandbox_get_position(position_id)
        if not row or row["owner_id"] != self._owner.id:
            return OrderResult(False, None, "Position not found")
        return await self._close_internal(row, size_to_close=float(row["size"]))

    async def close_position_partial(self, position_id: str, volume: float) -> OrderResult:
        row = sandbox_get_position(position_id)
        if not row or row["owner_id"] != self._owner.id:
            return OrderResult(False, None, "Position not found")
        size = float(row["size"])
        if volume <= 0 or volume >= size:
            return OrderResult(False, None, "Invalid partial close volume")
        return await self._close_internal(row, size_to_close=volume)

    async def _close_internal(self, row: dict, size_to_close: float) -> OrderResult:
        symbol = row["symbol"]
        side = row["side"]
        mid = await get_current_price(symbol)
        if mid is None:
            return OrderResult(False, None, f"Cannot get price for {symbol}")
        exit_side = "sell" if side == "long" else "buy"
        exit_price = _apply_spread(mid, symbol, exit_side)
        pnl = _pnl(side, size_to_close, float(row["entry_price"]), exit_price, symbol)
        new_balance = float(self._account.get("balance", 100000)) + pnl

        opened_at = row["opened_at"]
        if isinstance(opened_at, str):
            opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))

        # Order of writes matters: we take "commit" to mean "position deleted".
        # If any step before the delete fails, bail before mutating state so the
        # user can retry. This mirrors the PR 1 lesson on silent DB failures.
        if not sandbox_insert_closed_trade(
            self._owner.id, self._owner.kind,
            symbol=symbol, side=side, size=size_to_close,
            entry_price=float(row["entry_price"]), exit_price=exit_price,
            pnl=round(pnl, 2),
            opened_at=opened_at, closed_at=datetime.now(timezone.utc),
        ):
            return OrderResult(False, None, "Failed to persist closed trade")

        if not sandbox_update_balance(self._owner.id, new_balance):
            return OrderResult(False, None, "Failed to update balance")
        self._account["balance"] = new_balance

        remaining = float(row["size"]) - size_to_close
        if remaining <= 1e-9:
            sandbox_delete_position(row["id"])
        else:
            sandbox_update_position(row["id"], {"size": remaining})
        return OrderResult(True, row["id"], None)

    async def modify_position(self, position_id: str,
                               sl: float | None = None,
                               tp: float | None = None) -> OrderResult:
        row = sandbox_get_position(position_id)
        if not row or row["owner_id"] != self._owner.id:
            return OrderResult(False, None, "Position not found")
        updates: dict = {}
        if sl is not None:
            updates["stop_loss"] = sl
        if tp is not None:
            updates["take_profit"] = tp
        if updates:
            sandbox_update_position(position_id, updates)
        return OrderResult(True, position_id, None)

    async def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(False, None, "not implemented yet")

    async def history(self, limit: int = 50) -> list[ClosedTrade]:
        rows = sandbox_list_closed_trades(self._owner.id, limit=limit)
        out = []
        for row in rows:
            opened = row["opened_at"]
            closed = row["closed_at"]
            if isinstance(opened, str):
                opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            if isinstance(closed, str):
                closed = datetime.fromisoformat(closed.replace("Z", "+00:00"))
            out.append(ClosedTrade(
                id=row["id"],
                symbol=row["symbol"],
                side=row["side"],
                size=float(row["size"]),
                entry_price=float(row["entry_price"]),
                exit_price=float(row["exit_price"]),
                pnl=float(row["pnl"]),
                opened_at=opened,
                closed_at=closed,
            ))
        return out

    async def symbol_info(self, symbol: str) -> dict:
        return {"symbol": symbol, "sandbox": True}

    async def reset(self) -> None:
        sandbox_reset_account(self._owner.id, self._owner.kind)
        self._account = sandbox_get_or_create_account(self._owner.id, self._owner.kind)
