"""
Broker value objects shared by MetaApiBroker and SandboxBroker.

These are the public surface — route handlers and UI-facing JSON shape come
from these. Keep them frozen + validated so nobody produces malformed state.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str = "USD"


@dataclass(frozen=True)
class PositionDTO:
    id: str
    symbol: str
    side: Literal["long", "short"]
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None
    take_profit: float | None
    opened_at: datetime

    def __post_init__(self):
        if self.side not in ("long", "short"):
            raise ValueError("side must be 'long' or 'short'")


@dataclass(frozen=True)
class OrderDTO:
    id: str
    symbol: str
    side: Literal["buy", "sell"]
    size: float
    order_type: Literal["market", "limit", "stop"]
    price: float | None
    stop_loss: float | None
    take_profit: float | None
    status: Literal["pending", "filled", "cancelled"]
    created_at: datetime


@dataclass(frozen=True)
class OrderResult:
    success: bool
    order_id: str | None
    message: str | None


@dataclass(frozen=True)
class ClosedTrade:
    id: str
    symbol: str
    side: Literal["long", "short"]
    size: float
    entry_price: float
    exit_price: float
    pnl: float
    opened_at: datetime
    closed_at: datetime
    order_id: str | None = None
    position_id: str | None = None
