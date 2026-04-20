"""Per-IP anonymous quota: prevents cookie-rotation abuse."""

import os
import secrets

import pytest

from app.services.ip_quota import check_ip
from app.services.quota import QuotaExceeded

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


class TestIPQuota:
    def test_first_call_allowed(self):
        ip_hash = secrets.token_hex(16)
        check_ip(ip_hash, "ai_score")  # no raise

    def test_limit_enforced(self):
        # ai_score IP limit default 100 per day
        ip_hash = secrets.token_hex(16)
        for _ in range(100):
            check_ip(ip_hash, "ai_score")
        with pytest.raises(QuotaExceeded) as exc:
            check_ip(ip_hash, "ai_score")
        assert exc.value.action.startswith("ip:")
        assert exc.value.limit == 100

    def test_uncapped_action_is_noop(self):
        ip_hash = secrets.token_hex(16)
        # briefing isn't in the IP cap mapping → no raise regardless
        for _ in range(5):
            check_ip(ip_hash, "briefing")

    def test_none_ip_is_noop(self):
        check_ip(None, "ai_score")
