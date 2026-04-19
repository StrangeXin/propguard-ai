"""MetaApiBroker delegates to live_trading module. Tests use mocks."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.metaapi_broker import MetaApiBroker
from app.services.broker_base import BrokerBase


class TestMetaApiBrokerProtocol:
    def test_satisfies_broker_base(self):
        broker = MetaApiBroker("acc-123")
        assert isinstance(broker, BrokerBase)


class TestMetaApiBrokerDelegation:
    @pytest.mark.asyncio
    async def test_place_market_order_delegates(self):
        with patch("app.services.metaapi_broker.mt5_place_order",
                   new=AsyncMock(return_value={"success": True, "order_id": "o1"})) as m:
            b = MetaApiBroker("acc-123")
            result = await b.place_market_order("EURUSD", "buy", 0.1)
            assert result.success
            assert result.order_id == "o1"
            m.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_account_info_delegates(self):
        fake = {
            "balance": 100000, "equity": 99500,
            "margin": 500, "freeMargin": 99000, "currency": "USD",
        }
        with patch("app.services.metaapi_broker.mt5_get_account_info",
                   new=AsyncMock(return_value=fake)):
            b = MetaApiBroker("acc-123")
            info = await b.account_info()
            assert info.balance == 100000
            assert info.equity == 99500
            assert info.free_margin == 99000

    @pytest.mark.asyncio
    async def test_reset_raises_not_implemented(self):
        b = MetaApiBroker("acc-123")
        with pytest.raises(NotImplementedError):
            await b.reset()
