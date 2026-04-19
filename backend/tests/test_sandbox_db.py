"""Integration tests for sandbox DB layer. Requires Supabase dev env."""

import os
import secrets
from datetime import datetime, timezone

import pytest

from app.services.auth import register_user, _users_mem
from app.services.sandbox_db import (
    sandbox_get_or_create_account,
    sandbox_update_balance,
    sandbox_insert_position,
    sandbox_list_positions,
    sandbox_delete_position,
    sandbox_insert_closed_trade,
    sandbox_list_closed_trades,
    sandbox_reset_account,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_user_id():
    _users_mem.clear()
    return register_user(
        f"sb-{secrets.token_hex(4)}@test.propguard.ai", "password123"
    )["id"]


class TestSandboxDB:
    def test_account_created_on_first_access(self):
        uid = _fresh_user_id()
        acct = sandbox_get_or_create_account(uid, "user")
        assert float(acct["balance"]) == 100000.0
        assert float(acct["initial_balance"]) == 100000.0
        assert acct["owner_id"] == uid

    def test_update_balance(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        sandbox_update_balance(uid, 101000.0)
        acct = sandbox_get_or_create_account(uid, "user")
        assert float(acct["balance"]) == 101000.0

    def test_position_lifecycle(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        pid = sandbox_insert_position(
            uid, "user", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.0850, stop_loss=None, take_profit=None,
        )
        assert pid
        positions = sandbox_list_positions(uid)
        assert len(positions) == 1
        assert positions[0]["symbol"] == "EURUSD"
        sandbox_delete_position(pid)
        assert sandbox_list_positions(uid) == []

    def test_closed_trade_history(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        now = datetime.now(timezone.utc)
        sandbox_insert_closed_trade(
            uid, "user",
            symbol="BTCUSD", side="long", size=0.01,
            entry_price=60000.0, exit_price=61000.0, pnl=10.0,
            opened_at=now, closed_at=now,
        )
        trades = sandbox_list_closed_trades(uid)
        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTCUSD"

    def test_reset_wipes_state(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        sandbox_insert_position(uid, "user", symbol="EURUSD", side="long",
                                 size=0.1, entry_price=1.0)
        sandbox_update_balance(uid, 95000)
        sandbox_reset_account(uid, "user")
        acct = sandbox_get_or_create_account(uid, "user")
        assert float(acct["balance"]) == 100000.0
        assert sandbox_list_positions(uid) == []
