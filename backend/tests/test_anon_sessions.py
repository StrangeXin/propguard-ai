"""
Tests for anon_sessions DB layer.
Requires Supabase dev env (SUPABASE_URL + SUPABASE_KEY in backend/.env).
"""

import os
import pytest

from app.services.anon_sessions import (
    create_anon_session,
    get_anon_session,
    touch_anon_session,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


class TestAnonSessions:
    def test_create_returns_uuid(self):
        sid = create_anon_session(ip_hash="hash1", user_agent="ua1")
        assert isinstance(sid, str) and len(sid) == 36

    def test_get_returns_row(self):
        sid = create_anon_session()
        row = get_anon_session(sid)
        assert row is not None
        assert row["id"] == sid
        assert row["claimed_by_user_id"] is None

    def test_get_missing_returns_none(self):
        assert get_anon_session("00000000-0000-0000-0000-000000000000") is None

    def test_touch_updates_last_active(self):
        import time
        sid = create_anon_session()
        before = get_anon_session(sid)["last_active_at"]
        time.sleep(1.1)  # ensure timestamp resolution difference
        touch_anon_session(sid)
        after = get_anon_session(sid)["last_active_at"]
        assert after > before
