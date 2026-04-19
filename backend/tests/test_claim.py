"""Claim flow: anon sandbox data follows the user on registration."""

import os
import secrets
from datetime import datetime, timezone

import pytest

from app.services.auth import _users_mem, register_user
from app.services.anon_sessions import create_anon_session, get_anon_session
from app.services.claim import claim_anon_data
from app.services.sandbox_db import (
    sandbox_get_or_create_account,
    sandbox_insert_position,
    sandbox_list_positions,
    sandbox_insert_closed_trade,
    sandbox_list_closed_trades,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _register(email: str) -> str:
    _users_mem.clear()
    return register_user(email, "password123")["id"]


class TestClaimFlow:
    def test_sandbox_positions_migrate(self):
        anon_id = create_anon_session()
        sandbox_get_or_create_account(anon_id, "anon")
        sandbox_insert_position(anon_id, "anon",
            symbol="EURUSD", side="long", size=0.1, entry_price=1.0850)
        sandbox_insert_position(anon_id, "anon",
            symbol="BTCUSD", side="short", size=0.01, entry_price=60000)
        assert len(sandbox_list_positions(anon_id)) == 2

        user_id = _register(f"claim-{secrets.token_hex(4)}@test.propguard.ai")
        counts = claim_anon_data(anon_id, user_id)
        assert counts["sandbox_positions"] == 2
        assert counts["sandbox_accounts"] >= 1  # anon acct deleted or re-owned
        assert len(sandbox_list_positions(user_id)) == 2
        assert len(sandbox_list_positions(anon_id)) == 0
        assert get_anon_session(anon_id)["claimed_by_user_id"] == user_id

    def test_sandbox_closed_trades_migrate(self):
        anon_id = create_anon_session()
        sandbox_get_or_create_account(anon_id, "anon")
        now = datetime.now(timezone.utc)
        sandbox_insert_closed_trade(
            anon_id, "anon", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.08, exit_price=1.09, pnl=10.0,
            opened_at=now, closed_at=now,
        )
        user_id = _register(f"claim-ct-{secrets.token_hex(4)}@test.propguard.ai")
        counts = claim_anon_data(anon_id, user_id)
        assert counts["sandbox_closed_trades"] == 1
        assert len(sandbox_list_closed_trades(user_id)) == 1

    def test_missing_anon_id_is_noop(self):
        user_id = _register(f"claim-noop-{secrets.token_hex(4)}@test.propguard.ai")
        counts = claim_anon_data(
            "00000000-0000-0000-0000-000000000000", user_id)
        assert all(v == 0 for v in counts.values())

    def test_idempotent(self):
        anon_id = create_anon_session()
        sandbox_get_or_create_account(anon_id, "anon")
        sandbox_insert_position(anon_id, "anon",
            symbol="EURUSD", side="long", size=0.1, entry_price=1.0850)
        user_id = _register(f"claim-idem-{secrets.token_hex(4)}@test.propguard.ai")
        first = claim_anon_data(anon_id, user_id)
        second = claim_anon_data(anon_id, user_id)
        # First call moved the position; second should find nothing to move.
        assert first["sandbox_positions"] == 1
        assert second["sandbox_positions"] == 0
