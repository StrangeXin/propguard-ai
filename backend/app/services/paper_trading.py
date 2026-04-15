"""
Paper Trading Engine — simulated order execution with real market prices.
Tracks virtual positions, P&L, and order history.
Switch to live trading by changing execution backend.
"""

import logging
import secrets
from datetime import datetime
from dataclasses import dataclass, field

from app.services.kline_data import get_kline_data

logger = logging.getLogger(__name__)


@dataclass
class PaperOrder:
    id: str
    symbol: str
    side: str  # "buy" or "sell"
    size: float
    order_type: str  # "market", "limit", "stop"
    price: float | None  # None for market orders
    stop_loss: float | None
    take_profit: float | None
    status: str  # "pending", "filled", "cancelled"
    filled_price: float | None = None
    filled_at: str | None = None
    created_at: str = ""


@dataclass
class PaperPosition:
    id: str
    symbol: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    current_price: float = 0
    unrealized_pnl: float = 0
    opened_at: str = ""


@dataclass
class PaperAccount:
    initial_balance: float = 100000
    balance: float = 100000
    equity: float = 100000
    positions: list[PaperPosition] = field(default_factory=list)
    orders: list[PaperOrder] = field(default_factory=list)
    closed_trades: list[dict] = field(default_factory=list)
    total_trades: int = 0
    winning_trades: int = 0


# Per-user paper accounts
_accounts: dict[str, PaperAccount] = {}


def get_paper_account(user_id: str, initial_balance: float = 100000) -> PaperAccount:
    if user_id not in _accounts:
        _accounts[user_id] = PaperAccount(
            initial_balance=initial_balance,
            balance=initial_balance,
            equity=initial_balance,
        )
    return _accounts[user_id]


def reset_paper_account(user_id: str, initial_balance: float = 100000):
    _accounts[user_id] = PaperAccount(
        initial_balance=initial_balance,
        balance=initial_balance,
        equity=initial_balance,
    )


async def get_current_price(symbol: str) -> float | None:
    """Get latest price from real market data."""
    try:
        bars, _ = await get_kline_data(symbol=symbol, period="1m", count=1)
        if bars:
            return bars[-1]["close"]
    except Exception as e:
        logger.warning(f"Price fetch failed for {symbol}: {e}")
    return None


async def place_order(
    user_id: str,
    symbol: str,
    side: str,
    size: float,
    order_type: str = "market",
    price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Place a paper trading order."""
    account = get_paper_account(user_id)

    order = PaperOrder(
        id=secrets.token_hex(6),
        symbol=symbol.upper(),
        side=side.lower(),
        size=size,
        order_type=order_type,
        price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status="pending",
        created_at=datetime.now().isoformat(),
    )

    if order_type == "market":
        current_price = await get_current_price(symbol)
        if current_price is None:
            return {"success": False, "error": f"Cannot get price for {symbol}"}

        order.filled_price = current_price
        order.filled_at = datetime.now().isoformat()
        order.status = "filled"

        # Check if we're closing an existing position
        existing = next(
            (p for p in account.positions
             if p.symbol == order.symbol and
             ((p.side == "long" and order.side == "sell") or
              (p.side == "short" and order.side == "buy"))),
            None,
        )

        if existing and existing.size <= size:
            # Close position
            pnl = _calculate_pnl(existing, current_price)
            account.balance += pnl
            account.total_trades += 1
            if pnl > 0:
                account.winning_trades += 1
            account.closed_trades.append({
                "id": existing.id,
                "symbol": existing.symbol,
                "side": existing.side,
                "size": existing.size,
                "entry_price": existing.entry_price,
                "exit_price": current_price,
                "pnl": round(pnl, 2),
                "opened_at": existing.opened_at,
                "closed_at": datetime.now().isoformat(),
            })
            account.positions.remove(existing)
            remaining = size - existing.size
            if remaining > 0:
                # Open reverse position with remaining size
                _open_position(account, order, current_price, remaining)
        else:
            # Open new position or add to existing
            _open_position(account, order, current_price, size)

    account.orders.append(order)
    _update_equity(account)

    return {
        "success": True,
        "order": _order_to_dict(order),
        "account": _account_summary(account),
    }


def _open_position(account: PaperAccount, order: PaperOrder, price: float, size: float):
    pos = PaperPosition(
        id=secrets.token_hex(6),
        symbol=order.symbol,
        side="long" if order.side == "buy" else "short",
        size=size,
        entry_price=price,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
        current_price=price,
        opened_at=datetime.now().isoformat(),
    )
    account.positions.append(pos)


def _calculate_pnl(pos: PaperPosition, exit_price: float) -> float:
    diff = exit_price - pos.entry_price
    if pos.side == "short":
        diff = -diff
    # Simplified: assume 1 lot = 100K units for forex, 1 unit for crypto
    if pos.entry_price > 100:  # crypto
        return diff * pos.size
    else:  # forex
        return diff * pos.size * 100000


async def update_positions(user_id: str) -> PaperAccount:
    """Update all positions with current market prices, check SL/TP."""
    account = get_paper_account(user_id)
    closed = []

    for pos in account.positions:
        price = await get_current_price(pos.symbol)
        if price is None:
            continue
        pos.current_price = price
        pos.unrealized_pnl = round(_calculate_pnl(pos, price), 2)

        # Check stop loss
        if pos.stop_loss:
            hit = (pos.side == "long" and price <= pos.stop_loss) or \
                  (pos.side == "short" and price >= pos.stop_loss)
            if hit:
                closed.append((pos, pos.stop_loss, "stop_loss"))

        # Check take profit
        if pos.take_profit:
            hit = (pos.side == "long" and price >= pos.take_profit) or \
                  (pos.side == "short" and price <= pos.take_profit)
            if hit:
                closed.append((pos, pos.take_profit, "take_profit"))

    # Close triggered positions
    for pos, exit_price, reason in closed:
        pnl = _calculate_pnl(pos, exit_price)
        account.balance += pnl
        account.total_trades += 1
        if pnl > 0:
            account.winning_trades += 1
        account.closed_trades.append({
            "id": pos.id,
            "symbol": pos.symbol,
            "side": pos.side,
            "size": pos.size,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "reason": reason,
            "opened_at": pos.opened_at,
            "closed_at": datetime.now().isoformat(),
        })
        account.positions.remove(pos)

    _update_equity(account)
    return account


async def modify_position(user_id: str, position_id: str, stop_loss: float | None = None, take_profit: float | None = None) -> dict:
    """Modify SL/TP of an existing position."""
    account = get_paper_account(user_id)
    pos = next((p for p in account.positions if p.id == position_id), None)
    if not pos:
        return {"success": False, "error": "Position not found"}

    if stop_loss is not None:
        pos.stop_loss = stop_loss
    if take_profit is not None:
        pos.take_profit = take_profit

    return {"success": True, "position": _position_to_dict(pos)}


async def close_position(user_id: str, position_id: str) -> dict:
    """Close a specific position at market price."""
    account = get_paper_account(user_id)
    pos = next((p for p in account.positions if p.id == position_id), None)
    if not pos:
        return {"success": False, "error": "Position not found"}

    side = "sell" if pos.side == "long" else "buy"
    return await place_order(user_id, pos.symbol, side, pos.size)


def _update_equity(account: PaperAccount):
    unrealized = sum(p.unrealized_pnl for p in account.positions)
    account.equity = round(account.balance + unrealized, 2)


def _order_to_dict(o: PaperOrder) -> dict:
    return {
        "id": o.id, "symbol": o.symbol, "side": o.side, "size": o.size,
        "order_type": o.order_type, "price": o.price, "stop_loss": o.stop_loss,
        "take_profit": o.take_profit, "status": o.status,
        "filled_price": o.filled_price, "filled_at": o.filled_at,
        "created_at": o.created_at,
    }


def _position_to_dict(p: PaperPosition) -> dict:
    return {
        "id": p.id, "symbol": p.symbol, "side": p.side, "size": p.size,
        "entry_price": p.entry_price, "current_price": p.current_price,
        "stop_loss": p.stop_loss, "take_profit": p.take_profit,
        "unrealized_pnl": p.unrealized_pnl, "opened_at": p.opened_at,
    }


def _account_summary(account: PaperAccount) -> dict:
    win_rate = (account.winning_trades / account.total_trades * 100) if account.total_trades > 0 else 0
    return {
        "balance": account.balance,
        "equity": account.equity,
        "initial_balance": account.initial_balance,
        "pnl": round(account.equity - account.initial_balance, 2),
        "pnl_pct": round((account.equity - account.initial_balance) / account.initial_balance * 100, 2),
        "open_positions": len(account.positions),
        "total_trades": account.total_trades,
        "winning_trades": account.winning_trades,
        "win_rate": round(win_rate, 1),
        "positions": [_position_to_dict(p) for p in account.positions],
        "recent_trades": account.closed_trades[-10:],
    }
