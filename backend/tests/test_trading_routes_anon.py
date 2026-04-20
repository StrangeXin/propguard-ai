"""Integration tests for anonymous trading reads + attributed writes.

Uses TestClient with a mocked broker layer — no real Supabase or MetaApi calls.
The app import is deferred inside the `client` fixture so the module collects
cleanly even when .env contains fields that the Settings model rejects (the
pre-existing pydantic-settings failures affect other test files at runtime,
not at collection time; this file avoids collection-time failure by importing
app lazily and patching get_settings before the lru_cache fires).

Tests:
  1. Anon GET /api/trading/account → 200, positions include user_label
  2. Anon POST /api/trading/order → 401
  3. Anon GET /api/accounts/{id}/briefing → 401
  4. Anon POST /api/sandbox/reset → 401 (require_user fires before 403)
  5. Logged-in-unbound POST /api/sandbox/reset → 403
  6. Logged-in-bound POST /api/sandbox/reset → 403
  7. Logged-in-unbound POST /api/trading/order on shared account → attribution recorded
  8. Logged-in-bound POST /api/trading/order on own account → attribution NOT recorded
"""

import time
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

import jwt
import pytest
from fastapi.testclient import TestClient


# ── Constants / shared user stubs ─────────────────────────────────────────

_UNBOUND_USER = {
    "id": "user-unbound-001",
    "email": "alice@x.com",
    "name": "Alice",
    "tier": "free",
    "metaapi_account_id": None,
    "password_hash": "salt:hash",
}

_BOUND_USER = {
    "id": "user-bound-001",
    "email": "bob@x.com",
    "name": "Bob",
    "tier": "pro",
    "metaapi_account_id": "acc-of-bob",
    "password_hash": "salt:hash",
}

_NOW = datetime(2026, 4, 20, 9, 0, 0)

# A mock Settings object that satisfies BrokerAPIClient.__init__ without DB.
_MOCK_SETTINGS = MagicMock(
    metaapi_account_id="",  # unset → sandbox in default factory
    broker_api_url="",
    broker_api_key="",
    broker_api_secret="",
    metaapi_token="",
)


def _make_token(user: dict, secret: str, algorithm: str) -> str:
    return jwt.encode(
        {"user_id": user["id"], "email": user["email"], "exp": time.time() + 3600},
        secret,
        algorithm=algorithm,
    )


# ── App fixture (lazy import + settings patch) ─────────────────────────────


@pytest.fixture(scope="module")
def app_and_consts():
    """Import app exactly once per module, with get_settings patched so the
    lru_cache never calls Settings() with the real .env (which has extra keys
    that the current pydantic-settings version rejects).
    """
    with patch("app.config.get_settings", return_value=_MOCK_SETTINGS):
        from app.config import get_settings as _gs
        _gs.cache_clear()  # ensure our mock is used if it was cached already

        from app.main import app
        from app.services.auth import JWT_SECRET, JWT_ALGORITHM

    return app, JWT_SECRET, JWT_ALGORITHM


@pytest.fixture
def client(app_and_consts):
    app, _, _ = app_and_consts
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def jwt_secret(app_and_consts):
    _, secret, algo = app_and_consts
    return secret, algo


@pytest.fixture
def mock_broker():
    from app.services.broker_types import AccountInfo, PositionDTO, OrderResult

    broker = MagicMock()
    broker.account_info = AsyncMock(return_value=AccountInfo(
        balance=100000.0, equity=100500.0, margin=500.0,
        free_margin=99500.0, currency="USD",
    ))
    broker.positions = AsyncMock(return_value=[
        PositionDTO(
            id="pos1", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.10, current_price=1.105, unrealized_pnl=50.0,
            stop_loss=None, take_profit=None, opened_at=_NOW,
        ),
    ])
    broker.pending_orders = AsyncMock(return_value=[])
    broker.history = AsyncMock(return_value=[])
    broker.place_market_order = AsyncMock(return_value=OrderResult(
        success=True, order_id="order-123", message=None,
    ))
    return broker


@pytest.fixture
def unbound_token(jwt_secret):
    """JWT for a logged-in unbound user. Patches DB lookups in verify_token."""
    secret, algo = jwt_secret
    token = _make_token(_UNBOUND_USER, secret, algo)
    with patch("app.services.auth.db_get_user_by_email", return_value=_UNBOUND_USER), \
         patch("app.services.auth.db_get_user_by_id", return_value=_UNBOUND_USER):
        yield token


@pytest.fixture
def bound_token(jwt_secret):
    """JWT for a logged-in bound user. Patches DB lookups in verify_token."""
    secret, algo = jwt_secret
    token = _make_token(_BOUND_USER, secret, algo)
    with patch("app.services.auth.db_get_user_by_email", return_value=_BOUND_USER), \
         patch("app.services.auth.db_get_user_by_id", return_value=_BOUND_USER):
        yield token


# ── Anon session helpers ────────────────────────────────────────────────────

def _anon_patches():
    """Context manager that stubs out the DB-backed anon session calls."""
    return (
        patch("app.services.owner_resolver.create_anon_session", return_value="anon-sid-test"),
        patch("app.services.owner_resolver.get_anon_session", return_value=None),
        patch("app.services.owner_resolver.touch_anon_session"),
    )


# ── Tests ──────────────────────────────────────────────────────────────────


def test_anon_can_read_account(client, mock_broker):
    """Anon GET /api/trading/account returns 200 and positions include user_label."""
    p1, p2, p3 = _anon_patches()
    with p1, p2, p3, \
         patch("app.api.routes.get_broker", return_value=mock_broker), \
         patch("app.api.routes._labels_for_positions", return_value={"pos1": "Mason"}):
        res = client.get("/api/trading/account")

    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    body = res.json()
    assert "positions" in body
    assert len(body["positions"]) == 1
    assert body["positions"][0]["user_label"] == "Mason"


def test_anon_cannot_place_order(client):
    """Anon POST /api/trading/order → 401."""
    p1, p2, p3 = _anon_patches()
    with p1, p2, p3:
        res = client.post("/api/trading/order", json={
            "symbol": "EURUSD", "side": "buy", "size": 0.1,
        })
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"


def test_anon_cannot_get_briefing(client):
    """Anon GET /api/accounts/{id}/briefing → 401."""
    p1, p2, p3 = _anon_patches()
    with p1, p2, p3:
        res = client.get(
            "/api/accounts/acc1/briefing",
            params={"firm_name": "ftmo", "account_size": 100000},
        )
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"


def test_sandbox_reset_rejected_for_anon(client):
    """Anon POST /api/sandbox/reset → 401 (require_user fires before the 403)."""
    p1, p2, p3 = _anon_patches()
    with p1, p2, p3:
        res = client.post("/api/sandbox/reset")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"


def test_sandbox_reset_rejected_for_logged_in_unbound(client, unbound_token):
    """Logged-in unbound user POST /api/sandbox/reset → 403."""
    res = client.post(
        "/api/sandbox/reset",
        headers={"Authorization": f"Bearer {unbound_token}"},
    )
    assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"


def test_sandbox_reset_rejected_for_bound(client, bound_token):
    """Logged-in bound user POST /api/sandbox/reset → 403."""
    res = client.post(
        "/api/sandbox/reset",
        headers={"Authorization": f"Bearer {bound_token}"},
    )
    assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"


def test_logged_in_shared_account_write_records_attribution(
    client, mock_broker, unbound_token,
):
    """Logged-in unbound user placing order on shared account → attribution recorded."""
    recorded = []

    def _record(**kwargs):
        recorded.append(kwargs)
        return True

    mock_settings = MagicMock(metaapi_account_id="shared-acc")

    with patch("app.api.routes.get_broker", return_value=mock_broker), \
         patch("app.api.routes.get_settings", return_value=mock_settings), \
         patch("app.api.routes.record_attribution", side_effect=_record), \
         patch("app.api.routes.get_user_by_id", return_value=_UNBOUND_USER):
        res = client.post(
            "/api/trading/order",
            json={"symbol": "EURUSD", "side": "buy", "size": 0.1},
            headers={"Authorization": f"Bearer {unbound_token}"},
        )

    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    assert len(recorded) == 1, f"Expected 1 attribution row, got {len(recorded)}: {recorded}"
    assert recorded[0]["broker_order_id"] == "order-123"
    assert recorded[0]["account_id"] == "shared-acc"
    assert recorded[0]["user_label"], "user_label must be non-empty"


def test_logged_in_bound_account_write_does_not_record(
    client, mock_broker, bound_token,
):
    """Logged-in bound user placing order on own account → NO attribution row."""
    recorded = []

    def _record(**kwargs):
        recorded.append(kwargs)
        return True

    with patch("app.api.routes.get_broker", return_value=mock_broker), \
         patch("app.api.routes.record_attribution", side_effect=_record):
        res = client.post(
            "/api/trading/order",
            json={"symbol": "EURUSD", "side": "buy", "size": 0.1},
            headers={"Authorization": f"Bearer {bound_token}"},
        )

    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    assert recorded == [], f"Expected no attribution rows, got {recorded}"
