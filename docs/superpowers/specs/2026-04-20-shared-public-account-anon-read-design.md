# Shared Public Account — Anonymous Read + Attributed Writes

**Date:** 2026-04-20
**Status:** Approved for implementation
**Scope:** Backend (FastAPI), Frontend (Next.js), DB migration
**Related prior work:** `2026-04-19-anonymous-sandbox-design.md`

## Goal

Let anonymous visitors see everything happening on the shared public MetaApi account (positions, pending orders, trade history) without logging in. Require login only for actions that produce side-effects (place/modify/close orders, AI auto-trade, AI briefing). When a logged-in user places an order on the shared account, record which user placed it and surface the attribution in the trade history so different users' activity is visible. Users who want an isolated environment connect their own MetaApi account via the existing entry.

## Non-goals

- Per-user isolation on the shared account (any logged-in user can modify/close anyone's positions — this is the chosen "shared control" model).
- Per-position audit log for modify/close actions. Only order-placement attribution in v1.
- Rate limiting or anti-abuse on shared-account writes. Deferred to a follow-up.

## Authorization matrix

Shared public account = backend `config.METAAPI_ACCOUNT_ID` (the TopStep/CFT default). Any user whose `owner.metaapi_account_id` is `None` (anonymous, or logged-in-but-unbound) reads/writes against this single account.

| Endpoint | Current | New |
|---|---|---|
| `GET /api/trading/account` | `require_user` | **`get_owner`** |
| `GET /api/trading/account-info` | `require_user` | **`get_owner`** |
| `GET /api/trading/orders` | `require_user` | **`get_owner`** |
| `GET /api/trading/history` | `require_user` | **`get_owner`** |
| `GET /api/trading/symbol/{symbol}` | public | unchanged |
| `POST /api/trading/order` | `require_user` | unchanged |
| `POST /api/trading/pending-order` | `require_user` | unchanged |
| `POST /api/trading/position/{id}/close` | `require_user` | unchanged |
| `POST /api/trading/position/{id}/close-partial` | `require_user` | unchanged |
| `POST /api/trading/position/{id}/modify` | `require_user` | unchanged |
| `POST /api/trading/order/{id}/cancel` | `require_user` | unchanged |
| `POST /api/ai-trade/analyze` `execute` `start` `stop` | `require_user` | unchanged |
| `GET /api/accounts/{id}/briefing` | public | **`require_user`** |
| `POST /api/sandbox/reset` | `require_user` | **always 403** (see "Broker routing" below — shared and bound accounts are both real MetaApi, neither is resettable) |

Bound users (`owner.metaapi_account_id` non-null) continue to read/write their own MetaApi account. They do not see shared-account data and no attribution is recorded for them.

## Broker routing

Previously `broker_factory.get_broker(owner)` returned `SandboxBroker(owner)` for every unbound owner — a per-owner simulated account. Under this design the shared public account is the real MetaApi demo at `settings.metaapi_account_id`, so the factory changes:

```python
def get_broker(owner: Owner) -> BrokerBase:
    if owner.metaapi_account_id:
        return MetaApiBroker(owner.metaapi_account_id)
    settings = get_settings()
    if settings.metaapi_account_id:
        return MetaApiBroker(settings.metaapi_account_id)
    return SandboxBroker(owner)  # local-dev fallback when MetaApi unconfigured
```

Consequences:
- Every anonymous and unbound-logged-in user now reads/writes the **same real MetaApi demo account**. This is the product decision: real MT5 experience over isolation.
- Per-owner sandbox rows in Postgres become orphaned. No cleanup migration in this PR — harmless, cleaned up later.
- `POST /api/sandbox/reset` loses its purpose (neither shared nor bound accounts are sandboxes anymore). We return 403 uniformly with `detail="Account reset is not supported on real broker accounts"` and hide the frontend button for everyone.

## Data model

New migration `supabase/migrations/<ts>_order_attributions.sql`:

```sql
create table if not exists order_attributions (
  broker_order_id text primary key,
  broker_position_id text,
  account_id text not null,
  user_id uuid not null references users(id) on delete set null,
  user_label text not null,
  symbol text,
  side text check (side in ('buy','sell')),
  volume numeric,
  placed_at timestamptz default now()
);

create index if not exists idx_attr_position on order_attributions(broker_position_id);
create index if not exists idx_attr_account_time on order_attributions(account_id, placed_at desc);
```

Field notes:
- `broker_order_id` is the MetaApi order id and the primary key — one order, one placer.
- `broker_position_id` is indexed separately so the positions read path can `IN`-join quickly. Pending orders have no positionId at placement time and require backfill (see below).
- `user_label` is frozen at write time — it does NOT track future changes to `users.name`, so editing one's display name does not rewrite history.
- `account_id` exists so the table can support multiple shared accounts in the future without migration.
- `symbol` / `side` / `volume` are denormalized for "my activity" queries without round-tripping to MetaApi.

### Label freezing

New module `backend/app/services/attribution.py`:

```python
def freeze_user_label(user: dict) -> str:
    name = (user.get("name") or "").strip()
    if name:
        return name[:32]
    email = user["email"]
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked = local[0] + "*"
    else:
        masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked}@{domain}"
```

## Write path (attribution)

Inside the two order-placement endpoints — `/api/trading/order` (market) and `/api/trading/pending-order` (limit/stop) — after a successful broker response:

```python
if result.get("orderId") and owner.metaapi_account_id is None:
    try:
        record_attribution(
            broker_order_id=result["orderId"],
            broker_position_id=result.get("positionId"),
            account_id=settings.METAAPI_ACCOUNT_ID,
            user_id=owner.id,
            user_label=freeze_user_label(get_user(owner.id)),
            symbol=body.symbol,
            side=body.side,
            volume=body.volume,
        )
    except Exception as e:
        logger.error("attribution write failed: %s", e)
        # Do NOT raise — the order is already live at the broker.
```

Skip rules:
- `owner.metaapi_account_id is not None` — user is on their own bound account; no attribution.
- `result.get("orderId")` is falsy — broker rejected the order.

## Read path (label join)

`GET /api/trading/account` — after pulling positions from MetaApi, collect `position.id` values, run one `SELECT broker_position_id, user_label FROM order_attributions WHERE broker_position_id = ANY($1)`, attach `user_label` to each position. Missing rows render as `"—"` (not null, to keep frontend typing simple).

`GET /api/trading/history` — same approach keyed on `orderId`. Additionally, for deals where the attribution row has a null `broker_position_id` but the MetaApi deal exposes one, fire a fire-and-forget UPDATE to backfill. Do not block the response.

`GET /api/trading/orders` (pending) — same approach keyed on `orderId`.

For bound users (`owner.metaapi_account_id` non-null) the read handlers skip the attribution query entirely and return `user_label: null` — the frontend hides the column.

Response schema additions (additive, no breaking change):

```jsonc
// positions array items, history deals, pending orders all gain:
{ "user_label": "Mason" }        // logged-in name
{ "user_label": "m***n@gmail.com" } // masked email fallback
{ "user_label": "—" }            // pre-feature or missing attribution
{ "user_label": null }           // bound user, attribution disabled
```

## Frontend changes

**`frontend/src/lib/api.ts`** — all trading GETs use `credentials: 'include'` so the anon cookie round-trips; read calls no longer short-circuit on missing token.

**`components/dashboard/TradingPanel.tsx`** — form stays interactive. On submit, if no JWT, open `LoginModal`; else submit. Same pattern for AI-analyze button.

**`components/dashboard/PositionsTable.tsx`** — new `By` column rendering `user_label`. Close/modify controls stay visible; anon click opens `LoginModal`. When response has `user_label === null` (bound-account mode), hide the column entirely.

**Trade history view** — add `By` column with the same null-hide rule. The exact component file is pinned during implementation after inspecting the current history rendering in `components/dashboard/AccountManager.tsx` and its children.

**`components/dashboard/BriefingPanel.tsx`** — on 401 from `/briefing`, render a "Log in to view today's briefing" placeholder with a CTA that opens `LoginModal`.

**`components/dashboard/AITrader.tsx`** — panel visible to anon; start/stop buttons open `LoginModal`.

**New `components/LoginModal.tsx`** — lightweight modal with email+password form. On success, close modal. v1 does NOT re-dispatch the pending action — user clicks again. Secondary CTA links to `/login?mode=register`.

**`components/dashboard/AccountHeader.tsx`** — add "Connect my account" button linking to the existing `/settings/broker` page. Visible to all users; label adapts ("Log in to connect your account" when anon). The settings page itself is unchanged.

**`components/dashboard/TradingPanel.tsx` / sandbox reset control** — hide (or disable with tooltip "Connect your own account to reset") when `owner.metaapi_account_id` is falsy. Backend enforces regardless.

**i18n** — new keys in `frontend/src/i18n/`: `By`, `trade.by.unknown` (`—`), `auth.login_to_place_order`, `auth.login_to_view_briefing`, `auth.connect_your_account`, `sandbox.reset_disabled_on_public`.

## Edge cases

- **Attribution write failure** — logged, order succeeds, history shows `—`.
- **Pending-order positionId backfill miss** — lazy backfill during history reads covers most cases. Close/modify continues to work (operates on positionId directly), only the `By` column shows `—`.
- **Pre-feature historical orders** — no attribution rows; display as `—`. No backfill attempted.
- **Bound user** — reads hit their own account, writes skip attribution, frontend hides `By` column. The feature is effectively invisible.
- **Anonymous cookie** — `get_owner` issues the existing 30-day `anon_session_id` cookie; no new cookie work. Every fetch must use `credentials: 'include'`.
- **Shared-control abuse** — deferred. Any logged-in user can close any public-account position. Login itself is the gate. Follow-up work can add a `position_actions` audit table and rate limits.
- **Public-account reset** — hard-blocked by 403 in the backend for everyone. Neither shared nor bound accounts are resettable (both are real MetaApi). Frontend reset button hidden for everyone. If the shared demo account gets blown out, an operator rotates in a fresh `settings.metaapi_account_id`.

## Testing

**Backend** (`backend/tests/`):

- `test_attribution.py`:
  - `freeze_user_label` — name present, name empty/email masking, `local_part` length ≤ 2, name truncated at 32 chars.
  - `record_attribution` — happy path, DB exception path (must not raise).
- `test_trading_routes_anon.py`:
  - Anon `GET /api/trading/account` → 200, shared account, positions include `user_label`.
  - Anon `POST /api/trading/order` → 401.
  - Anon `GET /api/accounts/{id}/briefing` → 401.
  - Logged-in user on shared account placing an order → exactly one new `order_attributions` row with correct `user_label`.
  - Logged-in user on bound account placing an order → no new `order_attributions` row.
  - Anon, unbound-logged-in, and bound `POST /api/sandbox/reset` all → 403.

**Frontend manual smoke** (to be codified in the implementation plan via headless browser per `feedback_automate_smoke_tests.md`):

- Anon visitor sees positions / pending orders / history with `By` column.
- Anon clicks "Place Order" → `LoginModal` opens.
- Anon clicks "Briefing" → placeholder + CTA.
- Logged-in user places order → own `name` (or masked email) appears in `By` column.
- After binding own account in `/settings/broker`, `By` column disappears and other users' positions are no longer visible.
- Public-account reset button absent/disabled for unbound users.

## Rollout

1. DB migration (new table, indexes).
2. Backend `services/attribution.py` + write/read changes + auth dep changes.
3. Frontend `LoginModal` + read-path column + login-gated buttons.
4. Manual smoke test via headless browser.
5. Deploy backend + frontend.

No feature flag — the change is additive (new column, new modal, loosened auth on reads). If something breaks, revert is one commit.
