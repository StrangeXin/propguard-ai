# PropGuard AI — Anonymous Sandbox Mode & Tiered Access

**Status:** Design approved, ready for implementation plan
**Date:** 2026-04-19
**Author:** Brainstorming session between user and assistant

## Problem

PropGuard AI currently requires authentication to access the dashboard. This blocks the top of the conversion funnel: prospective users can't experience the core product (AI trading, compliance monitoring, auto-execution) before signing up. We need to lower the entry barrier while preserving a strong reason to register and pay.

## Goal

Allow fully unauthenticated users to experience every feature of PropGuard AI on a per-visitor isolated sandbox account, then convert them to registered/paid users who can bind their own real Prop Firm MetaApi accounts. The paid tier's value proposition becomes concrete: real account binding + higher AI quotas + 24/7 background automation + persistent history.

## Non-Goals

- Rebuilding the existing `tier.py` plan system — reuse it, extend it with an `anon` tier.
- Rewriting the existing authentication system — keep it, just make it optional.
- Supporting BYOK for Claude API — all AI calls flow through our shared Claude key for cost control and UX consistency.
- Multi-device sync for anonymous users — anonymous sessions are cookie-bound to one browser.

## Product Decisions (from brainstorming)

1. **Anonymous users get full feature access** (option C from the brainstorm) via a per-visitor simulated sandbox account starting at $100,000 equity.
2. **Pricing model Y**: anonymous/free users have capped quotas and constraints; paid tiers unlock real account binding + unlimited AI + 24/7 background auto-trader + permanent history.
3. **Server-side state with TTL** (option Q): anonymous state persists in Postgres under an `anon_session_id` cookie; registration atomically migrates that data to the new user's `user_id`, zero data loss at the conversion point.

## High-Level Architecture

```
┌─────────────────┐        ┌──────────────────────┐
│ Browser         │        │ FastAPI              │
│                 │  HTTP  │                      │
│ anon_session_id │◀──────▶│ OwnerResolver        │
│ cookie (30d)    │        │ (Depends(get_owner)) │
└─────────────────┘        └──────────┬───────────┘
                                      │  Owner(id, kind, plan, metaapi_account_id)
                                      ▼
                           ┌──────────────────────┐
                           │ Quota Middleware     │──▶ plan_quotas table
                           └──────────┬───────────┘
                                      ▼
              ┌───────────────────────┴────────────────────────┐
              ▼                                                ▼
    ┌─────────────────┐                             ┌───────────────────┐
    │ BrokerFactory   │                             │ AIClient          │
    │                 │                             │ (shared Claude key)│
    │ ├ MetaApiBroker │ (paid users)                │ + cost_ledger     │
    │ └ SandboxBroker │ (anon/free)                 └───────────────────┘
    └─────────────────┘
              │
              ▼
    ┌─────────────────────────────────────┐
    │ Postgres (Supabase)                 │
    │  anon_sessions   (new)              │
    │  users           (existing)         │
    │  trades          (+ owner_id col)   │
    │  strategies      (+ owner_id col)   │
    │  ai_history      (+ owner_id col)   │
    │  owner_quota_usage (new)            │
    │  ai_cost_ledger  (new)              │
    └─────────────────────────────────────┘
```

## Component Design

### 1. `Owner` abstraction (core)

A single value object flowing through the entire request path. Service layer never branches on "is this anonymous vs logged in"; it reads `owner.plan` and `owner.metaapi_account_id`.

```python
# backend/app/models/owner.py
@dataclass(frozen=True)
class Owner:
    id: str                           # user UUID or anon_session UUID
    kind: Literal["user", "anon"]
    plan: Literal["anon", "free", "pro", "premium"]
    metaapi_account_id: str | None    # None → route to SandboxBroker
```

All existing service function signatures migrate from `(user_id, ...)` to `(owner: Owner, ...)`.

### 2. `OwnerResolver` middleware

A FastAPI dependency. Resolution order:

1. `Authorization: Bearer <jwt>` header present and valid → fetch user from `users` table → `Owner(kind="user", plan=user.plan, metaapi_account_id=user.metaapi_account_id)`.
2. Else `anon_session_id` cookie present → fetch row from `anon_sessions` → `Owner(kind="anon", plan="anon", metaapi_account_id=None)`. Update `last_active_at`.
3. Else no credentials → insert new row in `anon_sessions`, set `Set-Cookie: anon_session_id=<uuid>; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`.

Expired/invalid JWT falls through to step 2 (graceful degradation, never hard-fails into a broken UI).

### 3. Database schema changes

**New tables:**

```sql
CREATE TABLE anon_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ip_hash TEXT,  -- optional: SHA256(ip + salt) for abuse detection
    user_agent TEXT
);
CREATE INDEX idx_anon_sessions_last_active ON anon_sessions(last_active_at)
    WHERE claimed_by_user_id IS NULL;

CREATE TABLE owner_quota_usage (
    owner_id UUID NOT NULL,
    owner_kind TEXT NOT NULL CHECK (owner_kind IN ('user','anon')),
    action TEXT NOT NULL,
    date DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner_id, action, date)
);

CREATE TABLE plan_quotas (
    plan TEXT NOT NULL CHECK (plan IN ('anon','free','pro','premium')),
    action TEXT NOT NULL,
    daily_limit INTEGER,  -- NULL means unlimited
    PRIMARY KEY (plan, action)
);

CREATE TABLE ai_cost_ledger (
    id BIGSERIAL PRIMARY KEY,
    owner_id UUID NOT NULL,
    owner_kind TEXT NOT NULL,
    date DATE NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd NUMERIC(10,6) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_cost_owner_date ON ai_cost_ledger(owner_id, date);
```

**Existing tables get `owner_id` + `owner_kind`:**

```sql
-- trades, strategies, ai_history, alert_history, saved_configs, etc.
ALTER TABLE trades ADD COLUMN owner_id UUID NOT NULL;
ALTER TABLE trades ADD COLUMN owner_kind TEXT NOT NULL
    CHECK (owner_kind IN ('user','anon'));
CREATE INDEX idx_trades_owner ON trades(owner_id);
-- (repeat for each user-owned table)
```

During migration, existing `user_id` rows get mirrored to `(owner_id=user_id, owner_kind='user')`. The `user_id` column stays during a deprecation window, then is dropped.

**No foreign key on `owner_id`.** Because `owner_id` is polymorphic (references either `users.id` or `anon_sessions.id` depending on `owner_kind`), Postgres can't enforce a standard FK. Integrity is maintained in application code and by the cleanup job (§12).

### 4. Anonymous → user claim flow

On successful registration (in `POST /api/auth/register`), if the request carries an `anon_session_id` cookie, run a single transaction:

```sql
BEGIN;
UPDATE trades SET owner_id = :new_user_id, owner_kind = 'user'
    WHERE owner_id = :anon_id AND owner_kind = 'anon';
UPDATE strategies SET owner_id = :new_user_id, owner_kind = 'user'
    WHERE owner_id = :anon_id AND owner_kind = 'anon';
UPDATE ai_history SET owner_id = :new_user_id, owner_kind = 'user'
    WHERE owner_id = :anon_id AND owner_kind = 'anon';
UPDATE alert_history SET owner_id = :new_user_id, owner_kind = 'user'
    WHERE owner_id = :anon_id AND owner_kind = 'anon';
UPDATE owner_quota_usage SET owner_id = :new_user_id, owner_kind = 'user'
    WHERE owner_id = :anon_id AND owner_kind = 'anon';
UPDATE anon_sessions SET claimed_by_user_id = :new_user_id
    WHERE id = :anon_id;
COMMIT;
```

Response returns a count of migrated rows so the frontend can show "已保留您的 23 笔沙盒交易".

### 5. `BrokerBase` + implementations

```python
# backend/app/services/broker_base.py
class BrokerBase(Protocol):
    async def account_info(self) -> AccountInfo: ...
    async def positions(self) -> list[Position]: ...
    async def pending_orders(self) -> list[Order]: ...
    async def place_market_order(self, symbol: str, side: str,
                                  volume: float, sl: float | None,
                                  tp: float | None) -> OrderResult: ...
    async def place_pending_order(self, ...) -> OrderResult: ...
    async def close_position(self, position_id: str) -> None: ...
    async def close_position_partial(self, position_id: str,
                                      volume: float) -> None: ...
    async def modify_position(self, position_id: str,
                               sl: float | None, tp: float | None) -> None: ...
    async def cancel_order(self, order_id: str) -> None: ...
    async def history(self, from_date: datetime,
                       to_date: datetime) -> list[Trade]: ...
    async def symbol_info(self, symbol: str) -> SymbolInfo: ...
```

`MetaApiBroker` — current `broker.py` refactored to implement the protocol; instantiated per-request with the user's account ID.

`SandboxBroker` — new; delegates most logic to the existing `paper_trading.py` but keys all state by `owner_id`. Quote source is the existing `kline_data.py` (OKX / TwelveData). Execution uses midprice ± configured spread; fills are instant. Spread config in `data/sandbox_spreads.json` (e.g., EURUSD=1pt, XAUUSD=30pt, BTCUSD=$5).

Sandbox-specific features:
- Starting equity configurable per Prop Firm rule file (default $100k).
- `POST /api/sandbox/reset` — wipes positions/orders/history, resets equity. Rate-limited to prevent abuse.
- The sandbox respects the selected Prop Firm's rules for compliance, so PropGuard's core value prop (compliance monitoring) is fully experienced in the sandbox.

### 6. `BrokerFactory`

```python
# backend/app/services/broker_factory.py
def get_broker(owner: Owner) -> BrokerBase:
    if owner.metaapi_account_id:
        return MetaApiBroker(owner.metaapi_account_id)
    return SandboxBroker(owner.id)
```

All 11 trading routes in `routes.py` switch to `broker = get_broker(owner)` and call the protocol methods. The existing `live_trading.py` and `paper_trading.py` wrapper code is collapsed into the two broker implementations.

### 7. `AIClient` + unified Claude routing

All AI calls flow through our shared Claude key — no BYOK. This keeps cost visible, caches consistent, and avoids user key management.

```python
# backend/app/services/ai_client.py
class AIClient:
    def __init__(self, owner: Owner):
        self.owner = owner
        self._anthropic = Anthropic(api_key=settings.shared_claude_key)

    async def score_signal(self, prompt: str) -> ScoreResult:
        await quota.check_and_consume(self.owner, "ai_score")
        resp = await self._anthropic.messages.create(...)
        await cost_tracker.record(self.owner, resp.usage)
        return parse(resp)

    async def trade_tick(self, context: TradingContext) -> TradeDecision:
        await quota.check_and_consume(self.owner, "ai_trade_tick")
        ...

    async def briefing(self, context: BriefingContext) -> Briefing:
        await quota.check_and_consume(self.owner, "briefing")
        ...
```

`ai_scorer.py`, `ai_trader.py`, and `briefing.py` migrate to use `AIClient(owner)` instead of instantiating Anthropic directly.

### 8. Quota system

The quota table is the single source of truth. No hardcoded limits in service code.

| Action | anon | free | pro | premium |
|--------|------|------|-----|---------|
| `ai_score` | 10/day | 20/day | 500/day | unlimited |
| `ai_trade_tick` | 50/day | 100/day | 2000/day | unlimited |
| `briefing` | 1/day | 2/day | 20/day | unlimited |
| `saved_strategies` | 3 total | 5 total | 50 total | unlimited |
| `history_retention_days` | 7 | 30 | unlimited | unlimited |
| `sandbox_reset` | 5/day | 20/day | unlimited | unlimited |

Implementation:
- `plan_quotas` table seeded by migration; editable without code change.
- `@require_quota("ai_score")` FastAPI dependency, returns `402` with machine-readable `QUOTA_EXCEEDED` error on miss.
- Counters roll over at UTC midnight (simplest approach; revisit if users complain about timezone).
- Total-count quotas (saved_strategies) checked against current row count, not a daily counter.

### 9. Anonymous AI auto-trader: frontend-driven tick

Paid users: the existing backend loop in `ai_trader.py` continues to run per-user tasks in the background.

Anonymous/free users: the backend loop does **not** start a task for them. Instead, the frontend polls `POST /api/ai/tick` every N seconds while the Auto Trading panel is active. When the tab closes, polling stops, and the AI stops. This is intentional — it's the single most concrete upgrade hook ("want AI to trade while you sleep? upgrade to Pro").

The tick endpoint itself is owner-agnostic: it loads the user's active strategy, builds context, calls `AIClient.trade_tick()`, executes the resulting action via `get_broker(owner)`. Same function serves frontend polls (anon/free) and backend scheduled calls (pro/premium).

### 10. Frontend changes

**`/dashboard` route becomes public.** Remove the auth guard in `frontend/src/app/dashboard/page.tsx`.

**Landing page `/`**: primary CTA changes to "Try for free — no signup required" pointing directly at `/dashboard`.

**Dashboard header banner** driven by `Owner.kind` / `Owner.plan`:

- `anon`: 🔬 Experience mode · Sandbox $100,000 · Data retained 30 days · **[Register to save →]**
- `free`: ✅ Logged in (Free plan) · **[Upgrade to Pro to bind real account →]**
- `pro` / `premium`: ✅ Pro · Real account: FTMO-XXXX (shows connected firm)

**New page `/settings/broker`** (paid users only):
1. Input field for MetaApi Account ID.
2. `POST /api/user/broker/connect` — backend calls MetaApi SDK `account.deploy()`, waits for `deployed` state (up to 10s).
3. On success: update `users.metaapi_account_id`, switch this user's `BrokerFactory` output starting from the next request.
4. On failure: show diagnostic (invalid account ID / MT5 credentials missing / server unreachable) with a link to documentation.

Security: we store only the MetaApi Account ID. MT5 login credentials are held by MetaApi's platform, never touch our servers.

**Global error interceptor** (new) handles the standardized error schema:

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "Daily AI scoring limit reached (10/10)",
    "upgrade_url": "/pricing",
    "resets_at": "2026-04-20T00:00:00Z"
  }
}
```

Mappings:
- `QUOTA_EXCEEDED` → modal with upgrade CTA + reset countdown.
- `PLAN_REQUIRED` → modal "This feature requires Pro plan".
- `BROKER_UNAVAILABLE` → top banner: "MetaApi temporarily unreachable, falling back to sandbox".

### 11. Conversion hooks (product-level, documented so future iteration keeps them consistent)

1. Quota hit → inline modal with upgrade CTA.
2. Strategy save count reaches 3 → "Max 3 saved — register for 50".
3. AI auto-trader running for 15 min → toast "AI is working for you… upgrade to Pro to keep it running when you're away".
4. Sandbox account bust → modal "Sandbox has been reset — try again with real account protections?".
5. "Reset Sandbox" button subtext → "Register for unlimited resets + permanent history replay".

### 12. Cleanup and maintenance

Nightly cron job (Supabase scheduled function or Railway cron):

```sql
-- Step 1: delete orphan rows for expired anon sessions (polymorphic owner_id,
--         so cleanup is explicit rather than FK-cascade).
WITH expired AS (
    SELECT id FROM anon_sessions
    WHERE claimed_by_user_id IS NULL
      AND last_active_at < NOW() - INTERVAL '30 days'
)
DELETE FROM trades          WHERE owner_kind = 'anon' AND owner_id IN (SELECT id FROM expired);
-- repeat for strategies, ai_history, alert_history, owner_quota_usage, ai_cost_ledger
DELETE FROM anon_sessions
WHERE claimed_by_user_id IS NULL
  AND last_active_at < NOW() - INTERVAL '30 days';
```

For user deletion (`users` table), the application's delete-user flow explicitly cascades: it deletes all rows where `owner_kind='user' AND owner_id=<user_id>` before deleting the user row. This logic lives in a single `delete_user()` service function.

A separate retention policy job enforces `history_retention_days` per plan by deleting rows older than the limit. Runs nightly.

## Error Handling

**Standardized error schema** across all endpoints (described in §10).

**Broker failures**:
- MetaApi connection loss for paid users → return `BROKER_UNAVAILABLE` with `retry_after`. Frontend shows banner but keeps compliance view working (reads cached state).
- Sandbox broker is in-process, can't fail due to connectivity; only input validation errors.

**Quota edge cases**:
- Race condition (two simultaneous calls at count=9/10): atomic `INSERT ... ON CONFLICT (owner_id, action, date) DO UPDATE SET count = count + 1 RETURNING count` then compare to limit.
- Clock skew at UTC midnight: accept; users might get one extra call or one less near the boundary.

**Claim flow failures**:
- Registration succeeds but claim transaction fails: registration still succeeds (user created), claim is retried once asynchronously. If still fails, log to Sentry and allow user to manually trigger claim from settings.
- Cookie missing at registration: no claim, user starts fresh. UX: most users register within the same session so cookie is usually present.

**AI cost runaway**:
- Soft cap per anon session per day on total input tokens (e.g., 50k). Beyond that, all AI actions return `QUOTA_EXCEEDED` regardless of action-level quota. Prevents a motivated attacker from bypassing per-action limits.

## Testing Strategy

The current backend has 6 test files for ~4800 lines of services — this rollout is the right time to backfill coverage on the critical path.

**New test files:**

- `test_owner_resolver.py` — middleware resolution across all three cases (JWT valid / anon cookie / neither); JWT expiry falls through to anon; cookie is set correctly on new anon sessions.
- `test_broker_factory.py` — routes to SandboxBroker when `metaapi_account_id` is None, routes to MetaApiBroker (mocked) otherwise.
- `test_sandbox_broker.py` — order placement, position tracking, P&L calculation at various prices, close / partial-close, compliance rule enforcement, reset.
- `test_quota.py` — each plan's limits enforced, daily rollover at UTC midnight, 402 response shape, race condition under concurrent requests.
- `test_anon_claim.py` — critical. Five+ rows across all user-owned tables under an anon session, registration triggers claim, all rows switched to new user_id atomically, anon_session marked `claimed_by_user_id`.
- `test_ai_client.py` — cost ledger is written on every call, quota consumed before API call, shared key is used regardless of owner kind.

**Existing tests** (`test_auth.py`, `test_rule_engine.py`, etc.) need updates to pass an `Owner` instead of a raw `user_id`.

**Integration test** (end-to-end, new): anonymous visit → place trade → register → verify trade is associated with the new user.

## Rollout Plan

Three sequential PRs to reduce risk:

**PR 1 — Foundation (no user-visible change)**
- Migration: add `anon_sessions`, `plan_quotas`, `owner_quota_usage`, `ai_cost_ledger` tables.
- Migration: add `owner_id` + `owner_kind` columns to all user-owned tables; backfill from `user_id`.
- Add `Owner` model + `OwnerResolver` middleware; all existing endpoints use it but keep their current auth-required behavior.
- Deploy and verify no regressions (all logged-in users still work exactly as before).

**PR 2 — Abstractions + sandbox (still auth-gated)**
- `BrokerBase` protocol + `MetaApiBroker` refactor of current `broker.py` + new `SandboxBroker`.
- `AIClient` refactor of `ai_scorer.py` / `ai_trader.py` / `briefing.py`.
- Quota middleware + `plan_quotas` seed data.
- Backend supports sandbox mode end-to-end, but frontend still gates on login. Can flip a feature flag to test internally.

**PR 3 — Public launch**
- Remove auth guard on `/dashboard`; add plan-based banner.
- Conversion hook modals on quota/plan errors.
- Registration claim flow.
- `/settings/broker` page for paid user binding.
- Landing page CTA update.
- Public launch.

## Open Questions (deferred to implementation)

1. Should the frontend-driven AI tick also work over WebSocket? Currently polling is simpler; WebSocket can be a later optimization.
2. Should anonymous users be able to pre-configure Telegram notifications (and upgrade to start receiving them)? Current plan: Telegram is paid-only to keep complexity bounded; revisit if conversion data suggests otherwise.
3. Exact `plan_quotas` values: the table above is a starting point. Monitor `ai_cost_ledger` in the first 2 weeks and tune.

## Success Metrics

- Time-to-first-trade for new visitors (target: < 2 minutes from landing).
- Anonymous → registered conversion rate (baseline to establish post-launch).
- Registration claim success rate (target: > 99% of registrations with `anon_session_id` cookie successfully migrate data).
- Anonymous-only AI cost per DAU (target: below a threshold TBD after first week of data).
