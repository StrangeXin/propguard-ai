"""SandboxBroker tests against real Supabase + mocked market prices."""

import os
import secrets
from unittest.mock import patch, AsyncMock

import pytest

from app.models.owner import Owner
from app.services.auth import register_user, _users_mem
from app.services.sandbox_broker import SandboxBroker
from app.services.sandbox_db import sandbox_reset_account

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


@pytest.fixture
def owner():
    _users_mem.clear()
    email = f"sbx-{secrets.token_hex(4)}@test.propguard.ai"
    user = register_user(email, "password123")
    o = Owner(id=user["id"], kind="user", plan="free", metaapi_account_id=None)
    sandbox_reset_account(o.id, "user")
    yield o
    sandbox_reset_account(o.id, "user")


class TestSandboxAccountInfo:
    @pytest.mark.asyncio
    async def test_fresh_account_starts_at_100k(self, owner):
        b = SandboxBroker(owner)
        info = await b.account_info()
        assert info.balance == 100000.0
        assert info.equity == 100000.0
        assert info.free_margin == 100000.0


class TestSandboxMarketOrder:
    @pytest.mark.asyncio
    async def test_buy_creates_long_position(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            result = await b.place_market_order(
                symbol="EURUSD", side="buy", volume=0.1,
            )
            assert result.success
            positions = await b.positions()
            assert len(positions) == 1
            assert positions[0].side == "long"
            assert positions[0].size == 0.1
            # entry price = mid + half-spread (1 pip on EURUSD → 0.00005)
            assert positions[0].entry_price > 1.0850

    @pytest.mark.asyncio
    async def test_sell_creates_short_position(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            result = await b.place_market_order(
                symbol="EURUSD", side="sell", volume=0.1,
            )
            assert result.success
            positions = await b.positions()
            assert positions[0].side == "short"

    @pytest.mark.asyncio
    async def test_missing_price_returns_error(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=None)):
            b = SandboxBroker(owner)
            result = await b.place_market_order(
                symbol="WEIRDX", side="buy", volume=0.1,
            )
            assert not result.success
            assert "price" in result.message.lower()


class TestSandboxClosePosition:
    @pytest.mark.asyncio
    async def test_close_full_position_settles_pnl(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.1)
            assert r.success
            pid = r.order_id

        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0860)):
            # Re-construct so the broker reloads account state, mimicking
            # how routes.py creates a fresh broker per request.
            b2 = SandboxBroker(owner)
            r2 = await b2.close_position(pid)
            assert r2.success
            info = await b2.account_info()
            assert info.balance > 100000
            assert len(await b2.positions()) == 0

    @pytest.mark.asyncio
    async def test_close_partial(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.3)
            pid = r.order_id

        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0860)):
            b2 = SandboxBroker(owner)
            r2 = await b2.close_position_partial(pid, 0.1)
            assert r2.success
            positions = await b2.positions()
            assert len(positions) == 1
            assert abs(positions[0].size - 0.2) < 1e-9

    @pytest.mark.asyncio
    async def test_modify_position_sl_tp(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.1)
            pid = r.order_id
            m = await b.modify_position(pid, sl=1.08, tp=1.10)
            assert m.success
            positions = await b.positions()
            assert positions[0].stop_loss == 1.08
            assert positions[0].take_profit == 1.10


class TestSandboxHistory:
    @pytest.mark.asyncio
    async def test_closed_trades_appear_in_history(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.1)

        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0860)):
            b2 = SandboxBroker(owner)
            await b2.close_position(r.order_id)

        trades = await b2.history(limit=10)
        assert len(trades) == 1
        assert trades[0].symbol == "EURUSD"
        assert trades[0].pnl > 0


class TestSandboxReset:
    @pytest.mark.asyncio
    async def test_reset_restores_initial_state(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            await b.place_market_order("EURUSD", "buy", 0.1)

        await b.reset()
        info = await b.account_info()
        assert info.balance == 100000.0
        assert info.equity == 100000.0
        assert len(await b.positions()) == 0
        assert (await b.history()) == []
