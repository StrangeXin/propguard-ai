"""Quota checks against plan_quotas + owner_quota_usage tables."""

import os
import secrets

import pytest

from app.models.owner import Owner
from app.services.auth import register_user, _users_mem
from app.services.quota import check_and_consume, QuotaExceeded, _reset_for_test

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_user_owner(plan: str = "free") -> Owner:
    _users_mem.clear()
    email = f"q-{secrets.token_hex(4)}@test.propguard.ai"
    user = register_user(email, "password123")
    return Owner(id=user["id"], kind="user", plan=plan, metaapi_account_id=None)


def _fresh_anon_owner() -> Owner:
    return Owner(
        id="00000000-0000-0000-0000-" + secrets.token_hex(6).ljust(12, "0"),
        kind="anon",
        plan="anon",
        metaapi_account_id=None,
    )


class TestQuota:
    def test_first_call_allowed_and_counter_incremented(self):
        owner = _fresh_user_owner(plan="free")
        _reset_for_test(owner.id, "ai_score")
        assert check_and_consume(owner, "ai_score") is True

    def test_anon_limit_respected(self):
        owner = _fresh_anon_owner()
        _reset_for_test(owner.id, "ai_score")
        # anon ai_score daily_limit = 10
        for _ in range(10):
            assert check_and_consume(owner, "ai_score") is True
        with pytest.raises(QuotaExceeded) as exc:
            check_and_consume(owner, "ai_score")
        assert exc.value.limit == 10
        assert exc.value.used == 10
        assert exc.value.action == "ai_score"

    def test_premium_is_unlimited(self):
        owner = _fresh_user_owner(plan="premium")
        _reset_for_test(owner.id, "ai_score")
        for _ in range(25):
            assert check_and_consume(owner, "ai_score") is True

    def test_unknown_plan_action_rejected(self):
        owner = _fresh_user_owner(plan="free")
        with pytest.raises(QuotaExceeded):
            check_and_consume(owner, "nonexistent_action")

    def test_separate_actions_have_independent_counters(self):
        owner = _fresh_anon_owner()
        _reset_for_test(owner.id, "ai_score")
        _reset_for_test(owner.id, "briefing")
        for _ in range(10):
            check_and_consume(owner, "ai_score")
        # briefing still has 1/day left (anon)
        assert check_and_consume(owner, "briefing") is True


class TestRequireQuotaDependency:
    def _app(self):
        from fastapi import Depends, FastAPI
        from app.services.owner_resolver import require_user
        from app.services.quota import require_quota
        app = FastAPI()

        @app.post("/ai/score")
        async def score(owner: Owner = Depends(require_user),
                         _q=Depends(require_quota("ai_score"))):
            return {"ok": True}

        return app

    def test_402_when_over_limit(self):
        from fastapi.testclient import TestClient
        from app.services.auth import register_user, login_user, _users_mem

        _users_mem.clear()
        email = f"rq-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        login = login_user(email, "password123")
        token = login["token"]
        uid = login["user"]["id"]

        _reset_for_test(uid, "ai_score")
        owner = Owner(id=uid, kind="user", plan="free", metaapi_account_id=None)
        # Burn through the 20/day free quota
        for _ in range(20):
            check_and_consume(owner, "ai_score")

        client = TestClient(self._app())
        resp = client.post("/ai/score",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 402
        err = resp.json()["detail"]
        assert err["code"] == "QUOTA_EXCEEDED"
        assert err["action"] == "ai_score"
        assert "upgrade_url" in err
        assert "resets_at" in err
