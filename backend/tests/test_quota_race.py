"""Race-condition smoke test for check_and_consume.

Fires N concurrent requests at a limit of L; asserts exactly L succeed and
(N - L) raise QuotaExceeded. Without the atomic RPC this would sometimes
miss counts (SELECT-then-UPSERT lost-update bug from PR 2b review I2).
"""

import asyncio
import os
import secrets

import pytest

from app.models.owner import Owner
from app.services.quota import check_and_consume, QuotaExceeded, _reset_for_test

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


@pytest.mark.asyncio
async def test_concurrent_consume_does_not_lose_counts():
    # anon ai_score limit = 10
    owner = Owner(
        id="00000000-0000-0000-0000-" + secrets.token_hex(6).ljust(12, "0"),
        kind="anon", plan="anon", metaapi_account_id=None,
    )
    _reset_for_test(owner.id, "ai_score")

    async def one_call():
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, check_and_consume, owner, "ai_score")
            return "ok"
        except QuotaExceeded:
            return "limit"

    # 12 concurrent calls; 10 should succeed, 2 should raise.
    results = await asyncio.gather(*[one_call() for _ in range(12)])
    ok_count = sum(1 for r in results if r == "ok")
    limit_count = sum(1 for r in results if r == "limit")
    assert ok_count == 10, f"expected exactly 10 successes, got {ok_count}"
    assert limit_count == 2, f"expected exactly 2 rejections, got {limit_count}"
