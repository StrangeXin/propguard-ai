"""Regression guard: anonymous users see read-only preview; trading requires login.

Product decision (2026-04-20): anonymous visitors can view the shared FTMO
demo compliance data + use AI preview (ai-trade/tick, signals/parse) but
must log in before placing orders. This test locks in that boundary so
future refactors don't accidentally re-open trading to anon.
"""

import os
import secrets

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _client():
    from app.main import app
    return TestClient(app)


class TestAnonCanView:
    """Anon can see the shared demo + AI preview — no login required."""

    def test_anon_can_read_compliance(self):
        resp = _client().get(
            "/api/accounts/demo-001/compliance"
            "?firm_name=ftmo&account_size=100000&evaluation_type=1-step"
        )
        assert resp.status_code == 200
        assert "account" in resp.json()

    def test_anon_can_read_firms_list(self):
        assert _client().get("/api/firms").status_code == 200

    def test_anon_can_read_kline(self):
        assert _client().get("/api/kline/BTCUSD").status_code == 200

    def test_anon_can_call_ai_tick(self):
        resp = _client().post("/api/ai-trade/tick", json={
            "strategy": {"symbols": ["EURUSD"], "name": "preview", "rules": ["t"]},
            "firm_name": "ftmo", "account_size": 100000, "dry_run": True,
        })
        # 200 if Claude key configured, 402 if quota hit, 400 if config missing.
        # Never 401 — anon is allowed.
        assert resp.status_code != 401


class TestAnonCannotTrade:
    """Writing orders, modifying positions — all login-gated."""

    def test_anon_cannot_get_trading_account(self):
        assert _client().get("/api/trading/account").status_code == 401

    def test_anon_cannot_place_order(self):
        resp = _client().post("/api/trading/order", json={
            "symbol": "EURUSD", "side": "buy", "size": 0.1,
        })
        assert resp.status_code == 401

    def test_anon_cannot_execute_ai_actions(self):
        resp = _client().post("/api/ai-trade/execute", json={"actions": []})
        assert resp.status_code == 401


class TestSafeUser:
    """Regression: private fields never leak in any user-returning endpoint."""

    def test_safe_user_strips_password_and_encrypted_token(self):
        from app.services.auth import _safe_user
        raw = {
            "id": "u-1", "email": "a@b.c", "name": "X", "tier": "free",
            "password_hash": "should-not-leak",
            "metaapi_user_token_encrypted": "also-should-not-leak",
            "metaapi_account_id": "acct-123",
        }
        safe = _safe_user(raw)
        assert "password_hash" not in safe
        assert "metaapi_user_token_encrypted" not in safe
        assert safe["metaapi_account_id"] == "acct-123"

    def test_auth_me_does_not_leak_encrypted_token(self):
        """Live-wire test: /api/auth/me response must not contain the cipher."""
        from app.services.auth import register_user, login_user, _users_mem
        _users_mem.clear()
        email = f"leak-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        token = login_user(email, "password123")["token"]
        resp = _client().get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert "password_hash" not in user
        assert "metaapi_user_token_encrypted" not in user
