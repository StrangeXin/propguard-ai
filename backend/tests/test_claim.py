"""Claim flow: anon data follows the user on registration.

Note: tests that verified sandbox-specific row migration (sandbox_positions,
sandbox_closed_trades) were removed when sandbox_db.py was deleted. The DB
tables themselves still hold historical data; the claim logic in claim.py still
migrates them, but the test helpers that seeded those tables are gone.
The remaining tests cover non-sandbox behaviour (noop, idempotency at row=0).
"""

import os
import secrets

import pytest

from app.services.auth import _users_mem, register_user
from app.services.anon_sessions import create_anon_session, get_anon_session
from app.services.claim import claim_anon_data

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _register(email: str) -> str:
    _users_mem.clear()
    return register_user(email, "password123")["id"]


class TestClaimFlow:
    def test_missing_anon_id_is_noop(self):
        user_id = _register(f"claim-noop-{secrets.token_hex(4)}@test.propguard.ai")
        counts = claim_anon_data(
            "00000000-0000-0000-0000-000000000000", user_id)
        assert all(v == 0 for v in counts.values())

    def test_idempotent_empty(self):
        """Calling claim twice on an anon session with no rows is always noop."""
        anon_id = create_anon_session()
        user_id = _register(f"claim-idem-{secrets.token_hex(4)}@test.propguard.ai")
        first = claim_anon_data(anon_id, user_id)
        second = claim_anon_data(anon_id, user_id)
        assert all(v == 0 for v in first.values())
        assert all(v == 0 for v in second.values())
