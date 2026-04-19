"""
AIClient — the single place that talks to Claude.

Invariants:
1. Every call checks + consumes the caller's quota before hitting Claude
   (unless the route layer already consumed via `@require_quota`, in which
   case the caller passes `consume_quota=False` to avoid double-charging).
2. Every call records token usage in ai_cost_ledger.
3. Shared Anthropic key used for all owners — BYOK is out of scope per
   spec §7.
"""

import logging
from typing import Any

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.owner import Owner
from app.services.ai_cost import record_tokens
from app.services.quota import check_and_consume

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self, owner: Owner):
        self._owner = owner
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.ai_model or "claude-haiku-4-5-20251001"

    async def _call(self, *, action: str, system_prompt: str, user_prompt: str,
                     max_tokens: int = 1024,
                     consume_quota: bool = True) -> dict[str, Any]:
        if consume_quota:
            check_and_consume(self._owner, action)

        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(getattr(block, "text", "") for block in resp.content)
        input_tokens = getattr(resp.usage, "input_tokens", 0)
        output_tokens = getattr(resp.usage, "output_tokens", 0)

        cost = record_tokens(
            self._owner, model=self._model,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )

        return {
            "text": text,
            "model": self._model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
        }

    async def score_signal(self, *, system_prompt: str, user_prompt: str,
                            max_tokens: int = 500,
                            consume_quota: bool = True) -> dict[str, Any]:
        return await self._call(
            action="ai_score", system_prompt=system_prompt,
            user_prompt=user_prompt, max_tokens=max_tokens,
            consume_quota=consume_quota,
        )

    async def trade_tick(self, *, system_prompt: str, user_prompt: str,
                          max_tokens: int = 2048,
                          consume_quota: bool = True) -> dict[str, Any]:
        return await self._call(
            action="ai_trade_tick", system_prompt=system_prompt,
            user_prompt=user_prompt, max_tokens=max_tokens,
            consume_quota=consume_quota,
        )

    async def briefing(self, *, system_prompt: str, user_prompt: str,
                        max_tokens: int = 1024,
                        consume_quota: bool = True) -> dict[str, Any]:
        return await self._call(
            action="briefing", system_prompt=system_prompt,
            user_prompt=user_prompt, max_tokens=max_tokens,
            consume_quota=consume_quota,
        )
