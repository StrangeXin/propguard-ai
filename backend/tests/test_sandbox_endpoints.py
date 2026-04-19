"""Smoke tests for sandbox-specific API endpoints."""

import os
import secrets

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_token(client: TestClient) -> str:
    email = f"sbe-{secrets.token_hex(4)}@test.propguard.ai"
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    resp = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return resp.json()["token"]


def _client():
    from app.main import app
    return TestClient(app)


class TestSandboxReset:
    def test_reset_requires_auth(self):
        c = _client()
        resp = c.post("/api/sandbox/reset")
        assert resp.status_code == 401

    def test_reset_returns_ok_for_sandbox_user(self):
        c = _client()
        token = _fresh_token(c)
        resp = c.post("/api/sandbox/reset",
                      headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
