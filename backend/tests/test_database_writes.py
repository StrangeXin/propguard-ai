"""
Integration tests for the four DB helpers that write to tables with the
NOT NULL owner_id / owner_kind constraint added in the owner-abstraction
migration. Without these columns set, the NOT NULL constraints reject
the insert; the helpers' blanket except-Exception-return-None masked
this silently until a reviewer reproduced it live.

Purpose of this file: guarantee every write helper populates owner_id
+ owner_kind from user_id going forward.
"""

import os
import secrets

import pytest

from app.services.auth import register_user, _users_mem
from app.services.database import (
    db_save_alert,
    db_save_ai_trade_log,
    db_save_signal,
    db_save_trading_account,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_user():
    _users_mem.clear()
    email = f"dbwrite-{secrets.token_hex(4)}@test.propguard.ai"
    return register_user(email, "password123")


class TestDatabaseWrites:
    def test_db_save_signal_populates_owner(self):
        user = _fresh_user()
        result = db_save_signal(
            user["id"],
            {"symbol": "EURUSD", "direction": "buy", "raw_text": "test"},
            {"score": 80, "risk_level": "low", "rationale": "ok"},
        )
        assert result is not None
        assert result["owner_id"] == user["id"]
        assert result["owner_kind"] == "user"

    def test_db_save_alert_populates_owner(self):
        user = _fresh_user()
        result = db_save_alert(
            user["id"],
            {
                "account_id": "demo-001",
                "firm_name": "ftmo",
                "rule_type": "daily_loss",
                "alert_level": "WARNING",
                "message": "test alert",
                "remaining": 500.0,
                "remaining_pct": 20.0,
            },
        )
        assert result is not None
        assert result["owner_id"] == user["id"]
        assert result["owner_kind"] == "user"

    def test_db_save_ai_trade_log_populates_owner(self):
        user = _fresh_user()
        result = db_save_ai_trade_log(
            user["id"],
            strategy_name="test",
            symbols="BTCUSD",
            analysis="analysis text",
            actions_planned=0,
            actions_executed=0,
            prompt="prompt",
            result={},
            dry_run=True,
        )
        assert result is not None
        assert result["owner_id"] == user["id"]
        assert result["owner_kind"] == "user"

    def test_db_save_trading_account_populates_owner(self):
        user = _fresh_user()
        result = db_save_trading_account(
            user["id"],
            {
                "account_id": f"acc-{secrets.token_hex(4)}",
                "firm_name": "ftmo",
                "account_size": 100000,
                "broker_type": "mock",
                "label": "test",
            },
        )
        assert result is not None
        assert result["owner_id"] == user["id"]
        assert result["owner_kind"] == "user"
