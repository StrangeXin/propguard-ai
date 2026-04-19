"""Test ai_cost_ledger writes."""

import os
import secrets

import pytest

from app.models.owner import Owner
from app.services.auth import register_user, _users_mem
from app.services.ai_cost import record_tokens, get_cost_today, COST_PER_1M

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _owner() -> Owner:
    _users_mem.clear()
    u = register_user(f"cost-{secrets.token_hex(4)}@test.propguard.ai", "password123")
    return Owner(id=u["id"], kind="user", plan="free", metaapi_account_id=None)


class TestAICost:
    def test_record_tokens_inserts_row_and_returns_cost(self):
        o = _owner()
        cost = record_tokens(o, model="claude-haiku-4-5-20251001",
                             input_tokens=1000, output_tokens=500)
        assert cost > 0
        today_total = get_cost_today(o.id)
        assert today_total >= cost

    def test_unknown_model_uses_default_rate(self):
        o = _owner()
        cost = record_tokens(o, model="claude-unknown-v999",
                             input_tokens=100, output_tokens=50)
        assert cost > 0

    def test_zero_tokens_records_zero_cost(self):
        o = _owner()
        cost = record_tokens(o, model="claude-haiku-4-5-20251001",
                             input_tokens=0, output_tokens=0)
        assert cost == 0
