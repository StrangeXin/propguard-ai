"""db_save_ai_trade_log accepts anon owners (M3 from PR 2b review)."""

import os
import secrets

import pytest

from app.services.database import db_save_ai_trade_log

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


class TestAnonAITradeLog:
    def test_anon_owner_persists(self):
        anon_id = "00000000-0000-0000-0000-" + secrets.token_hex(6).ljust(12, "0")
        result = db_save_ai_trade_log(
            strategy_name="anon-test",
            symbols="EURUSD",
            analysis="x",
            actions_planned=0,
            actions_executed=0,
            prompt="p",
            result={},
            dry_run=True,
            owner_id=anon_id,
            owner_kind="anon",
        )
        assert result is not None
        assert result["owner_id"] == anon_id
        assert result["owner_kind"] == "anon"
        assert result.get("user_id") is None

    def test_no_owner_context_returns_none(self):
        result = db_save_ai_trade_log(
            strategy_name="bad", symbols="",
            analysis="x", actions_planned=0, actions_executed=0,
            prompt="p", result={}, dry_run=True,
        )
        assert result is None
