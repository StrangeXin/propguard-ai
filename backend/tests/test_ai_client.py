"""AIClient wraps Anthropic, consumes quota, records cost."""

import os
import secrets
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.models.owner import Owner
from app.services.auth import register_user, _users_mem
from app.services.ai_client import AIClient
from app.services.quota import _reset_for_test

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_owner(plan="free") -> Owner:
    _users_mem.clear()
    u = register_user(f"aic-{secrets.token_hex(4)}@test.propguard.ai", "password123")
    o = Owner(id=u["id"], kind="user", plan=plan, metaapi_account_id=None)
    for action in ("ai_score", "ai_trade_tick", "briefing"):
        _reset_for_test(o.id, action)
    return o


def _mock_claude_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


class TestAIClient:
    @pytest.mark.asyncio
    async def test_score_signal_consumes_quota_and_records_cost(self):
        o = _fresh_owner(plan="free")
        with patch("app.services.ai_client.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(
                return_value=_mock_claude_response(
                    '{"score": 80, "risk_level": "low", "rationale": "ok"}', 300, 100))
            mock_cls.return_value = mock_client

            client = AIClient(o)
            result = await client.score_signal(
                system_prompt="sys", user_prompt="user", max_tokens=500,
            )
            assert result["text"].startswith("{")
            assert result["input_tokens"] == 300
            assert result["output_tokens"] == 100
            assert result["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_score_signal_blocked_over_quota(self):
        from app.services.quota import QuotaExceeded, check_and_consume
        o = Owner(
            id="00000000-0000-0000-0000-" + secrets.token_hex(6).ljust(12, "0"),
            kind="anon", plan="anon", metaapi_account_id=None,
        )
        _reset_for_test(o.id, "ai_score")
        for _ in range(10):  # anon daily_limit = 10
            check_and_consume(o, "ai_score")

        client = AIClient(o)
        with pytest.raises(QuotaExceeded):
            await client.score_signal(system_prompt="sys", user_prompt="user")

    @pytest.mark.asyncio
    async def test_trade_tick_uses_ai_trade_tick_action(self):
        o = _fresh_owner(plan="free")
        with patch("app.services.ai_client.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(
                return_value=_mock_claude_response('{"actions":[]}', 50, 20))
            mock_cls.return_value = mock_client
            client = AIClient(o)
            result = await client.trade_tick(system_prompt="sys", user_prompt="user")
            assert result["text"] == '{"actions":[]}'

    @pytest.mark.asyncio
    async def test_consume_quota_false_skips_check(self):
        """When the route layer already consumed via @require_quota, AIClient
        should not double-charge."""
        from app.services.quota import check_and_consume
        o = Owner(
            id="00000000-0000-0000-0000-" + secrets.token_hex(6).ljust(12, "0"),
            kind="anon", plan="anon", metaapi_account_id=None,
        )
        _reset_for_test(o.id, "ai_score")
        for _ in range(10):  # exhaust
            check_and_consume(o, "ai_score")

        with patch("app.services.ai_client.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(
                return_value=_mock_claude_response('{"ok":1}', 10, 5))
            mock_cls.return_value = mock_client
            client = AIClient(o)
            # Must NOT raise QuotaExceeded despite being over limit.
            result = await client.score_signal(
                system_prompt="s", user_prompt="u", consume_quota=False,
            )
            assert result["text"] == '{"ok":1}'
