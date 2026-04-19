"""Tests for BrokerBase protocol.

Verify the protocol can be satisfied by a minimal stub. Actual implementations
are tested separately (test_sandbox_broker.py, test_metaapi_broker.py).
"""

import pytest
from datetime import datetime, timezone

from app.services.broker_base import BrokerBase
from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)


class _StubBroker:
    async def account_info(self) -> AccountInfo:
        return AccountInfo(100000, 100000, 0, 100000)

    async def positions(self) -> list[PositionDTO]:
        return []

    async def pending_orders(self) -> list[OrderDTO]:
        return []

    async def place_market_order(self, symbol, side, volume,
                                  sl=None, tp=None) -> OrderResult:
        return OrderResult(True, "o1", None)

    async def place_pending_order(self, symbol, side, volume, order_type,
                                   price, sl=None, tp=None) -> OrderResult:
        return OrderResult(True, "o2", None)

    async def close_position(self, position_id) -> OrderResult:
        return OrderResult(True, position_id, None)

    async def close_position_partial(self, position_id, volume) -> OrderResult:
        return OrderResult(True, position_id, None)

    async def modify_position(self, position_id, sl=None, tp=None) -> OrderResult:
        return OrderResult(True, position_id, None)

    async def cancel_order(self, order_id) -> OrderResult:
        return OrderResult(True, order_id, None)

    async def history(self, limit=50) -> list[ClosedTrade]:
        return []

    async def symbol_info(self, symbol) -> dict:
        return {}

    async def reset(self) -> None:
        return None


class TestBrokerBaseProtocol:
    def test_stub_satisfies_protocol(self):
        stub: BrokerBase = _StubBroker()
        assert isinstance(stub, BrokerBase)

    @pytest.mark.asyncio
    async def test_stub_methods_callable(self):
        stub: BrokerBase = _StubBroker()
        info = await stub.account_info()
        assert info.balance == 100000
        assert (await stub.positions()) == []
        assert (await stub.place_market_order("EURUSD", "buy", 0.1)).success
