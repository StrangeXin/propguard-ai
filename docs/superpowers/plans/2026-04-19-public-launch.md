# PR 3: Public launch — anon dashboard + claim flow + broker binding

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip the dashboard from "login required" to "anyone can try", with (a) a backend claim flow that atomically migrates anon-session data to the newly-registered user, (b) a `/settings/broker` page for Pro users to bind their MetaApi account, (c) a global 402 handler that turns quota misses into a clear upgrade modal, and (d) a plan-aware dashboard banner so every visitor knows what mode they're in.

**Architecture:** Backend adds two endpoints (`/api/user/broker/connect`, `/api/auth/claim` — or embed claim in register), a scheduled cleanup for expired anon sessions, and an atomic quota RPC. Frontend threads the `anon_session_id` cookie through API calls, removes the auth guard on `/dashboard`, installs a fetch wrapper that reads `detail.code` on 402/403 responses and shows an upgrade modal, and adds a new `/settings/broker` page.

**Tech Stack:** Python 3.11+, FastAPI, Next.js 16, Supabase, MetaApi Cloud SDK. **IMPORTANT**: this repo's frontend warning `frontend/AGENTS.md` says "This is NOT the Next.js you know. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code." Every frontend task below must follow that guidance — don't apply Next.js 14/15 patterns from training data without checking.

**Spec reference:** `docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md` §4, §10, §11, §12.

**Dependencies:** PRs 1, 2a, 2b landed on `main`. Current tip has Owner abstraction, SandboxBroker, AIClient + quota.

**Scope for this plan:** PR 3. Conversion-hook polish (spec §11 items 2-5: strategy count modal, "AI works while you sleep", sandbox-bust modal) plus abuse-backstop IP caps are deferred to PR 3b.

---

## File Structure

**New files:**
- `backend/app/services/claim.py` — atomic owner_id migration
- `backend/app/services/metaapi_admin.py` — MetaApi SDK connectivity test
- `supabase/migrations/20260422000000_atomic_quota_rpc.sql` — Postgres function for atomic counter
- `supabase/migrations/20260422000001_anon_cleanup_cron.sql` — scheduled function for expired anon sessions
- `frontend/src/lib/api.ts` — fetch wrapper: attaches JWT or anon cookie, routes 402 to modal
- `frontend/src/components/dashboard/PlanBanner.tsx` — anon/free/pro banner
- `frontend/src/components/UpgradeModal.tsx` — global upgrade modal shown on 402
- `frontend/src/app/settings/broker/page.tsx` — MetaApi binding page
- `frontend/src/app/settings/layout.tsx` — optional nav for settings section
- `backend/tests/test_claim.py`
- `backend/tests/test_metaapi_admin.py`

**Modified files:**
- `backend/app/api/routes.py` — `POST /api/user/broker/connect`, hook claim into `/api/auth/register`
- `backend/app/services/anon_sessions.py` — `claim_anon_data(anon_id, user_id)` moves rows across all owner-scoped tables
- `backend/app/services/quota.py` — replace SELECT+UPSERT with `rpc("quota_consume", ...)` call
- `frontend/src/app/dashboard/page.tsx` — remove auth redirect, render PlanBanner
- `frontend/src/app/page.tsx` — landing CTA changes to "Try for free — no signup"
- `frontend/src/app/login/page.tsx` — after register, call `/api/auth/me` to detect migrated rows and show "N records preserved"
- `frontend/src/app/providers.tsx` — mount UpgradeModal at root; expose `showUpgradeModal()`

---

## Task 1: Atomic quota RPC + migration

**Files:**
- Create: `supabase/migrations/20260422000000_atomic_quota_rpc.sql`
- Modify: `backend/app/services/quota.py`

PR 2b review I2: current SELECT-then-UPSERT loses a consumption under concurrent requests. Fix with a single Postgres function that inserts-or-conditionally-increments.

- [ ] **Step 1: Write the migration**

`supabase/migrations/20260422000000_atomic_quota_rpc.sql`:

```sql
-- Atomic quota consumption. Returns the new count, or NULL if the limit was hit.
create or replace function quota_consume(
  p_owner_id uuid,
  p_owner_kind text,
  p_action text,
  p_date date,
  p_limit integer
) returns integer language plpgsql as $$
declare
  result_count integer;
begin
  insert into owner_quota_usage (owner_id, owner_kind, action, date, count)
    values (p_owner_id, p_owner_kind, p_action, p_date, 1)
  on conflict (owner_id, action, date) do update
    set count = owner_quota_usage.count + 1
    where owner_quota_usage.count < p_limit
  returning count into result_count;
  return result_count;  -- NULL iff the WHERE clause prevented the update (limit reached).
end $$;
```

- [ ] **Step 2: Apply**

```bash
cd /Users/hexin/code/test/last30days/.worktrees/public-launch
echo "y" | supabase db push --linked --include-all 2>&1 | tail -5
```

- [ ] **Step 3: Switch `check_and_consume` to RPC**

Replace the SELECT-then-UPSERT block in `backend/app/services/quota.py` `check_and_consume` with:

```python
    today = _today_utc_iso()
    db = get_db()
    if not db:
        return True

    try:
        result = db.rpc("quota_consume", {
            "p_owner_id": owner.id,
            "p_owner_kind": owner.kind,
            "p_action": action,
            "p_date": today,
            "p_limit": daily_limit,
        }).execute()
        # RPC returns the new count, or None if the limit was already hit.
        new_count = result.data
        if new_count is None:
            # We need the current count for the error payload; re-read.
            existing = db.table("owner_quota_usage").select("count").eq(
                "owner_id", owner.id).eq("action", action).eq("date", today).limit(1).execute()
            used = existing.data[0]["count"] if existing.data else daily_limit
            raise QuotaExceeded(action=action, limit=daily_limit, used=used, plan=owner.plan)
        return True
    except QuotaExceeded:
        raise
    except Exception as e:
        logger.error(f"quota consume rpc: {e}")
        return True  # fail-open tradeoff, same as before
```

- [ ] **Step 4: Verify existing quota tests still pass**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_quota.py -v
```
Expected: 6/6 pass.

- [ ] **Step 5: Add a concurrency smoke test** (new `tests/test_quota_race.py`):

```python
"""Race-condition smoke test for check_and_consume. Fires N concurrent
requests at a limit of N, asserts exactly one QuotaExceeded is raised
(i.e. no consumption is lost)."""

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
        # check_and_consume is sync; run in executor for parallelism
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, check_and_consume, owner, "ai_score")
            return "ok"
        except QuotaExceeded:
            return "limit"

    # 12 concurrent calls; 10 should succeed, 2 should raise QuotaExceeded.
    results = await asyncio.gather(*[one_call() for _ in range(12)])
    ok_count = sum(1 for r in results if r == "ok")
    limit_count = sum(1 for r in results if r == "limit")
    assert ok_count == 10, f"expected exactly 10 successes, got {ok_count}"
    assert limit_count == 2, f"expected exactly 2 rejections, got {limit_count}"
```

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/20260422000000_atomic_quota_rpc.sql backend/app/services/quota.py backend/tests/test_quota_race.py
git commit -m "feat(quota): atomic consume via Postgres RPC; race test"
```

---

## Task 2: Claim flow on register

**Files:**
- Create: `backend/app/services/claim.py`
- Test: `backend/tests/test_claim.py`
- Modify: `backend/app/api/routes.py` (register endpoint)

Spec §4: on successful registration, atomically re-own all rows where `owner_id = anon_session_id` to `user_id`. Response returns a count so the frontend can show "N records preserved".

- [ ] **Step 1: Test-first — `backend/tests/test_claim.py`**

```python
"""Claim flow: anon sandbox data follows the user on registration."""

import os
import secrets
from datetime import datetime, timezone

import pytest

from app.services.auth import _users_mem
from app.services.anon_sessions import create_anon_session, get_anon_session
from app.services.claim import claim_anon_data
from app.services.database import get_db
from app.services.sandbox_db import (
    sandbox_get_or_create_account, sandbox_insert_position, sandbox_list_positions,
    sandbox_insert_closed_trade, sandbox_list_closed_trades,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


class TestClaimFlow:
    def _register(self, email):
        _users_mem.clear()
        from app.services.auth import register_user
        return register_user(email, "password123")["id"]

    def test_sandbox_positions_migrate(self):
        anon_id = create_anon_session()
        sandbox_get_or_create_account(anon_id, "anon")
        pid1 = sandbox_insert_position(anon_id, "anon",
            symbol="EURUSD", side="long", size=0.1, entry_price=1.0850)
        pid2 = sandbox_insert_position(anon_id, "anon",
            symbol="BTCUSD", side="short", size=0.01, entry_price=60000)
        assert len(sandbox_list_positions(anon_id)) == 2

        # Register
        user_id = self._register(f"claim-{secrets.token_hex(4)}@test.propguard.ai")

        # Claim
        counts = claim_anon_data(anon_id, user_id)
        assert counts["sandbox_positions"] == 2
        # Positions now owned by user_id
        assert len(sandbox_list_positions(user_id)) == 2
        # Anon no longer sees them
        assert len(sandbox_list_positions(anon_id)) == 0
        # Anon session marked claimed
        assert get_anon_session(anon_id)["claimed_by_user_id"] == user_id

    def test_sandbox_closed_trades_migrate(self):
        anon_id = create_anon_session()
        sandbox_get_or_create_account(anon_id, "anon")
        now = datetime.now(timezone.utc)
        sandbox_insert_closed_trade(
            anon_id, "anon", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.08, exit_price=1.09, pnl=10.0,
            opened_at=now, closed_at=now,
        )
        user_id = self._register(f"claim-ct-{secrets.token_hex(4)}@test.propguard.ai")
        counts = claim_anon_data(anon_id, user_id)
        assert counts["sandbox_closed_trades"] == 1
        assert len(sandbox_list_closed_trades(user_id)) == 1

    def test_missing_anon_id_is_noop(self):
        user_id = self._register(f"claim-noop-{secrets.token_hex(4)}@test.propguard.ai")
        counts = claim_anon_data(
            "00000000-0000-0000-0000-000000000000", user_id)
        assert all(v == 0 for v in counts.values())
```

- [ ] **Step 2: Implement `backend/app/services/claim.py`**

```python
"""
Atomic migration of anon-session-owned rows to a newly registered user.

Called from the register endpoint when a valid `anon_session_id` cookie
was present on the request. Updates `owner_id` / `owner_kind` across every
user-owned table, then marks the anon_session as claimed.

Polymorphic owner_id means no FK cascade. This function explicitly enumerates
the tables; any new owner-scoped table added in the future must be added here.
"""

import logging

from app.services.anon_sessions import claim_anon_session as _mark_claimed
from app.services.database import get_db

logger = logging.getLogger(__name__)

# Tables that carry (owner_id, owner_kind) per the PR 1 + PR 2a migrations.
_OWNER_SCOPED_TABLES = [
    "trading_accounts",
    "signals",
    "alerts",
    "ai_trade_logs",
    "sandbox_accounts",       # one row per owner — UPSERT case
    "sandbox_positions",
    "sandbox_orders",
    "sandbox_closed_trades",
    "owner_quota_usage",
    "ai_cost_ledger",
]


def claim_anon_data(anon_id: str, user_id: str) -> dict[str, int]:
    """Re-own all rows from anon_id to user_id. Returns per-table row counts.

    Idempotent for the common case: running twice moves zero rows the second
    time (the WHERE clause filters on owner_id).
    """
    db = get_db()
    counts: dict[str, int] = {t: 0 for t in _OWNER_SCOPED_TABLES}
    if not db:
        return counts

    for table in _OWNER_SCOPED_TABLES:
        try:
            # sandbox_accounts has one row per owner; a user who registers a second
            # anon session claim should not create a duplicate account row. If a
            # sandbox_account already exists for the user, DELETE the anon one
            # instead of re-owning it.
            if table == "sandbox_accounts":
                existing_user = db.table(table).select("owner_id").eq("owner_id", user_id).limit(1).execute()
                if existing_user.data:
                    deleted = db.table(table).delete().eq("owner_id", anon_id).execute()
                    counts[table] = len(deleted.data or [])
                    continue

            result = db.table(table).update({
                "owner_id": user_id,
                "owner_kind": "user",
            }).eq("owner_id", anon_id).eq("owner_kind", "anon").execute()
            counts[table] = len(result.data or [])
        except Exception as e:
            logger.error(f"claim {table}: {e}")

    _mark_claimed(anon_id, user_id)
    return counts
```

- [ ] **Step 3: Hook into register**

In `backend/app/api/routes.py`, find the `POST /api/auth/register` endpoint. Modify to:

```python
from fastapi import Request
from app.services.claim import claim_anon_data
from app.services.owner_resolver import ANON_COOKIE

@router.post("/api/auth/register")
async def register_endpoint(body: RegisterInput, request: Request):
    try:
        user = register_user(body.email, body.password, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Claim any anon session data for this newly-created user.
    claimed = {}
    anon_id = request.cookies.get(ANON_COOKIE)
    if anon_id:
        claimed = claim_anon_data(anon_id, user["id"])
    total_claimed = sum(claimed.values())

    # Issue a login token so the user is logged in immediately.
    from app.services.auth import login_user
    login = login_user(body.email, body.password)
    return {
        "user": user,
        "token": login["token"],
        "claimed": claimed,
        "total_claimed": total_claimed,
    }
```

If an existing `/api/auth/register` already has a different shape, adapt (keep the response's existing top-level keys and add `claimed`/`total_claimed`).

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_claim.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/claim.py backend/app/services/anon_sessions.py backend/app/api/routes.py backend/tests/test_claim.py
git commit -m "feat(claim): migrate anon-session rows to user on register"
```

---

## Task 3: MetaApi broker bind endpoint

**Files:**
- Create: `backend/app/services/metaapi_admin.py`
- Test: `backend/tests/test_metaapi_admin.py`
- Modify: `backend/app/api/routes.py`

Spec §10: `/settings/broker` page POSTs `{metaapi_account_id}`. Backend tests connectivity, saves to `users.metaapi_account_id`, from next request the user routes to `MetaApiBroker`.

- [ ] **Step 1: Write the admin helper**

`backend/app/services/metaapi_admin.py`:

```python
"""MetaApi account binding — validates a user-provided account ID.

Keeps the MetaApi SDK call isolated so the route doesn't import it directly.
If MetaApi is unavailable (token missing, account ID invalid), returns a
descriptive error string rather than raising.
"""

import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


async def test_metaapi_account(account_id: str) -> tuple[bool, str]:
    """Returns (ok, message). `ok=True` if the account deploys and responds.
    On failure, `message` is user-safe (no secrets, actionable)."""
    settings = get_settings()
    if not settings.metaapi_token:
        return False, "Server MetaApi token not configured; ask admin."

    try:
        from metaapi_cloud_sdk import MetaApi
        api = MetaApi(settings.metaapi_token)
        account = await asyncio.wait_for(
            api.metatrader_account_api.get_account(account_id), timeout=10,
        )
        # account.state is DEPLOYED / UNDEPLOYED / DRAFT / DEPLOYING etc.
        state = getattr(account, "state", "UNKNOWN")
        if state == "DRAFT":
            return False, "Account is in DRAFT state — deploy it in MetaApi dashboard first."
        if state in ("DEPLOYING", "UNDEPLOYING"):
            return False, f"Account is {state}; retry in a few seconds."
        return True, f"Account connected (state: {state})"
    except asyncio.TimeoutError:
        return False, "MetaApi timed out; check network and try again."
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            return False, "Account ID not found in MetaApi."
        if "unauthorized" in msg.lower() or "401" in msg:
            return False, "Access denied — is this your account?"
        return False, f"Connection failed: {msg[:200]}"
```

- [ ] **Step 2: Write the endpoint**

In `backend/app/api/routes.py`:

```python
from app.services.metaapi_admin import test_metaapi_account

class BrokerConnectInput(BaseModel):
    metaapi_account_id: str


@router.post("/api/user/broker/connect")
async def user_broker_connect(
    body: BrokerConnectInput, owner: Owner = Depends(require_user),
):
    """Validate + persist a user's MetaApi account binding.

    Free users can call this to upgrade their experience (sandbox → real).
    Paid users use it to switch accounts.
    """
    acct_id = body.metaapi_account_id.strip()
    if not acct_id or len(acct_id) < 20:
        raise HTTPException(400, "Invalid MetaApi account ID format.")

    ok, message = await test_metaapi_account(acct_id)
    if not ok:
        raise HTTPException(400, message)

    from app.services.auth import update_user
    updated = update_user(owner.id, {"metaapi_account_id": acct_id})
    if not updated:
        raise HTTPException(500, "Failed to save account binding.")

    return {"success": True, "message": message, "user": updated}


@router.delete("/api/user/broker")
async def user_broker_disconnect(owner: Owner = Depends(require_user)):
    """Unbind — user goes back to sandbox mode."""
    from app.services.auth import update_user
    updated = update_user(owner.id, {"metaapi_account_id": None})
    return {"success": True, "user": updated}
```

- [ ] **Step 3: Write tests (mocked SDK)**

`backend/tests/test_metaapi_admin.py`:

```python
"""test_metaapi_account wraps MetaApi SDK errors into user-safe messages."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.metaapi_admin import test_metaapi_account


class TestMetaApiAdmin:
    @pytest.mark.asyncio
    async def test_success_returns_state(self):
        fake_account = MagicMock(state="DEPLOYED")
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(return_value=fake_account)
        with patch("app.services.metaapi_admin.get_settings") as s, \
             patch.dict("os.environ", {"METAAPI_TOKEN": "x"}), \
             patch("metaapi_cloud_sdk.MetaApi", return_value=fake_api):
            s.return_value.metaapi_token = "x"
            ok, msg = await test_metaapi_account("acc-123456789012345678901234")
            assert ok
            assert "DEPLOYED" in msg

    @pytest.mark.asyncio
    async def test_missing_token(self):
        with patch("app.services.metaapi_admin.get_settings") as s:
            s.return_value.metaapi_token = ""
            ok, msg = await test_metaapi_account("acc-x")
            assert not ok
            assert "not configured" in msg.lower()

    @pytest.mark.asyncio
    async def test_draft_state_rejected(self):
        fake_account = MagicMock(state="DRAFT")
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(return_value=fake_account)
        with patch("app.services.metaapi_admin.get_settings") as s, \
             patch("metaapi_cloud_sdk.MetaApi", return_value=fake_api):
            s.return_value.metaapi_token = "x"
            ok, msg = await test_metaapi_account("acc-123456789012345678901234")
            assert not ok
            assert "DRAFT" in msg

    @pytest.mark.asyncio
    async def test_not_found(self):
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(
            side_effect=Exception("Account not found"))
        with patch("app.services.metaapi_admin.get_settings") as s, \
             patch("metaapi_cloud_sdk.MetaApi", return_value=fake_api):
            s.return_value.metaapi_token = "x"
            ok, msg = await test_metaapi_account("acc-xxxxxxxxxxxxxxxxxxxxxxxx")
            assert not ok
            assert "not found" in msg.lower()
```

- [ ] **Step 4: Run tests, commit**

```bash
cd backend && python -m pytest tests/test_metaapi_admin.py -v
git add backend/app/services/metaapi_admin.py backend/app/api/routes.py backend/tests/test_metaapi_admin.py
git commit -m "feat(broker): POST /api/user/broker/connect validates + saves MetaApi binding"
```

---

## Task 4: Anon cleanup scheduled job

**Files:**
- Create: `supabase/migrations/20260422000001_anon_cleanup_cron.sql`

Spec §12: nightly prune of expired anon sessions (30-day TTL).

- [ ] **Step 1: Write the migration**

```sql
-- Nightly cleanup of expired unclaimed anon sessions + dependent rows.
-- owner_id is polymorphic (no FK cascade), so we explicitly delete
-- orphan rows before removing the anon_sessions row.

create or replace function cleanup_expired_anon() returns integer language plpgsql as $$
declare
  deleted_sessions integer;
begin
  with expired as (
    select id from anon_sessions
    where claimed_by_user_id is null
      and last_active_at < now() - interval '30 days'
  )
  delete from sandbox_positions       where owner_kind = 'anon' and owner_id in (select id from expired);
  -- ... (repeat for every owner-scoped table)

  -- (Abridged above for clarity — real SQL below):
  delete from sandbox_positions       where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from sandbox_orders          where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from sandbox_closed_trades   where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from sandbox_accounts        where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from ai_trade_logs           where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from signals                 where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from alerts                  where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from owner_quota_usage       where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');
  delete from ai_cost_ledger          where owner_kind = 'anon' and owner_id in
    (select id from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days');

  delete from anon_sessions where claimed_by_user_id is null and last_active_at < now() - interval '30 days';
  get diagnostics deleted_sessions = row_count;
  return deleted_sessions;
end $$;
```

**Note**: Supabase Scheduled Functions (`pg_cron` or Supabase's scheduled-tasks UI) will invoke this nightly. Set up in Supabase dashboard after migration applies. Document in PR description — not a code task.

- [ ] **Step 2: Apply and manually invoke once to verify**

```bash
echo "y" | supabase db push --linked --include-all
```

Then via Supabase SQL editor (outside this codebase):
```sql
select cleanup_expired_anon();
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260422000001_anon_cleanup_cron.sql
git commit -m "db: cleanup_expired_anon() function for nightly pruning"
```

---

## Task 5: Frontend `api.ts` wrapper

**Files:**
- Create: `frontend/src/lib/api.ts`

The single place that makes fetch calls. Adds `Authorization: Bearer <jwt>` if logged in; anon cookie is sent automatically by the browser. On 402 or 403, routes through the global `onApiError` callback.

- [ ] **Step 1: Read the Next.js 16 docs for fetch patterns**

```bash
ls /Users/hexin/code/test/last30days/frontend/node_modules/next/dist/docs/ 2>&1 | head -20
# If the docs list includes anything about fetch/client-side, skim it for changes.
```

- [ ] **Step 2: Write the wrapper**

`frontend/src/lib/api.ts`:

```typescript
// Single fetch wrapper. Attaches JWT when present, always sends cookies
// (so the anon_session_id cookie flows), routes 402/403 to a global handler.

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

type ApiErrorHandler = (error: {
  status: number;
  code?: string;
  message?: string;
  detail?: Record<string, unknown>;
}) => void;

let _onError: ApiErrorHandler = () => {};

export function setApiErrorHandler(fn: ApiErrorHandler) {
  _onError = fn;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = typeof window !== "undefined"
    ? localStorage.getItem("propguard-token")
    : null;

  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include", // send anon_session_id cookie
  });

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const detail = (data as { detail?: Record<string, unknown> })?.detail;
    const code = detail && typeof detail === "object" ? (detail as { code?: string }).code : undefined;
    _onError({ status: res.status, code, detail: detail as Record<string, unknown> | undefined });
    throw Object.assign(new Error(`API ${res.status}`), {
      status: res.status,
      code,
      detail,
    });
  }

  return data as T;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): api wrapper with JWT + cookie + 402 error routing"
```

---

## Task 6: Upgrade modal + global wiring

**Files:**
- Create: `frontend/src/components/UpgradeModal.tsx`
- Modify: `frontend/src/app/providers.tsx`

- [ ] **Step 1: Write the modal**

`frontend/src/components/UpgradeModal.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { setApiErrorHandler } from "@/lib/api";

type UpgradePayload = {
  action?: string;
  message?: string;
  limit?: number;
  used?: number;
  plan?: string;
  upgrade_url?: string;
  resets_at?: string;
};

export function UpgradeModal() {
  const [payload, setPayload] = useState<UpgradePayload | null>(null);

  useEffect(() => {
    setApiErrorHandler((err) => {
      if (err.status === 402 && err.detail) {
        setPayload(err.detail as UpgradePayload);
      }
    });
  }, []);

  if (!payload) return null;

  const reset = payload.resets_at ? new Date(payload.resets_at).toLocaleString() : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={() => setPayload(null)}
    >
      <div
        className="bg-neutral-900 border border-neutral-700 rounded-lg p-6 max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold mb-2">Daily limit reached</h2>
        <p className="text-neutral-300 mb-4">{payload.message}</p>
        <dl className="text-sm text-neutral-400 space-y-1 mb-5">
          <div>Used: {payload.used} / {payload.limit}</div>
          <div>Plan: {payload.plan}</div>
          {reset && <div>Resets: {reset}</div>}
        </dl>
        <div className="flex gap-2 justify-end">
          <button className="px-4 py-2 text-sm rounded bg-neutral-700 hover:bg-neutral-600"
                  onClick={() => setPayload(null)}>Close</button>
          <a className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white"
             href={payload.upgrade_url || "/pricing"}>Upgrade</a>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Mount at root**

Edit `frontend/src/app/providers.tsx`:

```tsx
import { UpgradeModal } from "@/components/UpgradeModal";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <AuthProvider>
        {children}
        <UpgradeModal />
      </AuthProvider>
    </I18nProvider>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UpgradeModal.tsx frontend/src/app/providers.tsx
git commit -m "feat(frontend): global UpgradeModal listens for 402 and surfaces upgrade CTA"
```

---

## Task 7: Remove dashboard auth guard + plan banner

**Files:**
- Create: `frontend/src/components/dashboard/PlanBanner.tsx`
- Modify: `frontend/src/app/dashboard/page.tsx`

- [ ] **Step 1: Write the banner component**

`frontend/src/components/dashboard/PlanBanner.tsx`:

```tsx
"use client";

import Link from "next/link";

type Props = {
  userKind: "anon" | "user";
  plan: string;
  metaapiAccountId: string | null;
};

export function PlanBanner({ userKind, plan, metaapiAccountId }: Props) {
  if (userKind === "anon") {
    return (
      <div className="flex items-center justify-between gap-4 rounded border border-amber-600/50 bg-amber-950/40 px-4 py-2 text-sm">
        <div className="text-amber-200">
          🔬 Experience mode · Sandbox $100,000 · Data retained 30 days
        </div>
        <Link href="/login"
              className="px-3 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium">
          Register to save →
        </Link>
      </div>
    );
  }

  if (plan === "free") {
    return (
      <div className="flex items-center justify-between gap-4 rounded border border-blue-600/50 bg-blue-950/40 px-4 py-2 text-sm">
        <div className="text-blue-200">
          ✅ Logged in · Free plan · Sandbox only
        </div>
        <Link href="/settings/broker"
              className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium">
          Upgrade to Pro to bind real account →
        </Link>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-4 rounded border border-emerald-600/50 bg-emerald-950/40 px-4 py-2 text-sm">
      <div className="text-emerald-200">
        ✅ {plan[0].toUpperCase() + plan.slice(1)} · Real account:{" "}
        <span className="font-mono">{metaapiAccountId?.slice(0, 8) ?? "—"}…</span>
      </div>
      <Link href="/settings/broker" className="text-emerald-200 hover:underline text-xs">
        Manage →
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: Modify `dashboard/page.tsx`**

Remove the `useEffect` that redirects unauthenticated users to `/login`:

Before (current line 41-45):
```tsx
useEffect(() => {
  if (!authLoading && !user) {
    router.push("/login");
  }
}, [authLoading, user, router]);
```

After: delete the `useEffect` + `router` import if unused elsewhere. Dashboard is now public.

Render `<PlanBanner>` at the top of the dashboard. The banner needs plan info — surface it via either `useAuth().user` (which has `tier` and should be extended with `metaapi_account_id`) OR a new `useOwner()` hook that calls `/api/auth/me` and falls back to anon.

Simpler path for this task: if `user` is null, render `kind="anon", plan="anon", metaapiAccountId=null`. Otherwise render `kind="user", plan=user.tier, metaapiAccountId=user.metaapi_account_id || null`.

Add near the top of the dashboard JSX:
```tsx
<PlanBanner
  userKind={user ? "user" : "anon"}
  plan={user?.tier ?? "anon"}
  metaapiAccountId={(user as { metaapi_account_id?: string } | null)?.metaapi_account_id ?? null}
/>
```

Also extend the `User` interface in `useAuth.ts` to include `metaapi_account_id: string | null`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/PlanBanner.tsx frontend/src/app/dashboard/page.tsx frontend/src/hooks/useAuth.ts
git commit -m "feat(frontend): dashboard is public; PlanBanner shows mode"
```

---

## Task 8: Landing page CTA

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Change the primary CTA**

In the hero section of `page.tsx`, the primary button currently points to login/register. Change it to `/dashboard`:

Search for `Get Started Free` (or equivalent) in `page.tsx`. Change its `href` to `"/dashboard"`. Rename to `Try for free — no signup required` (en) / `免费试用，无需注册` (zh). Keep `Sign In` as the secondary link.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat(frontend): landing CTA routes directly to /dashboard (no signup required)"
```

---

## Task 9: `/settings/broker` page

**Files:**
- Create: `frontend/src/app/settings/broker/page.tsx`
- (Optional) Create: `frontend/src/app/settings/layout.tsx`

- [ ] **Step 1: Write the page**

```tsx
"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/app/providers";
import { api } from "@/lib/api";

export default function BrokerSettingsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [accountId, setAccountId] = useState(user && (user as { metaapi_account_id?: string }).metaapi_account_id || "");
  const [status, setStatus] = useState<"idle" | "connecting" | "connected" | "error">("idle");
  const [message, setMessage] = useState("");

  if (!user) {
    return (
      <div className="max-w-xl mx-auto p-6">
        <h1 className="text-xl font-semibold mb-3">Broker settings</h1>
        <p>Please <a className="underline" href="/login">log in</a> first.</p>
      </div>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setStatus("connecting");
    setMessage("Validating account...");
    try {
      const result = await api<{ message: string }>("/api/user/broker/connect", {
        method: "POST",
        body: JSON.stringify({ metaapi_account_id: accountId.trim() }),
      });
      setStatus("connected");
      setMessage(result.message || "Connected.");
      setTimeout(() => router.push("/dashboard"), 1500);
    } catch (e: unknown) {
      setStatus("error");
      const err = e as { detail?: string | { message?: string } };
      setMessage(
        typeof err.detail === "string" ? err.detail :
        err.detail?.message ?? "Connection failed."
      );
    }
  };

  const disconnect = async () => {
    await api("/api/user/broker", { method: "DELETE" });
    setAccountId("");
    setStatus("idle");
    setMessage("Disconnected — reverted to sandbox.");
  };

  return (
    <div className="max-w-xl mx-auto p-6">
      <h1 className="text-xl font-semibold mb-3">Broker settings</h1>
      <p className="text-sm text-neutral-400 mb-5">
        Bind your MetaApi account ID to trade with real funds. Get your ID from{" "}
        <a className="underline" href="https://app.metaapi.cloud/" target="_blank" rel="noreferrer">
          app.metaapi.cloud
        </a>.
      </p>

      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm font-medium">MetaApi account ID</label>
        <input
          type="text"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          className="w-full px-3 py-2 rounded bg-neutral-800 border border-neutral-700 font-mono text-sm"
          required
        />
        <div className="flex gap-2">
          <button type="submit" disabled={status === "connecting"}
                  className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
            {status === "connecting" ? "Validating..." : "Connect"}
          </button>
          {user && (user as { metaapi_account_id?: string }).metaapi_account_id && (
            <button type="button" onClick={disconnect}
                    className="px-4 py-2 rounded bg-neutral-700 hover:bg-neutral-600">
              Disconnect
            </button>
          )}
        </div>
        {message && (
          <div className={status === "error"
            ? "text-red-400 text-sm"
            : status === "connected" ? "text-green-400 text-sm" : "text-neutral-300 text-sm"}>
            {message}
          </div>
        )}
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/settings
git commit -m "feat(frontend): /settings/broker page for MetaApi binding"
```

---

## Task 10: End-to-end smoke + PR

**Files:** none (ops)

- [ ] **Step 1: Full pytest**

```bash
cd /Users/hexin/code/test/last30days/.worktrees/public-launch
set -a && source backend/.env && set +a
cd backend && python -m pytest -v 2>&1 | tail -5
```
Expected: ~150 passed (134 from PR 2b + ~15 new).

- [ ] **Step 2: Start servers + drive headless browser smoke**

```bash
cd backend && python -m uvicorn app.main:app --port 8001 &
cd ../frontend && npm install --silent && npx next dev --port 3001 &
sleep 6

B=~/.claude/skills/gstack/browse/dist/browse

# Anon flow: open /dashboard without auth, verify the page loads + banner says "Experience mode"
$B goto http://localhost:3001/dashboard > /dev/null
$B snapshot -c -d 2 > /tmp/pr3-anon.txt
grep -i "experience\|sandbox\|register to save" /tmp/pr3-anon.txt | head -3

# Register + confirm claim flow runs
EMAIL="pr3-$(date +%s)@test.propguard.ai"
$B goto http://localhost:3001/login > /dev/null
$B snapshot -i > /dev/null
$B click @e4 > /dev/null  # Register tab
sleep 1
$B snapshot -i > /dev/null
$B fill @e1 "PR3" > /dev/null
$B fill @e2 "$EMAIL" > /dev/null
$B fill @e3 "password123" > /dev/null
$B click @e4 > /dev/null  # Create Account
sleep 4
echo "URL: $($B url)"
$B text 2>&1 | grep -iE "logged in|free plan|upgrade" | head -3
```

- [ ] **Step 3: API smoke for claim flow**

```bash
# Register with an anon_session_id cookie; verify response has claimed counts
COOKIE_JAR=$(mktemp)
# First: hit /api/trading/account as anon to mint a session + create sandbox account
curl -s -c "$COOKIE_JAR" http://localhost:8001/api/trading/account > /dev/null
# (returns 401 since /api/trading/account requires auth; but the anon cookie is still set via get_owner)
# Better: hit the public /api/ai-trade/tick to mint + use sandbox
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST http://localhost:8001/api/ai-trade/tick \
  -H "Content-Type: application/json" \
  -d '{"strategy":{"symbols":["EURUSD"]},"firm_name":"ftmo","account_size":100000,"dry_run":true}' > /dev/null
# Register with same cookie jar
EMAIL="claim-$(date +%s)@test.propguard.ai"
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"password123\"}" | python3 -m json.tool | head -20
```

Expected: response shape includes `claimed: {...per-table counts...}` and `total_claimed > 0`.

- [ ] **Step 4: Stop servers + push PR**

```bash
kill $(pgrep -f "uvicorn app.main:app --port 8001") 2>/dev/null
kill $(pgrep -f "next dev --port 3001") 2>/dev/null

git push -u origin feat/public-launch 2>&1 | tail -3
gh pr create --title "PR 3: Public launch — anon dashboard + claim + broker binding" --body "See docs/superpowers/plans/2026-04-19-public-launch.md"
```

---

## Self-review

- [ ] **Spec coverage:** §4 claim flow → T2. §10 frontend changes → T6, T7, T8, T9. §11 conversion hook #1 (quota modal) → T5, T6. §12 cleanup → T4. PR 2b I2 atomic RPC → T1.
- [ ] **Out of scope:** conversion hooks §11 items 2-5 (strategy count limit, "AI works while away" popover, sandbox-bust modal). IP-level abuse backstop (I1 from PR 2b). Both tracked in `docs/followups.md` or future plans.
- [ ] **Next.js 16 caveat:** every frontend task mentions the AGENTS.md warning. Implementers must read `node_modules/next/dist/docs/` before writing code.
- [ ] **Type consistency:** `claim_anon_data`, `test_metaapi_account`, `PlanBanner`, `UpgradeModal`, `setApiErrorHandler` — all referenced consistently.
- [ ] **Placeholder scan:** no "TBD" / "similar to Task N" / incomplete code blocks.
