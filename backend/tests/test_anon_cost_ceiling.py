"""Global anon cost ceiling blocks Claude calls when exceeded."""

import os
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.owner import Owner
from app.services.ai_client import AIClient
from app.services.quota import QuotaExceeded

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


class TestAnonCostCeiling:
    @pytest.mark.asyncio
    async def test_anon_blocked_when_ceiling_exceeded(self):
        owner = Owner(
            id="00000000-0000-0000-0000-" + secrets.token_hex(6).ljust(12, "0"),
            kind="anon", plan="anon", metaapi_account_id=None,
        )
        with patch("app.services.ai_client.AsyncAnthropic"), \
             patch("app.services.ai_cost.get_anon_cost_today", return_value=999.0):
            client = AIClient(owner)
            with pytest.raises(QuotaExceeded) as exc:
                await client.score_signal(
                    system_prompt="", user_prompt="x",
                    consume_quota=False,
                )
            assert "anon-cost-ceiling" in exc.value.action

    @pytest.mark.asyncio
    async def test_user_not_affected_by_anon_ceiling(self):
        owner = Owner(
            id="11111111-1111-1111-1111-111111111111",
            kind="user", plan="free", metaapi_account_id=None,
        )
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text='{"ok":1}')]
        mock_resp.usage = MagicMock(input_tokens=10, output_tokens=5)
        with patch("app.services.ai_client.AsyncAnthropic") as mock_cls, \
             patch("app.services.ai_cost.get_anon_cost_today", return_value=999.0):
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client
            client = AIClient(owner)
            result = await client.score_signal(
                system_prompt="", user_prompt="x", consume_quota=False,
            )
            assert result["text"] == '{"ok":1}'
