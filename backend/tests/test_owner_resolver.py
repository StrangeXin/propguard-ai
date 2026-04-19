"""
Tests for get_owner FastAPI dependency.
Uses a disposable minimal FastAPI app + TestClient so tests don't depend on
the full PropGuard wiring.
"""

import os
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.models.owner import Owner
from app.services.owner_resolver import get_owner

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _make_app():
    app = FastAPI()

    @app.get("/whoami")
    def whoami(owner: Owner = Depends(get_owner)):
        return {
            "id": owner.id,
            "kind": owner.kind,
            "plan": owner.plan,
            "metaapi_account_id": owner.metaapi_account_id,
        }

    return app


class TestGetOwnerAnonymous:
    def test_no_credentials_mints_anon_session(self):
        client = TestClient(_make_app())
        resp = client.get("/whoami")
        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] == "anon"
        assert body["plan"] == "anon"
        assert body["metaapi_account_id"] is None
        assert "anon_session_id" in resp.cookies


class TestGetOwnerExistingAnon:
    def test_cookie_reuses_existing_session(self):
        client = TestClient(_make_app())
        r1 = client.get("/whoami")
        sid = r1.cookies["anon_session_id"]
        r2 = client.get("/whoami", cookies={"anon_session_id": sid})
        assert r2.json()["id"] == sid
        assert r2.json()["kind"] == "anon"

    def test_unknown_cookie_mints_new_session(self):
        client = TestClient(_make_app())
        bogus = "00000000-0000-0000-0000-000000000000"
        resp = client.get("/whoami", cookies={"anon_session_id": bogus})
        assert resp.json()["id"] != bogus
        assert resp.json()["kind"] == "anon"


class TestGetOwnerUser:
    def test_valid_jwt_returns_user_owner(self):
        import secrets
        from app.services.auth import register_user, login_user, _users_mem
        _users_mem.clear()
        email = f"ownerjwt-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        token = login_user(email, "password123")["token"]

        client = TestClient(_make_app())
        resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] == "user"
        assert body["plan"] == "free"
        assert "anon_session_id" not in resp.cookies

    def test_invalid_jwt_falls_back_to_anon(self):
        client = TestClient(_make_app())
        resp = client.get("/whoami", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 200
        assert resp.json()["kind"] == "anon"


class TestRequireUser:
    def _app_with_guard(self):
        from app.services.owner_resolver import require_user
        app = FastAPI()

        @app.get("/private")
        def private(owner: Owner = Depends(require_user)):
            return {"id": owner.id}

        return app

    def test_anon_rejected_with_401(self):
        resp = TestClient(self._app_with_guard()).get("/private")
        assert resp.status_code == 401
        assert "authentication" in resp.json()["detail"].lower()

    def test_user_allowed(self):
        import secrets
        from app.services.auth import register_user, login_user, _users_mem
        _users_mem.clear()
        email = f"reqguard-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        token = login_user(email, "password123")["token"]
        resp = TestClient(self._app_with_guard()).get(
            "/private", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
