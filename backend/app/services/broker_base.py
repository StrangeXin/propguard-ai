"""
BrokerBase — the runtime-checkable Protocol both broker implementations
satisfy. Every trading route calls methods on this interface; the factory
picks the right implementation per request based on Owner.metaapi_account_id.
"""

from typing import Protocol, runtime_checkable

from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)


@runtime_checkable
class BrokerBase(Protocol):
    async def account_info(self) -> AccountInfo: ...
    async def positions(self) -> list[PositionDTO]: ...
    async def pending_orders(self) -> list[OrderDTO]: ...

    async def place_market_order(
        self, symbol: str, side: str, volume: float,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult: ...

    async def place_pending_order(
        self, symbol: str, side: str, volume: float,
        order_type: str, price: float,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult: ...

    async def close_position(self, position_id: str) -> OrderResult: ...
    async def close_position_partial(
        self, position_id: str, volume: float,
    ) -> OrderResult: ...
    async def modify_position(
        self, position_id: str,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult: ...

    async def cancel_order(self, order_id: str) -> OrderResult: ...

    async def history(self, limit: int = 50) -> list[ClosedTrade]: ...
    async def symbol_info(self, symbol: str) -> dict: ...

    async def reset(self) -> None:
        """Sandbox-only. MetaApi implementation raises NotImplementedError."""
        ...
