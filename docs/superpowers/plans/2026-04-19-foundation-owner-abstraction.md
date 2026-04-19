# Foundation: Owner Abstraction + Schema Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the `Owner` abstraction and supporting database schema so that future PRs can unify anonymous and authenticated code paths. This PR must ship with zero user-visible change — all existing authenticated flows continue to work exactly as before.

**Architecture:** Add four new tables (`anon_sessions`, `plan_quotas`, `owner_quota_usage`, `ai_cost_ledger`) and add `owner_id` + `owner_kind` columns to all user-owned tables. Introduce a typed `Owner` dataclass and a FastAPI dependency `get_owner` that resolves every request to an `Owner` (JWT user, existing anon cookie, or newly minted anon session). Existing auth-required endpoints wrap `get_owner` with a `require_user` guard to preserve current behavior.

**Tech Stack:** Python 3.11+, FastAPI, Supabase (Postgres), PyJWT, pytest, fastapi.testclient.

**Spec reference:** `docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md` §1–4 and §12.

**Scope for this plan:** PR 1 only (Foundation). PRs 2 (Broker/AI abstractions + sandbox) and 3 (public launch) get separate plan documents after this one lands.

---

## File Structure

**New files:**
- `supabase/migrations/20260420000000_owner_abstraction.sql` — all schema changes in one migration
- `backend/app/models/owner.py` — `Owner` dataclass + `OwnerKind`, `PlanTier` literals
- `backend/app/services/anon_sessions.py` — DB functions for `anon_sessions` table
- `backend/app/services/owner_resolver.py` — FastAPI dependency `get_owner` + `require_user` helper
- `backend/tests/test_owner_model.py` — tests for Owner dataclass invariants
- `backend/tests/test_anon_sessions.py` — tests for anon session DB layer
- `backend/tests/test_owner_resolver.py` — FastAPI dependency tests using `TestClient`

**Modified files:**
- `backend/app/services/database.py` — add helpers for reading `users.metaapi_account_id` (new column)
- `backend/app/services/auth.py` — `verify_token` returns user dict already; add a helper `user_dict_to_owner` that maps it to `Owner` (kept thin so the JWT logic stays in `auth.py`)
- `backend/app/api/routes.py` — wire `Depends(require_user)` into existing authenticated endpoints (behavior preserved — they still 401 for non-users)

---

## Task 1: Write the schema migration

**Files:**
- Create: `supabase/migrations/20260420000000_owner_abstraction.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- PropGuard AI — Owner abstraction + anonymous session support
-- Migration: 20260420000000_owner_abstraction
-- Spec: docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md

-- 1. Anonymous session storage
create table if not exists anon_sessions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  last_active_at timestamptz not null default now(),
  claimed_by_user_id uuid references users(id) on delete set null,
  ip_hash text,
  user_agent text
);

create index if not exists idx_anon_sessions_last_active
  on anon_sessions(last_active_at)
  where claimed_by_user_id is null;

-- 2. Plan-level quota configuration (editable without code deploy)
create table if not exists plan_quotas (
  plan text not null check (plan in ('anon','free','pro','premium')),
  action text not null,
  daily_limit integer,           -- null = unlimited
  total_limit integer,           -- null = unlimited; used for 'saved_strategies'
  primary key (plan, action)
);

-- Seed quotas matching spec §8
insert into plan_quotas (plan, action, daily_limit, total_limit) values
  ('anon',    'ai_score',         10,   null),
  ('anon',    'ai_trade_tick',    50,   null),
  ('anon',    'briefing',         1,    null),
  ('anon',    'saved_strategies', null, 3),
  ('anon',    'sandbox_reset',    5,    null),
  ('free',    'ai_score',         20,   null),
  ('free',    'ai_trade_tick',    100,  null),
  ('free',    'briefing',         2,    null),
  ('free',    'saved_strategies', null, 5),
  ('free',    'sandbox_reset',    20,   null),
  ('pro',     'ai_score',         500,  null),
  ('pro',     'ai_trade_tick',    2000, null),
  ('pro',     'briefing',         20,   null),
  ('pro',     'saved_strategies', null, 50),
  ('pro',     'sandbox_reset',    null, null),
  ('premium', 'ai_score',         null, null),
  ('premium', 'ai_trade_tick',    null, null),
  ('premium', 'briefing',         null, null),
  ('premium', 'saved_strategies', null, null),
  ('premium', 'sandbox_reset',    null, null)
on conflict (plan, action) do nothing;

-- 3. Daily counters
create table if not exists owner_quota_usage (
  owner_id uuid not null,
  owner_kind text not null check (owner_kind in ('user','anon')),
  action text not null,
  date date not null,
  count integer not null default 0,
  primary key (owner_id, action, date)
);

create index if not exists idx_owner_quota_usage_date
  on owner_quota_usage(date);

-- 4. AI cost ledger (per-owner token + $ accounting)
create table if not exists ai_cost_ledger (
  id bigserial primary key,
  owner_id uuid not null,
  owner_kind text not null check (owner_kind in ('user','anon')),
  date date not null,
  input_tokens integer not null,
  output_tokens integer not null,
  cost_usd numeric(10,6) not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_ai_cost_owner_date
  on ai_cost_ledger(owner_id, date);

-- 5. Add metaapi_account_id to users (real-account binding; null = sandbox)
alter table users add column if not exists metaapi_account_id text;

-- 6. Add owner_id + owner_kind to user-owned tables
-- Pattern: nullable column + backfill from user_id + set not null
-- (No FK because owner_id is polymorphic across users/anon_sessions)

alter table trading_accounts add column if not exists owner_id uuid;
alter table trading_accounts add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update trading_accounts set owner_id = user_id, owner_kind = 'user'
  where owner_id is null and user_id is not null;
alter table trading_accounts alter column owner_id set not null;
alter table trading_accounts alter column owner_kind set not null;
create index if not exists idx_trading_accounts_owner
  on trading_accounts(owner_id);

alter table signals add column if not exists owner_id uuid;
alter table signals add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update signals set owner_id = user_id, owner_kind = 'user'
  where owner_id is null and user_id is not null;
alter table signals alter column owner_id set not null;
alter table signals alter column owner_kind set not null;
create index if not exists idx_signals_owner
  on signals(owner_id, received_at desc);

alter table alerts add column if not exists owner_id uuid;
alter table alerts add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update alerts set owner_id = user_id, owner_kind = 'user'
  where owner_id is null and user_id is not null;
alter table alerts alter column owner_id set not null;
alter table alerts alter column owner_kind set not null;
create index if not exists idx_alerts_owner
  on alerts(owner_id, created_at desc);

alter table ai_trade_logs add column if not exists owner_id uuid;
alter table ai_trade_logs add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update ai_trade_logs set owner_id = user_id, owner_kind = 'user'
  where owner_id is null and user_id is not null;
alter table ai_trade_logs alter column owner_id set not null;
alter table ai_trade_logs alter column owner_kind set not null;
create index if not exists idx_ai_trade_logs_owner
  on ai_trade_logs(owner_id, created_at desc);

-- NOTE: user_id columns are kept during the deprecation window.
-- A follow-up migration after PR 3 ships will drop them.
```

- [ ] **Step 2: Commit the migration**

```bash
git add supabase/migrations/20260420000000_owner_abstraction.sql
git commit -m "db: add anon_sessions, plan_quotas, owner_quota_usage, ai_cost_ledger + owner_id columns"
```

---

## Task 2: Apply the migration to the development Supabase project

**Files:**
- None (ops step against the dev Supabase project)

- [ ] **Step 1: Push the migration**

Run:
```bash
export SUPABASE_ACCESS_TOKEN=<token-from-1Password>
./scripts/db-migrate.sh push
```
Expected output: `Applied: 20260420000000_owner_abstraction.sql`. If it fails, read the Postgres error — most likely a table the migration expected (`signals`, `ai_trade_logs`, `trading_accounts`, `alerts`) doesn't exist in this environment, in which case the `alter table ... add column if not exists` survives but the `update ... set ... where user_id is not null` no-ops.

- [ ] **Step 2: Verify tables exist**

Run (via Supabase SQL editor or psql):
```sql
select table_name from information_schema.tables
where table_schema = 'public'
  and table_name in ('anon_sessions','plan_quotas','owner_quota_usage','ai_cost_ledger');
```
Expected: 4 rows returned.

- [ ] **Step 3: Verify plan_quotas seed loaded**

Run:
```sql
select count(*) from plan_quotas;
```
Expected: 20 (4 plans × 5 actions).

No commit needed — this step only pushes the migration file from Task 1.

---

## Task 3: Create the `Owner` dataclass

**Files:**
- Create: `backend/app/models/owner.py`
- Test: `backend/tests/test_owner_model.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_owner_model.py
"""Tests for the Owner value object."""

import pytest

from app.models.owner import Owner


class TestOwner:
    def test_user_owner(self):
        o = Owner(id="u-1", kind="user", plan="pro", metaapi_account_id="acct-123")
        assert o.kind == "user"
        assert o.plan == "pro"
        assert o.metaapi_account_id == "acct-123"

    def test_anon_owner(self):
        o = Owner(id="a-1", kind="anon", plan="anon", metaapi_account_id=None)
        assert o.kind == "anon"
        assert o.metaapi_account_id is None

    def test_anon_kind_must_have_anon_plan(self):
        with pytest.raises(ValueError, match="anon owners must have plan='anon'"):
            Owner(id="a-1", kind="anon", plan="pro", metaapi_account_id=None)

    def test_anon_cannot_have_metaapi_binding(self):
        with pytest.raises(ValueError, match="anon owners cannot bind metaapi"):
            Owner(id="a-1", kind="anon", plan="anon", metaapi_account_id="acct-1")

    def test_frozen(self):
        o = Owner(id="u-1", kind="user", plan="free", metaapi_account_id=None)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            o.plan = "pro"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_owner_model.py -v`
Expected: `ModuleNotFoundError: No module named 'app.models.owner'`

- [ ] **Step 3: Implement the Owner dataclass**

```python
# backend/app/models/owner.py
"""
Owner — the single value object flowing through every request.

Replaces raw `user_id` arguments across the service layer. Services read
`owner.plan` and `owner.metaapi_account_id` instead of branching on
authenticated vs. anonymous.
"""

from dataclasses import dataclass
from typing import Literal

OwnerKind = Literal["user", "anon"]
PlanTier = Literal["anon", "free", "pro", "premium"]


@dataclass(frozen=True)
class Owner:
    id: str
    kind: OwnerKind
    plan: PlanTier
    metaapi_account_id: str | None

    def __post_init__(self):
        if self.kind == "anon" and self.plan != "anon":
            raise ValueError("anon owners must have plan='anon'")
        if self.kind == "anon" and self.metaapi_account_id is not None:
            raise ValueError("anon owners cannot bind metaapi accounts")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_owner_model.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/owner.py backend/tests/test_owner_model.py
git commit -m "feat(owner): add Owner value object with invariant checks"
```

---

## Task 4: Anon session DB helpers — `get_anon_session`

**Files:**
- Create: `backend/app/services/anon_sessions.py`
- Test: `backend/tests/test_anon_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_anon_sessions.py
"""
Tests for anon_sessions DB layer.
Requires Supabase dev env (SUPABASE_URL + SUPABASE_KEY in .env).
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_anon_sessions.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.anon_sessions'`

- [ ] **Step 3: Implement create/get**

```python
# backend/app/services/anon_sessions.py
"""
Anon session DB layer — minimal CRUD over the anon_sessions table.
"""

import logging
from datetime import datetime, timezone

from app.services.database import get_db

logger = logging.getLogger(__name__)


def create_anon_session(ip_hash: str | None = None,
                        user_agent: str | None = None) -> str | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("anon_sessions").insert({
            "ip_hash": ip_hash,
            "user_agent": user_agent,
        }).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        logger.error(f"create_anon_session: {e}")
    return None


def get_anon_session(session_id: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("anon_sessions").select("*").eq("id", session_id).limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"get_anon_session: {e}")
    return None


def touch_anon_session(session_id: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("anon_sessions").update({
            "last_active_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.error(f"touch_anon_session: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_anon_sessions.py -v`
Expected: 3 passed (or skipped if no Supabase creds).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/anon_sessions.py backend/tests/test_anon_sessions.py
git commit -m "feat(anon): CRUD helpers for anon_sessions table"
```

---

## Task 5: Anon session DB helpers — `touch_anon_session` test

**Files:**
- Test: `backend/tests/test_anon_sessions.py`

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/test_anon_sessions.py` inside `TestAnonSessions`:

```python
    def test_touch_updates_last_active(self):
        import time
        sid = create_anon_session()
        before = get_anon_session(sid)["last_active_at"]
        time.sleep(1.1)  # ensure timestamp resolution difference
        touch_anon_session(sid)
        after = get_anon_session(sid)["last_active_at"]
        assert after > before
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_anon_sessions.py::TestAnonSessions::test_touch_updates_last_active -v`
Expected: PASS. (Implementation was already written in Task 4; this is an extra verification test.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_anon_sessions.py
git commit -m "test(anon): verify touch updates last_active_at"
```

---

## Task 6: `claim_anon_session` — mark session as claimed

**Files:**
- Modify: `backend/app/services/anon_sessions.py`
- Test: `backend/tests/test_anon_sessions.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_anon_sessions.py` inside `TestAnonSessions`:

```python
    def test_claim_sets_user_id(self):
        sid = create_anon_session()
        fake_user_id = "11111111-1111-1111-1111-111111111111"
        claim_anon_session(sid, fake_user_id)
        row = get_anon_session(sid)
        assert row["claimed_by_user_id"] == fake_user_id
```

And update the import at the top:
```python
from app.services.anon_sessions import (
    create_anon_session,
    get_anon_session,
    touch_anon_session,
    claim_anon_session,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_anon_sessions.py::TestAnonSessions::test_claim_sets_user_id -v`
Expected: `ImportError: cannot import name 'claim_anon_session'`

- [ ] **Step 3: Implement**

Append to `backend/app/services/anon_sessions.py`:

```python
def claim_anon_session(session_id: str, user_id: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("anon_sessions").update({
            "claimed_by_user_id": user_id,
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.error(f"claim_anon_session: {e}")
```

Note: the actual data migration (updating `owner_id` on trades/strategies/etc.) is **NOT** part of this function. That's a separate `claim_anon_data` function added in PR 3 alongside the registration flow. This function only marks the session row.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_anon_sessions.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/anon_sessions.py backend/tests/test_anon_sessions.py
git commit -m "feat(anon): claim_anon_session marks session for user"
```

---

## Task 7: `user_dict_to_owner` helper in auth

**Files:**
- Modify: `backend/app/services/auth.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Append a new class to `backend/tests/test_auth.py`:

```python
class TestUserToOwner:
    def test_free_user_without_metaapi(self):
        from app.services.auth import user_dict_to_owner
        user = {"id": "u-1", "email": "a@b.c", "tier": "free", "metaapi_account_id": None}
        o = user_dict_to_owner(user)
        assert o.id == "u-1"
        assert o.kind == "user"
        assert o.plan == "free"
        assert o.metaapi_account_id is None

    def test_pro_user_with_metaapi(self):
        from app.services.auth import user_dict_to_owner
        user = {"id": "u-2", "tier": "pro", "metaapi_account_id": "acct-xyz"}
        o = user_dict_to_owner(user)
        assert o.plan == "pro"
        assert o.metaapi_account_id == "acct-xyz"

    def test_missing_tier_defaults_free(self):
        from app.services.auth import user_dict_to_owner
        user = {"id": "u-3"}
        o = user_dict_to_owner(user)
        assert o.plan == "free"
        assert o.metaapi_account_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth.py::TestUserToOwner -v`
Expected: `ImportError: cannot import name 'user_dict_to_owner'`

- [ ] **Step 3: Implement**

Append to `backend/app/services/auth.py`:

```python
from app.models.owner import Owner


def user_dict_to_owner(user: dict) -> Owner:
    """Map a user row (from DB or in-memory) to an Owner."""
    return Owner(
        id=user["id"],
        kind="user",
        plan=user.get("tier") or "free",
        metaapi_account_id=user.get("metaapi_account_id"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: all existing tests + 3 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth.py backend/tests/test_auth.py
git commit -m "feat(auth): user_dict_to_owner maps user dicts to Owner"
```

---

## Task 8: `get_owner` resolver — no credentials case

**Files:**
- Create: `backend/app/services/owner_resolver.py`
- Test: `backend/tests/test_owner_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_owner_resolver.py
"""
Tests for get_owner FastAPI dependency.
Uses a disposable minimal FastAPI app + TestClient so tests don't depend on
the full PropGuard wiring.
"""

import os
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.models.owner import Owner
from app.services.owner_resolver import get_owner

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _make_app():
    app = FastAPI()

    @app.get("/whoami")
    def whoami(owner: Owner = Depends(get_owner)):
        return {
            "id": owner.id,
            "kind": owner.kind,
            "plan": owner.plan,
            "metaapi_account_id": owner.metaapi_account_id,
        }

    return app


class TestGetOwnerAnonymous:
    def test_no_credentials_mints_anon_session(self):
        client = TestClient(_make_app())
        resp = client.get("/whoami")
        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] == "anon"
        assert body["plan"] == "anon"
        assert body["metaapi_account_id"] is None
        # Cookie should be set
        assert "anon_session_id" in resp.cookies
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.owner_resolver'`

- [ ] **Step 3: Implement the resolver (anon-mint case only)**

```python
# backend/app/services/owner_resolver.py
"""
FastAPI dependency that resolves every request to an Owner.

Resolution order:
  1. Authorization: Bearer <jwt> → authenticated user Owner.
  2. anon_session_id cookie → existing anonymous Owner (last_active_at touched).
  3. Neither → new anonymous session is created and cookie is set on response.
"""

import hashlib
import logging

from fastapi import Depends, Request, Response

from app.models.owner import Owner
from app.services.anon_sessions import (
    create_anon_session,
    get_anon_session,
    touch_anon_session,
)

logger = logging.getLogger(__name__)

ANON_COOKIE = "anon_session_id"
ANON_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()[:32]


def _mint_anon(request: Request, response: Response) -> Owner:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    sid = create_anon_session(ip_hash=_hash_ip(ip), user_agent=ua)
    if sid is None:
        # DB unavailable — fall back to ephemeral UUID that exists only for this request.
        import uuid
        sid = str(uuid.uuid4())
        logger.warning("anon session DB insert failed, using ephemeral id")
    response.set_cookie(
        key=ANON_COOKIE,
        value=sid,
        max_age=ANON_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return Owner(id=sid, kind="anon", plan="anon", metaapi_account_id=None)


def get_owner(request: Request, response: Response) -> Owner:
    # Step 3 only for now; JWT + existing-cookie cases land in later tasks.
    return _mint_anon(request, response)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/owner_resolver.py backend/tests/test_owner_resolver.py
git commit -m "feat(owner): get_owner mints anon session when no credentials"
```

---

## Task 9: `get_owner` — existing anon cookie case

**Files:**
- Modify: `backend/app/services/owner_resolver.py`
- Test: `backend/tests/test_owner_resolver.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_owner_resolver.py`:

```python
class TestGetOwnerExistingAnon:
    def test_cookie_reuses_existing_session(self):
        client = TestClient(_make_app())
        # First request mints session
        r1 = client.get("/whoami")
        sid = r1.cookies["anon_session_id"]
        # Second request with same cookie should return same id
        r2 = client.get("/whoami", cookies={"anon_session_id": sid})
        assert r2.json()["id"] == sid
        assert r2.json()["kind"] == "anon"

    def test_unknown_cookie_mints_new_session(self):
        client = TestClient(_make_app())
        bogus = "00000000-0000-0000-0000-000000000000"
        resp = client.get("/whoami", cookies={"anon_session_id": bogus})
        # Should NOT return the bogus id — a new one is minted
        assert resp.json()["id"] != bogus
        assert resp.json()["kind"] == "anon"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py::TestGetOwnerExistingAnon -v`
Expected: `test_cookie_reuses_existing_session` fails because the resolver currently always mints.

- [ ] **Step 3: Extend the resolver**

Replace the `get_owner` function body in `backend/app/services/owner_resolver.py`:

```python
def get_owner(request: Request, response: Response) -> Owner:
    # 2. Existing anon cookie
    sid = request.cookies.get(ANON_COOKIE)
    if sid:
        row = get_anon_session(sid)
        if row and row.get("claimed_by_user_id") is None:
            touch_anon_session(sid)
            return Owner(id=sid, kind="anon", plan="anon", metaapi_account_id=None)

    # 3. Mint a fresh anon session
    return _mint_anon(request, response)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/owner_resolver.py backend/tests/test_owner_resolver.py
git commit -m "feat(owner): get_owner reuses existing anon cookie"
```

---

## Task 10: `get_owner` — JWT user case

**Files:**
- Modify: `backend/app/services/owner_resolver.py`
- Test: `backend/tests/test_owner_resolver.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_owner_resolver.py`:

```python
class TestGetOwnerUser:
    def test_valid_jwt_returns_user_owner(self):
        import secrets
        from app.services.auth import register_user, login_user, _users_mem
        _users_mem.clear()
        email = f"ownerjwt-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        token = login_user(email, "password123")["token"]

        client = TestClient(_make_app())
        resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] == "user"
        assert body["plan"] == "free"
        # No anon cookie set because this is a logged-in user
        assert "anon_session_id" not in resp.cookies

    def test_invalid_jwt_falls_back_to_anon(self):
        client = TestClient(_make_app())
        resp = client.get("/whoami", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 200
        assert resp.json()["kind"] == "anon"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py::TestGetOwnerUser -v`
Expected: FAIL — the resolver ignores Authorization header.

- [ ] **Step 3: Extend the resolver**

Replace the `get_owner` function body:

```python
def get_owner(request: Request, response: Response) -> Owner:
    # 1. Authorization: Bearer <jwt>
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        from app.services.auth import verify_token, user_dict_to_owner
        token = auth_header[7:].strip()
        user = verify_token(token)
        if user:
            return user_dict_to_owner(user)
        # Invalid/expired JWT — fall through to anon resolution.

    # 2. Existing anon cookie
    sid = request.cookies.get(ANON_COOKIE)
    if sid:
        row = get_anon_session(sid)
        if row and row.get("claimed_by_user_id") is None:
            touch_anon_session(sid)
            return Owner(id=sid, kind="anon", plan="anon", metaapi_account_id=None)

    # 3. Mint a fresh anon session
    return _mint_anon(request, response)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/owner_resolver.py backend/tests/test_owner_resolver.py
git commit -m "feat(owner): get_owner resolves JWT to user, falls back gracefully"
```

---

## Task 11: `require_user` guard dependency

**Files:**
- Modify: `backend/app/services/owner_resolver.py`
- Test: `backend/tests/test_owner_resolver.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_owner_resolver.py`:

```python
class TestRequireUser:
    def _app_with_guard(self):
        from app.services.owner_resolver import require_user
        app = FastAPI()

        @app.get("/private")
        def private(owner: Owner = Depends(require_user)):
            return {"id": owner.id}

        return app

    def test_anon_rejected_with_401(self):
        resp = TestClient(self._app_with_guard()).get("/private")
        assert resp.status_code == 401
        assert "authentication" in resp.json()["detail"].lower()

    def test_user_allowed(self):
        import secrets
        from app.services.auth import register_user, login_user, _users_mem
        _users_mem.clear()
        email = f"reqguard-{secrets.token_hex(4)}@test.propguard.ai"
        register_user(email, "password123")
        token = login_user(email, "password123")["token"]
        resp = TestClient(self._app_with_guard()).get(
            "/private", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py::TestRequireUser -v`
Expected: `ImportError: cannot import name 'require_user'`

- [ ] **Step 3: Implement the guard**

Append to `backend/app/services/owner_resolver.py`:

```python
from fastapi import HTTPException


def require_user(owner: Owner = Depends(get_owner)) -> Owner:
    """Endpoints that still require authentication use this instead of get_owner."""
    if owner.kind != "user":
        raise HTTPException(status_code=401, detail="Authentication required")
    return owner
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_owner_resolver.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/owner_resolver.py backend/tests/test_owner_resolver.py
git commit -m "feat(owner): require_user guard for auth-required endpoints"
```

---

## Task 12: Ensure DB user lookups surface `metaapi_account_id`

**Files:**
- Modify: `backend/app/services/database.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth.py`:

```python
class TestMetaapiColumn:
    def test_registered_user_has_metaapi_account_id_none(self):
        import secrets
        from app.services.auth import register_user, _users_mem
        _users_mem.clear()
        email = f"meta-{secrets.token_hex(4)}@test.propguard.ai"
        user = register_user(email, "password123")
        # Must be present as a key so downstream user_dict_to_owner can read it.
        assert "metaapi_account_id" in user
        assert user["metaapi_account_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth.py::TestMetaapiColumn -v`
Expected: FAIL — `metaapi_account_id` is not in the user dict returned by the in-memory fallback.

- [ ] **Step 3: Update `_safe_user` and in-memory register to expose the column**

In `backend/app/services/auth.py`:

Change the in-memory `register_user` fallback block to include the column:
```python
    user = {
        "id": secrets.token_hex(8),
        "email": email,
        "name": user_name,
        "password_hash": pw_hash,
        "tier": "free",
        "telegram_chat_id": None,
        "metaapi_account_id": None,
        "created_at": datetime.now().isoformat(),
    }
```

For Supabase-backed path: the migration in Task 1 already added the column. `db.table("users").select("*")` will return it, so no Python change needed there.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth.py backend/tests/test_auth.py
git commit -m "feat(auth): in-memory user fallback exposes metaapi_account_id"
```

---

## Task 13: Wire `require_user` into existing authenticated endpoints

This task migrates existing endpoints that previously read the JWT inline to `Depends(require_user)`. Behavior stays identical — endpoints still reject non-users with 401.

**Files:**
- Modify: `backend/app/api/routes.py`

- [ ] **Step 1: Audit existing endpoints that read `Authorization` header inline**

Run:
```bash
cd backend && grep -n "Authorization\|verify_token\|Header(" app/api/routes.py
```
Expected output: a list of auth-gated endpoints. The ones currently parsing the header inline need to switch to `Depends(require_user)`.

- [ ] **Step 2: Pick the smallest pilot endpoint first — `GET /api/auth/me`**

Locate `@router.get("/api/auth/me")` in `backend/app/api/routes.py`. Current shape (approximate):
```python
@router.get("/api/auth/me")
async def me(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "")
    user = verify_token(token)
    if not user:
        raise HTTPException(401)
    return user
```

Change to:
```python
from app.services.owner_resolver import require_user
from app.services.auth import get_user_by_id
from app.models.owner import Owner
from fastapi import Depends

@router.get("/api/auth/me")
async def me(owner: Owner = Depends(require_user)):
    return get_user_by_id(owner.id)
```

- [ ] **Step 3: Restart backend and manually smoke-test**

Run:
```bash
cd backend && python -m uvicorn app.main:app --port 8001 &
# wait 2 seconds
curl -s http://localhost:8001/api/auth/me
curl -s -H "Authorization: Bearer garbage" http://localhost:8001/api/auth/me
# Register via existing flow, grab token, then:
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/auth/me
```
Expected: first two return 401 (no auth / bad auth), third returns user dict. Kill the server after.

- [ ] **Step 4: Migrate the remaining auth-gated endpoints**

The full list (confirm via the grep in Step 1):
- `POST /api/payments/checkout`
- Any endpoint that currently reads `authorization: str = Header(...)` and calls `verify_token`.

For each, replace the inline header parsing with `Depends(require_user)` and use `owner.id` where `user["id"]` was used. **Do not** touch endpoints that don't currently require auth — leave them as-is for PR 2/3 to migrate.

- [ ] **Step 5: Run the full test suite**

Run: `cd backend && python -m pytest -v`
Expected: all existing tests still pass (60+ existing + new ones from this plan). If an existing test fails, investigate — most likely a migrated endpoint changed its error shape.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "refactor(routes): migrate auth-gated endpoints to Depends(require_user)"
```

---

## Task 14: Smoke test — deploy locally and verify zero regression

This is the final gate before merging PR 1. No new code; run the existing product end-to-end against the migrated schema.

**Files:** none (ops verification)

- [ ] **Step 1: Start backend against dev Supabase**

Run:
```bash
cd backend && python -m uvicorn app.main:app --port 8001
```

- [ ] **Step 2: Start frontend**

Run in another shell:
```bash
cd frontend && echo "NEXT_PUBLIC_API_URL=http://localhost:8001" > .env.local && npx next dev --port 3001
```

- [ ] **Step 3: Manual smoke checklist**

Walk through this list in the browser at `http://localhost:3001`:
- [ ] Register a new account → succeeds, token returned.
- [ ] Log in → dashboard loads.
- [ ] Compliance card displays account state.
- [ ] K-line chart renders for a symbol.
- [ ] Place a simulated order through the trading panel.
- [ ] AI Trading panel analyzes a strategy.
- [ ] Log out → redirects back to login.

If any step fails, investigate before merging. Most likely failure: a service function reads a column that no longer exists or expects `user_id` where the caller now passes `owner.id`.

- [ ] **Step 4: Check no orphan `anon_sessions` rows accumulated**

Run against dev Supabase:
```sql
select count(*) from anon_sessions where claimed_by_user_id is null;
```
Expected: 0 (because no public endpoints use `get_owner` yet — they all use `require_user`, which doesn't mint). If > 0, something in Task 13 accidentally switched an auth-required endpoint to `get_owner`; fix before merging.

- [ ] **Step 5: Open PR**

```bash
gh pr create --title "PR 1/3: Owner abstraction + schema migration" --body "$(cat <<'EOF'
## Summary
- Adds `anon_sessions`, `plan_quotas`, `owner_quota_usage`, `ai_cost_ledger` tables
- Adds `owner_id` + `owner_kind` columns on all user-owned tables (backfilled from `user_id`)
- Introduces `Owner` value object, `get_owner` resolver, and `require_user` guard
- Migrates existing auth-gated endpoints to `Depends(require_user)` with zero behavior change

No user-visible change in this PR. Subsequent PRs build anonymous sandbox mode on this foundation.

Spec: `docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md`
Plan: `docs/superpowers/plans/2026-04-19-foundation-owner-abstraction.md`

## Test plan
- [x] `pytest backend/tests` — all green
- [ ] Manual smoke test per plan Task 14 Step 3
- [ ] Migration applied cleanly to dev Supabase (verified via §8 row count)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (author runs before handoff)

- [ ] **Spec coverage:** §1 Owner dataclass (Task 3), §2 resolver (Tasks 8–11), §3 schema (Tasks 1–2), §4 claim flow preparation (Task 6 — the marker; data migration itself is deferred to PR 3), §12 cleanup job (NOT in this plan — belongs in PR 2/3 ops work when sandbox data starts accumulating).
- [ ] **Placeholder scan:** no `TBD` / `implement later` / "similar to Task N" references in any step.
- [ ] **Type consistency:** `Owner`, `OwnerKind`, `PlanTier`, `get_owner`, `require_user`, `user_dict_to_owner`, `create_anon_session`, `get_anon_session`, `touch_anon_session`, `claim_anon_session`, `anon_session_id` cookie name — all used consistently across tasks.
- [ ] **Out of scope (intentional):** quota enforcement middleware (PR 2), Broker/AIClient abstractions (PR 2), frontend auth gate removal (PR 3), `/api/auth/register` claim flow invocation (PR 3). Each is flagged in its task or covered by a separate plan.
