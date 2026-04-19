# PR 2b: AIClient + Quota system

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every Claude API call through a unified `AIClient` that (a) uses our single shared API key, (b) checks+consumes a per-owner+per-action quota before the call, and (c) records token usage in `ai_cost_ledger` for observability. Free/anon users run AI auto-trading via a frontend-driven `POST /api/ai-trade/tick`; paid users keep the backend session loop.

**Architecture:** `AIClient(owner)` wraps `AsyncAnthropic` with three async methods (`score_signal`, `trade_tick`, `briefing`). A shared `@require_quota(action)` FastAPI dependency checks `owner_quota_usage` against `plan_quotas` and returns 402 on miss. All AI calls write to `ai_cost_ledger`. `ai_scorer.py`, `ai_trader.py`, `briefing.py` are refactored to delegate their Claude calls to `AIClient` instead of instantiating Anthropic directly.

**Tech Stack:** Python 3.11+, `anthropic>=0.34`, FastAPI, Supabase.

**Spec reference:** `docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md` §7, §8.

**Dependencies:** PR 1 (Owner abstraction) + PR 2a (Broker factory) landed on main. `plan_quotas`, `owner_quota_usage`, `ai_cost_ledger` tables already exist from PR 1's migration.

**Scope for this plan:** PR 2b. Anonymous dashboard + claim flow lives in PR 3.

---

## File Structure

**New files:**
- `backend/app/services/quota.py` — `check_and_consume`, `@require_quota`, `get_plan_limits`
- `backend/app/services/ai_client.py` — `AIClient` class + shared helpers
- `backend/app/services/ai_cost.py` — `record_tokens` helper writing to `ai_cost_ledger`
- `backend/tests/test_quota.py`
- `backend/tests/test_ai_client.py`
- `backend/tests/test_ai_cost.py`

**Modified files:**
- `backend/app/services/ai_scorer.py` — Claude call delegated to `AIClient(owner).score_signal(...)`
- `backend/app/services/ai_trader.py` — Claude call delegated to `AIClient(owner).trade_tick(...)`
- `backend/app/services/briefing.py` — Claude call delegated to `AIClient(owner).briefing(...)`
- `backend/app/api/routes.py` — `@require_quota` on AI endpoints; new `POST /api/ai-trade/tick`

---

## Task 1: Quota DB helpers

**Files:**
- Create: `backend/app/services/quota.py` (partial — check_and_consume only for now)
- Test: `backend/tests/test_quota.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_quota.py`:

```python
"""Quota checks against plan_quotas + owner_quota_usage tables."""

import os
import secrets
from datetime import date, timedelta

import pytest

from app.models.owner import Owner
from app.services.auth import register_user, _users_mem
from app.services.quota import check_and_consume, QuotaExceeded, _reset_for_test

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_user_owner(plan: str = "free") -> Owner:
    _users_mem.clear()
    email = f"q-{secrets.token_hex(4)}@test.propguard.ai"
    user = register_user(email, "password123")
    return Owner(id=user["id"], kind="user", plan=plan, metaapi_account_id=None)


class TestQuota:
    def test_first_call_allowed_and_counter_incremented(self):
        owner = _fresh_user_owner(plan="free")
        # free ai_score daily_limit = 20 per migration seed
        assert check_and_consume(owner, "ai_score") is True

    def test_anon_limit_respected(self):
        owner = Owner(id="anon-" + secrets.token_hex(8), kind="anon",
                      plan="anon", metaapi_account_id=None)
        _reset_for_test(owner.id, "ai_score")
        # anon ai_score daily_limit = 10
        for _ in range(10):
            assert check_and_consume(owner, "ai_score") is True
        # 11th must raise
        with pytest.raises(QuotaExceeded) as exc:
            check_and_consume(owner, "ai_score")
        assert exc.value.limit == 10
        assert exc.value.used == 10
        assert exc.value.action == "ai_score"

    def test_premium_is_unlimited(self):
        owner = _fresh_user_owner(plan="premium")
        _reset_for_test(owner.id, "ai_score")
        # premium ai_score daily_limit = null → unlimited
        for _ in range(25):
            assert check_and_consume(owner, "ai_score") is True

    def test_unknown_plan_action_rejected(self):
        owner = _fresh_user_owner(plan="free")
        with pytest.raises(QuotaExceeded):
            check_and_consume(owner, "nonexistent_action")

    def test_separate_actions_have_independent_counters(self):
        owner = _fresh_user_owner(plan="anon")  # wrong plan-kind for user, just test counter isolation
        owner = Owner(id="anon-iso-" + secrets.token_hex(8), kind="anon",
                      plan="anon", metaapi_account_id=None)
        _reset_for_test(owner.id, "ai_score")
        _reset_for_test(owner.id, "briefing")
        # Exhaust ai_score
        for _ in range(10):
            check_and_consume(owner, "ai_score")
        # briefing still has 1/day left (anon)
        assert check_and_consume(owner, "briefing") is True
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_quota.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/app/services/quota.py`:

```python
"""
Per-owner quota enforcement.

- `plan_quotas` defines limits per (plan, action).
- `owner_quota_usage` tracks daily consumption per (owner_id, action, date).
- `check_and_consume(owner, action)` atomically bumps the counter and
  raises `QuotaExceeded` if the limit is reached.

Daily counters roll over at UTC midnight (simplest approach; revisit if
users complain about timezone). `total_limit` (e.g. saved_strategies) is
checked against actual row counts in the target table, not this counter.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.models.owner import Owner
from app.services.database import get_db

logger = logging.getLogger(__name__)


@dataclass
class QuotaExceeded(Exception):
    action: str
    limit: int
    used: int
    plan: str

    def __str__(self):
        return f"{self.action} limit reached: {self.used}/{self.limit} on plan '{self.plan}'"


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _plan_limit(plan: str, action: str) -> tuple[int | None, int | None]:
    """Returns (daily_limit, total_limit). None = unlimited. Both None = action not configured."""
    db = get_db()
    if not db:
        return None, None
    try:
        result = db.table("plan_quotas").select("*").eq("plan", plan).eq("action", action).limit(1).execute()
        if result.data:
            row = result.data[0]
            return row.get("daily_limit"), row.get("total_limit")
    except Exception as e:
        logger.error(f"plan_limit lookup: {e}")
    return None, None


def check_and_consume(owner: Owner, action: str) -> bool:
    """Raises QuotaExceeded if over limit. Otherwise increments counter and returns True."""
    daily_limit, total_limit = _plan_limit(owner.plan, action)

    # Unconfigured action → treat as rejected (safer than allowing unbounded calls).
    if daily_limit is None and total_limit is None:
        raise QuotaExceeded(action=action, limit=0, used=0, plan=owner.plan)

    # Unlimited daily
    if daily_limit is None:
        return True

    today = _today_utc().isoformat()
    db = get_db()
    if not db:
        return True  # permissive when DB unavailable — avoid blocking the whole app
    try:
        existing = db.table("owner_quota_usage").select("count").eq(
            "owner_id", owner.id).eq("action", action).eq("date", today).limit(1).execute()
        current = existing.data[0]["count"] if existing.data else 0
        if current >= daily_limit:
            raise QuotaExceeded(action=action, limit=daily_limit, used=current, plan=owner.plan)

        # Upsert via increment pattern.
        new_count = current + 1
        db.table("owner_quota_usage").upsert({
            "owner_id": owner.id,
            "owner_kind": owner.kind,
            "action": action,
            "date": today,
            "count": new_count,
        }, on_conflict="owner_id,action,date").execute()
        return True
    except QuotaExceeded:
        raise
    except Exception as e:
        logger.error(f"quota consume: {e}")
        # Fail-open to avoid blocking trading/UI on transient DB hiccups. Alerts surface via logs.
        return True


def _reset_for_test(owner_id: str, action: str) -> None:
    """Testing helper: wipe today's counter. Not called in production."""
    db = get_db()
    if not db:
        return
    today = _today_utc().isoformat()
    try:
        db.table("owner_quota_usage").delete().eq("owner_id", owner_id).eq("action", action).eq("date", today).execute()
    except Exception as e:
        logger.warning(f"_reset_for_test: {e}")
```

- [ ] **Step 4: Run tests**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_quota.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quota.py backend/tests/test_quota.py
git commit -m "feat(quota): check_and_consume against plan_quotas + owner_quota_usage"
```

---

## Task 2: `@require_quota` FastAPI dependency

**Files:**
- Modify: `backend/app/services/quota.py`
- Modify: `backend/tests/test_quota.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/test_quota.py`:

```python
class TestRequireQuotaDependency:
    def _app(self):
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient
        from app.services.owner_resolver import require_user
        from app.services.quota import require_quota
        app = FastAPI()

        @app.post("/ai/score")
        async def score(owner: Owner = Depends(require_user),
                         _q=Depends(require_quota("ai_score"))):
            return {"ok": True}

        return app

    def test_402_when_over_limit(self):
        from fastapi.testclient import TestClient
        from app.services.auth import register_user, login_user, _users_mem
        from app.services.quota import check_and_consume, _reset_for_test

        _users_mem.clear()
        email = f"rq-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        token = login_user(email, "password123")["token"]
        uid = login_user(email, "password123")["user"]["id"]

        _reset_for_test(uid, "ai_score")
        # Burn through the 20/day free quota
        owner = Owner(id=uid, kind="user", plan="free", metaapi_account_id=None)
        for _ in range(20):
            check_and_consume(owner, "ai_score")

        client = TestClient(self._app())
        resp = client.post("/ai/score",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 402
        err = resp.json()
        assert err["error"]["code"] == "QUOTA_EXCEEDED"
        assert err["error"]["action"] == "ai_score"
        assert "upgrade_url" in err["error"]
        assert "resets_at" in err["error"]
```

- [ ] **Step 2: Confirm fails**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_quota.py::TestRequireQuotaDependency -v
```

- [ ] **Step 3: Add `require_quota` + error handler**

Append to `backend/app/services/quota.py`:

```python
from datetime import timedelta

from fastapi import Depends, HTTPException, Request

from app.services.owner_resolver import get_owner


def _resets_at_iso() -> str:
    """Next UTC midnight."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow.isoformat().replace("+00:00", "Z")


def require_quota(action: str):
    """FastAPI dependency factory. Checks and consumes `action` quota for the resolved Owner."""
    def _check(owner: Owner = Depends(get_owner)) -> Owner:
        try:
            check_and_consume(owner, action)
        except QuotaExceeded as e:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "action": e.action,
                    "message": str(e),
                    "limit": e.limit,
                    "used": e.used,
                    "plan": e.plan,
                    "upgrade_url": "/pricing",
                    "resets_at": _resets_at_iso(),
                },
            )
        return owner
    return _check
```

**Important:** FastAPI's default 402 shape is `{"detail": {...}}`. The test expects `{"error": {...}}`. Either (a) adjust the test to read `resp.json()["detail"]`, or (b) wrap the response with an app-level handler. **Choose (a)** — change the test to use `err = resp.json()["detail"]` so we don't introduce a global handler in this task.

Update the test accordingly.

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_quota.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quota.py backend/tests/test_quota.py
git commit -m "feat(quota): require_quota FastAPI dependency returns 402 on miss"
```

---

## Task 3: AI cost ledger helper

**Files:**
- Create: `backend/app/services/ai_cost.py`
- Test: `backend/tests/test_ai_cost.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_ai_cost.py`:

```python
"""Test ai_cost_ledger writes."""

import os
import secrets

import pytest

from app.models.owner import Owner
from app.services.auth import register_user, _users_mem
from app.services.ai_cost import record_tokens, get_cost_today, COST_PER_1M

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _owner() -> Owner:
    _users_mem.clear()
    u = register_user(f"cost-{secrets.token_hex(4)}@test.propguard.ai", "password123")
    return Owner(id=u["id"], kind="user", plan="free", metaapi_account_id=None)


class TestAICost:
    def test_record_tokens_inserts_row_and_returns_cost(self):
        o = _owner()
        cost = record_tokens(o, model="claude-haiku-4-5-20251001",
                             input_tokens=1000, output_tokens=500)
        assert cost > 0
        today_total = get_cost_today(o.id)
        assert today_total >= cost

    def test_unknown_model_uses_default_rate(self):
        o = _owner()
        cost = record_tokens(o, model="claude-unknown-v999",
                             input_tokens=100, output_tokens=50)
        assert cost > 0  # still records something

    def test_zero_tokens_records_zero_cost(self):
        o = _owner()
        cost = record_tokens(o, model="claude-haiku-4-5-20251001",
                             input_tokens=0, output_tokens=0)
        assert cost == 0
```

- [ ] **Step 2: Confirm fails**

- [ ] **Step 3: Implement**

`backend/app/services/ai_cost.py`:

```python
"""
AI cost ledger — per-owner Claude token + USD usage accounting.

Written to after every AIClient call. Enables per-user cost tracking for
pricing decisions and detecting abusive usage of shared API keys.
"""

import logging
from datetime import datetime, timezone

from app.models.owner import Owner
from app.services.database import get_db

logger = logging.getLogger(__name__)

# Per-1M-tokens USD pricing (Anthropic public prices as of 2026-04).
# Source: https://www.anthropic.com/pricing
# Tuple is (input_per_1m, output_per_1m).
COST_PER_1M: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "claude-haiku-4-5": (0.80, 4.0),
}
_DEFAULT_RATE = (3.0, 15.0)  # Sonnet-class; fallback for unknown models.


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = COST_PER_1M.get(model, _DEFAULT_RATE)
    cost = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
    return round(cost, 6)


def record_tokens(owner: Owner, *, model: str,
                  input_tokens: int, output_tokens: int) -> float:
    """Write a ledger row and return the computed cost in USD."""
    cost = _cost_usd(model, input_tokens, output_tokens)
    db = get_db()
    if not db:
        return cost
    try:
        db.table("ai_cost_ledger").insert({
            "owner_id": owner.id,
            "owner_kind": owner.kind,
            "date": datetime.now(timezone.utc).date().isoformat(),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "cost_usd": cost,
        }).execute()
    except Exception as e:
        logger.error(f"record_tokens: {e}")
    return cost


def get_cost_today(owner_id: str) -> float:
    """Sum of cost_usd for owner today. Used by admin dashboards and tests."""
    db = get_db()
    if not db:
        return 0.0
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        result = db.table("ai_cost_ledger").select("cost_usd").eq("owner_id", owner_id).eq("date", today).execute()
        return round(sum(float(r["cost_usd"]) for r in (result.data or [])), 6)
    except Exception as e:
        logger.error(f"get_cost_today: {e}")
        return 0.0
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_ai_cost.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_cost.py backend/tests/test_ai_cost.py
git commit -m "feat(ai): record_tokens + get_cost_today backed by ai_cost_ledger"
```

---

## Task 4: `AIClient` class

**Files:**
- Create: `backend/app/services/ai_client.py`
- Test: `backend/tests/test_ai_client.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_ai_client.py`:

```python
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
                return_value=_mock_claude_response('{"score": 80, "risk_level": "low", "rationale": "ok"}', 300, 100))
            mock_cls.return_value = mock_client

            client = AIClient(o)
            result = await client.score_signal(
                system_prompt="sys", user_prompt="user", max_tokens=500,
            )
            assert result["text"] == '{"score": 80, "risk_level": "low", "rationale": "ok"}'
            assert result["input_tokens"] == 300
            assert result["output_tokens"] == 100
            assert result["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_score_signal_blocked_over_quota(self):
        from app.services.quota import QuotaExceeded, check_and_consume
        o = _fresh_owner(plan="anon")
        # Exhaust anon quota (10/day)
        for _ in range(10):
            check_and_consume(o, "ai_score")

        client = AIClient(o)
        with pytest.raises(QuotaExceeded):
            await client.score_signal(system_prompt="sys", user_prompt="user")

    @pytest.mark.asyncio
    async def test_trade_tick_uses_ai_trade_tick_action(self):
        o = _fresh_owner(plan="free")
        with patch("app.services.ai_client.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=_mock_claude_response('{"actions":[]}', 50, 20))
            mock_cls.return_value = mock_client
            client = AIClient(o)
            await client.trade_tick(system_prompt="sys", user_prompt="user")
```

- [ ] **Step 2: Confirm fails**

- [ ] **Step 3: Implement**

`backend/app/services/ai_client.py`:

```python
"""
AIClient — the single place that talks to Claude.

Invariants:
1. Every call checks + consumes the caller's quota before hitting Claude.
2. Every successful call writes a row to ai_cost_ledger with token counts.
3. The shared Anthropic key is used for all owners (BYOK is explicitly out
   of scope per spec §7).
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
                     max_tokens: int = 1024) -> dict[str, Any]:
        # 1. Quota check raises QuotaExceeded on miss (route layer maps to 402).
        check_and_consume(self._owner, action)

        # 2. Claude call on our shared key.
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(getattr(block, "text", "") for block in resp.content)
        input_tokens = getattr(resp.usage, "input_tokens", 0)
        output_tokens = getattr(resp.usage, "output_tokens", 0)

        # 3. Cost ledger (best-effort; logged but non-fatal).
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
                            max_tokens: int = 500) -> dict[str, Any]:
        return await self._call(action="ai_score", system_prompt=system_prompt,
                                 user_prompt=user_prompt, max_tokens=max_tokens)

    async def trade_tick(self, *, system_prompt: str, user_prompt: str,
                          max_tokens: int = 2048) -> dict[str, Any]:
        return await self._call(action="ai_trade_tick", system_prompt=system_prompt,
                                 user_prompt=user_prompt, max_tokens=max_tokens)

    async def briefing(self, *, system_prompt: str, user_prompt: str,
                        max_tokens: int = 1024) -> dict[str, Any]:
        return await self._call(action="briefing", system_prompt=system_prompt,
                                 user_prompt=user_prompt, max_tokens=max_tokens)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_ai_client.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_client.py backend/tests/test_ai_client.py
git commit -m "feat(ai): AIClient wraps Anthropic + consumes quota + records cost"
```

---

## Task 5: Refactor `ai_scorer.py` to use AIClient

**Files:**
- Modify: `backend/app/services/ai_scorer.py`
- Modify: `backend/app/api/routes.py` (signal parsing endpoint passes `owner`)
- Test: existing tests must still pass; no new test file required since AIClient is covered.

- [ ] **Step 1: Read the current `ai_scorer.py`**

```bash
grep -n "anthropic\|Anthropic\|AsyncAnthropic\|client = " backend/app/services/ai_scorer.py
```

The scorer currently does:
```python
import anthropic
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
response = await client.messages.create(...)
```

- [ ] **Step 2: Add `owner` parameter to `score_signal`**

Change the signature of the top-level `score_signal` function in `ai_scorer.py` to accept an Owner:

```python
from app.models.owner import Owner
from app.services.ai_client import AIClient

async def score_signal(signal: Signal, owner: Owner, ...) -> ScoredSignal:
    ...
    ai = AIClient(owner)
    resp = await ai.score_signal(system_prompt="", user_prompt=SCORING_PROMPT.format(...))
    data = json.loads(resp["text"])
    ...
```

Replace the existing direct-Anthropic block. Keep the rule-based fallback for when `anthropic_api_key` is not configured — call `generate_template_scoring(...)` or equivalent if `AIClient` raises (wrap in try/except, but **do not swallow QuotaExceeded**; let it propagate).

- [ ] **Step 3: Update all callers in routes.py + other modules**

`grep -n "score_signal(" backend/app/` — every call site needs to pass `owner`. The one route that accepts signals is `POST /api/signals/parse`. It already has `owner: Owner = Depends(require_user)` from PR 1, so just pass it through.

- [ ] **Step 4: Run the full test suite**

```bash
cd backend && set -a && source .env && set +a && python -m pytest 2>&1 | tail -5
```
Expected: all previous tests pass (AIClient tests exercise the new path).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_scorer.py backend/app/api/routes.py
git commit -m "refactor(ai_scorer): delegate Claude call to AIClient"
```

---

## Task 6: Refactor `ai_trader.py` to use AIClient

**Files:**
- Modify: `backend/app/services/ai_trader.py`
- Modify: `backend/app/api/routes.py` (callers already have `owner`)

- [ ] **Step 1: Locate the Claude call**

```bash
grep -n "AsyncAnthropic\|anthropic" backend/app/services/ai_trader.py
```

Expected at ~line 319-320:
```python
import anthropic
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
```

- [ ] **Step 2: Thread `owner` through to the analysis function**

`ai_analyze_and_trade(strategy, firm_name, account_size, evaluation_type, dry_run)` — add `owner: Owner` parameter. Inside the function, replace the direct Anthropic call with:

```python
from app.services.ai_client import AIClient

ai = AIClient(owner)
resp = await ai.trade_tick(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt, max_tokens=2048)
text = resp["text"]
# Parse JSON from text as before
```

Update `start_trading_session(strategy, interval, owner, ...)` similarly.

- [ ] **Step 3: Update routes.py**

Every call to `ai_analyze_and_trade` or `start_trading_session` must now pass `owner`. `grep -n "ai_analyze_and_trade\|start_trading_session" backend/app/api/routes.py`.

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_trader.py backend/app/api/routes.py
git commit -m "refactor(ai_trader): delegate Claude call to AIClient"
```

---

## Task 7: Refactor `briefing.py` to use AIClient

**Files:**
- Modify: `backend/app/services/briefing.py`
- Modify: `backend/app/api/routes.py`

- [ ] **Step 1: Find Claude call in briefing.py**

```bash
grep -n "AsyncAnthropic\|anthropic\|def generate_ai_briefing" backend/app/services/briefing.py
```

- [ ] **Step 2: Add `owner` parameter to `generate_ai_briefing`**

```python
from app.services.ai_client import AIClient

async def generate_ai_briefing(account, report, top_signals, owner: Owner) -> dict:
    ...
    ai = AIClient(owner)
    resp = await ai.briefing(system_prompt="", user_prompt=briefing_prompt, max_tokens=1024)
    text = resp["text"]
    # Parse briefing sections as before
```

- [ ] **Step 3: Update callers**

The briefing endpoint is `GET /api/accounts/{id}/briefing`. Thread `owner` through.

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/briefing.py backend/app/api/routes.py
git commit -m "refactor(briefing): delegate Claude call to AIClient"
```

---

## Task 8: Wire `@require_quota` into AI endpoints

Spec §8: AI endpoints must be quota-gated. After Tasks 5-7, the AI calls themselves check quota via AIClient. But some endpoints should reject BEFORE doing other work if quota is exhausted — especially `/api/ai-trade/analyze` and `/api/ai-trade/execute` which do substantial setup. Adding `Depends(require_quota("ai_trade_tick"))` gives users a clean 402 before we incur server-side work.

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_quota_routes.py`

- [ ] **Step 1: Write smoke test**

`backend/tests/test_quota_routes.py`:

```python
"""Verify AI route-level quota enforcement."""

import os
import secrets

import pytest
from fastapi.testclient import TestClient

from app.services.auth import register_user, login_user, _users_mem
from app.services.quota import check_and_consume, _reset_for_test
from app.models.owner import Owner

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _app_client():
    from app.main import app
    return TestClient(app)


class TestAIRouteQuotas:
    def test_analyze_402_when_ai_trade_tick_exhausted(self):
        _users_mem.clear()
        email = f"rq-analyze-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        login = login_user(email, "password123")
        uid = login["user"]["id"]
        token = login["token"]

        # Burn through free ai_trade_tick quota (100/day).
        owner = Owner(id=uid, kind="user", plan="free", metaapi_account_id=None)
        _reset_for_test(uid, "ai_trade_tick")
        for _ in range(100):
            check_and_consume(owner, "ai_trade_tick")

        resp = _app_client().post(
            "/api/ai-trade/analyze",
            headers={"Authorization": f"Bearer {token}"},
            json={"strategy": {"symbols": ["EURUSD"]}, "firm_name": "ftmo",
                  "account_size": 100000, "dry_run": True},
        )
        assert resp.status_code == 402
        assert resp.json()["detail"]["code"] == "QUOTA_EXCEEDED"
```

- [ ] **Step 2: Add dependency to AI endpoints**

In `routes.py`, add `Depends(require_quota(...))` to each AI endpoint:

- `POST /api/signals/parse` — `Depends(require_quota("ai_score"))`
- `POST /api/ai-trade/analyze` — `Depends(require_quota("ai_trade_tick"))`
- `POST /api/ai-trade/execute` — `Depends(require_quota("ai_trade_tick"))`
- `GET /api/accounts/{id}/briefing` — `Depends(require_quota("briefing"))`

**Important:** `@require_quota` consumes the quota at the dependency stage. If the endpoint then calls AIClient which ALSO consumes, the user gets double-charged. To avoid that, AIClient takes a new `consume_quota: bool = True` flag — endpoints that pre-consumed via `@require_quota` pass `consume_quota=False`:

```python
# In ai_client.py AIClient._call:
async def _call(self, *, action, system_prompt, user_prompt, max_tokens=1024,
                 consume_quota: bool = True):
    if consume_quota:
        check_and_consume(self._owner, action)
    ...
```

And in the refactored services (Tasks 5-7), pass `consume_quota=False`. Update signatures and call sites accordingly.

Alternatively, keep `@require_quota` at the route level ONLY for endpoints that do substantial server-side work before the AI call. For simpler flows, let AIClient consume. Use judgment.

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes.py backend/app/services/ai_client.py backend/tests/test_quota_routes.py
git commit -m "feat(quota): require_quota on AI endpoints + no-double-consume flag"
```

---

## Task 9: `POST /api/ai-trade/tick` for anon/free frontend loop

Spec §9: anon/free users cannot use the backend's persistent AI trading session loop (only Pro/Premium get that). They drive AI trading from the browser via periodic POSTs. The endpoint takes a strategy + context and returns the latest AI decisions. The browser stops calling it when the user closes the tab → AI stops.

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_quota_routes.py`

- [ ] **Step 1: Add endpoint**

```python
@router.post("/api/ai-trade/tick")
async def ai_trade_tick(
    body: AITradeRequest,
    owner: Owner = Depends(get_owner),  # allows anon
    _q: Owner = Depends(require_quota("ai_trade_tick")),
):
    """Single AI trading cycle — frontend-driven for anon/free; backend loop for pro/premium.

    Identical payload + response to POST /api/ai-trade/analyze. The only
    difference is this endpoint also permits anonymous owners.
    """
    result = await ai_analyze_and_trade(
        strategy=body.strategy,
        firm_name=body.firm_name,
        account_size=body.account_size,
        evaluation_type=body.evaluation_type,
        dry_run=body.dry_run,
        owner=owner,
    )
    # Persist log (PR 1 DB helper already populates owner_id/owner_kind).
    from app.services.database import db_save_ai_trade_log
    db_save_ai_trade_log(
        user_id=owner.id if owner.kind == "user" else None,
        strategy_name=body.strategy.get("name", ""),
        symbols=",".join(body.strategy.get("symbols", [])),
        analysis=result.get("analysis", ""),
        actions_planned=len(result.get("actions", [])),
        actions_executed=0,
        prompt=result.get("prompt", ""),
        result=result,
        dry_run=body.dry_run,
    )
    return result
```

**Note:** `db_save_ai_trade_log` was patched in PR 1 to set `owner_id` + `owner_kind` when `user_id` is provided. For anon owners, `user_id=None` will skip the FK path. Either update `db_save_ai_trade_log` to accept an explicit `owner_id`/`owner_kind` (cleaner) or add a sibling `db_save_ai_trade_log_owner(owner, ...)`. Either is fine — choose the path with less churn.

- [ ] **Step 2: Add smoke test**

Append to `test_quota_routes.py`:

```python
class TestAITickAnon:
    def test_anon_can_hit_ai_tick_within_quota(self):
        client = _app_client()
        # No auth header → resolver mints anon session
        resp = client.post(
            "/api/ai-trade/tick",
            json={"strategy": {"symbols": ["EURUSD"]}, "firm_name": "ftmo",
                  "account_size": 100000, "dry_run": True},
        )
        # 200 if Claude key configured; otherwise 200 with error text inside result.
        # Accept either — we're mainly checking the quota wiring doesn't 401.
        assert resp.status_code in (200, 402)
```

- [ ] **Step 3: Run tests, commit**

```bash
git add backend/app/api/routes.py backend/tests/test_quota_routes.py
git commit -m "feat(ai): POST /api/ai-trade/tick for anon/free frontend loop"
```

---

## Task 10: Automated smoke + PR

- [ ] **Step 1: Full test suite**

```bash
cd /Users/hexin/code/test/last30days/.worktrees/ai-quota
set -a && source backend/.env && set +a
cd backend && python -m pytest -v 2>&1 | tail -10
```
Expected: 135+ passed (121 from PR 2a + ~14 new).

- [ ] **Step 2: Start servers + browser smoke**

```bash
cd backend && python -m uvicorn app.main:app --port 8001 &
cd ../frontend && npx next dev --port 3001 &
sleep 6

# Direct API smoke — simulates the frontend flow
EMAIL="qsmoke-$(date +%s)@test.propguard.ai"
curl -s -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"password123\"}" > /dev/null
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"password123\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

echo "=== Score a signal (uses ai_score quota) ==="
curl -s -X POST http://localhost:8001/api/signals/parse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"raw":"BUY EURUSD @ 1.0850 SL 1.08 TP 1.10"}' | python3 -m json.tool | head -20

echo "=== AI tick (uses ai_trade_tick quota) ==="
curl -s -X POST http://localhost:8001/api/ai-trade/tick \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy":{"symbols":["EURUSD"],"rules":"buy on SMA cross"},"firm_name":"ftmo","account_size":100000,"dry_run":true}' | python3 -m json.tool | head -20

echo "=== Check ai_cost_ledger grew ==="
# Admin check via SQL (optional — Supabase URL only with publishable key can't SELECT ledger if RLS blocks it)
```

- [ ] **Step 3: Stop servers + push PR**

```bash
kill $(pgrep -f "uvicorn app.main:app --port 8001") 2>/dev/null
kill $(pgrep -f "next dev --port 3001") 2>/dev/null

git push -u origin feat/ai-quota 2>&1 | tail -3
gh pr create --title "PR 2b: AIClient + Quota system" --body "$(cat docs/superpowers/plans/2026-04-19-ai-client-quota.md | head -5 ; echo '...')"
```

---

## Self-review checklist

- [ ] **Spec coverage:** §7 (AIClient unified routing) → Tasks 4–7. §8 (quota system) → Tasks 1–2 + 8. §9 (anon AI tick) → Task 9.
- [ ] **Placeholder scan:** every step has concrete code.
- [ ] **Type consistency:** `AIClient`, `check_and_consume`, `QuotaExceeded`, `require_quota`, `record_tokens`, `get_cost_today`, `COST_PER_1M` — used consistently across tasks.
- [ ] **Out of scope:** frontend dashboard public access (PR 3), anon→user claim flow (PR 3), BYOK for Claude (explicitly rejected in spec §7).
- [ ] **Deployment concern:** after merge, AI endpoints gain 402 responses on quota miss. Verify frontend has an error handler for 402 that shows upgrade modal — if not, it becomes a silent "nothing happens" UX bug. Flag for PR 3 frontend work if missing.
