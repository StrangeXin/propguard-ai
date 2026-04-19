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
