# Shared Public Account — Anon Read + Attributed Writes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anonymous visitors can view positions, pending orders, and trade history on the shared real-MetaApi demo account. Placing/modifying/closing orders, AI analysis, AI briefing, and AI auto-trade require login. Each order placed by a logged-in user on the shared account is attributed in a new `order_attributions` table; the user's frozen display label (`name` or masked email) joins into the history response so everyone can see who did what.

**Architecture:** (1) A new `order_attributions` table in Supabase. (2) `broker_factory.get_broker` flips — unbound owners now route to `MetaApiBroker(settings.metaapi_account_id)`, not `SandboxBroker`. (3) Four trading read endpoints (`/api/trading/account|account-info|orders|history`) drop `require_user` in favor of `get_owner`. (4) Two write endpoints record attribution rows; three read endpoints join labels into their response. (5) Frontend adds a `LoginModal`, a `By` column in positions/orders/history, and login-gated submit buttons.

**Tech Stack:** Python 3.11+, FastAPI, Supabase/Postgres, Next.js 16 + TypeScript, pytest.

**Spec reference:** `docs/superpowers/specs/2026-04-20-shared-public-account-anon-read-design.md`.

**Dependencies:** PR 2a (broker abstraction) and PR 2b (owner resolver, JWT auth) already landed. HEAD is `main@9f9e6ee`.

**Frontend caveat:** `frontend/AGENTS.md` warns this Next.js version has breaking changes from training-data. Before touching any frontend file, consult `node_modules/next/dist/docs/` for the relevant guide (routing, client components, fetch). Do not invent API shapes.

---

## File Structure

**New files:**
- `supabase/migrations/20260424000000_order_attributions.sql`
- `backend/app/services/attribution.py`
- `backend/tests/test_attribution.py`
- `backend/tests/test_trading_routes_anon.py`
- `frontend/src/components/LoginModal.tsx`
- `frontend/src/hooks/useLoginGate.ts`

**Modified files:**
- `backend/app/services/broker_factory.py` — fallback to `MetaApiBroker(settings.metaapi_account_id)` when owner is unbound
- `backend/app/api/routes.py` — auth dep flips on 4 read endpoints, briefing gets `require_user`, sandbox reset becomes always-403, attribution write in order/pending-order, attribution read join in account/orders/history
- `frontend/src/components/dashboard/TradingPanel.tsx` — login gate on order submit + AI analyze
- `frontend/src/components/dashboard/PositionsTable.tsx` — add `By` column
- `frontend/src/components/dashboard/AccountManager.tsx` — add `By` column to history
- `frontend/src/components/dashboard/BriefingPanel.tsx` — 401 fallback with login CTA
- `frontend/src/components/dashboard/AITrader.tsx` — login gate on start
- `frontend/src/components/dashboard/AccountHeader.tsx` — "Connect my account" CTA
- `frontend/src/lib/types.ts` — add `user_label` to `Position`, add `ClosedDeal` + `PendingOrder` types with `user_label`
- `frontend/src/i18n/locales.ts` — new EN/ZH keys
- `frontend/src/app/providers.tsx` — mount `LoginModal` globally

---

## Task 1: Attribution DB migration

**Files:**
- Create: `supabase/migrations/20260424000000_order_attributions.sql`

- [ ] **Step 1: Write the migration**

```sql
-- PropGuard AI — Order attribution for the shared public account
-- Migration: 20260424000000_order_attributions
-- Spec: docs/superpowers/specs/2026-04-20-shared-public-account-anon-read-design.md

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

- [ ] **Step 2: Push to Supabase**

```bash
export SUPABASE_ACCESS_TOKEN=<token from .env or keychain>
./scripts/db-migrate.sh push
```

Expected: migration file is applied, `./scripts/db-migrate.sh status` shows `20260424000000_order_attributions` as applied.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260424000000_order_attributions.sql
git commit -m "feat(db): order_attributions table for shared-account writes"
```

---

## Task 2: Attribution service module

**Files:**
- Create: `backend/app/services/attribution.py`
- Test: `backend/tests/test_attribution.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_attribution.py`:

```python
"""Tests for attribution service — label freezing and DB write helpers."""

from unittest.mock import patch, MagicMock

import pytest

from app.services.attribution import (
    freeze_user_label,
    record_attribution,
    fetch_labels_by_orders,
    fetch_labels_by_positions,
)


class TestFreezeUserLabel:
    def test_uses_name_when_present(self):
        assert freeze_user_label({"name": "Mason", "email": "m@x.com"}) == "Mason"

    def test_trims_name_whitespace(self):
        assert freeze_user_label({"name": "  Alice  ", "email": "a@x.com"}) == "Alice"

    def test_truncates_name_at_32_chars(self):
        long = "x" * 64
        assert freeze_user_label({"name": long, "email": "a@x.com"}) == "x" * 32

    def test_falls_back_to_masked_email_when_name_empty(self):
        assert freeze_user_label({"name": "", "email": "mason@example.com"}) == "m***n@example.com"

    def test_masks_short_local_part(self):
        # local part "ab" (len 2) → keep first char + "*"
        assert freeze_user_label({"name": "", "email": "ab@x.com"}) == "a*@x.com"

    def test_masks_single_char_local(self):
        assert freeze_user_label({"name": "", "email": "a@x.com"}) == "a*@x.com"

    def test_masks_name_none(self):
        assert freeze_user_label({"name": None, "email": "xy@host.com"}) == "x*@host.com"


class TestRecordAttribution:
    def test_happy_path_inserts_row(self):
        mock_db = MagicMock()
        mock_table = mock_db.table.return_value
        mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"broker_order_id": "o1"}])
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = record_attribution(
                broker_order_id="o1",
                broker_position_id="p1",
                account_id="acc1",
                user_id="u1",
                user_label="Mason",
                symbol="EURUSD",
                side="buy",
                volume=0.1,
            )
        assert result is True
        mock_db.table.assert_called_with("order_attributions")
        insert_arg = mock_table.insert.call_args[0][0]
        assert insert_arg["broker_order_id"] == "o1"
        assert insert_arg["user_label"] == "Mason"

    def test_swallows_db_exception(self):
        mock_db = MagicMock()
        mock_db.table.side_effect = RuntimeError("db down")
        with patch("app.services.attribution.get_db", return_value=mock_db):
            # MUST NOT raise — the order has already been placed at the broker.
            result = record_attribution(
                broker_order_id="o1", broker_position_id=None, account_id="acc1",
                user_id="u1", user_label="Mason", symbol="EURUSD", side="buy", volume=0.1,
            )
        assert result is False

    def test_returns_false_when_db_unavailable(self):
        with patch("app.services.attribution.get_db", return_value=None):
            result = record_attribution(
                broker_order_id="o1", broker_position_id=None, account_id="acc1",
                user_id="u1", user_label="Mason", symbol="EURUSD", side="buy", volume=0.1,
            )
        assert result is False


class TestFetchLabels:
    def test_fetch_by_orders_returns_map(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"broker_order_id": "o1", "user_label": "Mason"},
                {"broker_order_id": "o2", "user_label": "Alice"},
            ]
        )
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = fetch_labels_by_orders(["o1", "o2", "o3"])
        assert result == {"o1": "Mason", "o2": "Alice"}

    def test_fetch_by_orders_empty_input(self):
        with patch("app.services.attribution.get_db") as mock_get:
            result = fetch_labels_by_orders([])
        assert result == {}
        mock_get.assert_not_called()  # no DB round-trip for empty input

    def test_fetch_by_positions_returns_map(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"broker_position_id": "p1", "user_label": "Mason"}]
        )
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = fetch_labels_by_positions(["p1"])
        assert result == {"p1": "Mason"}

    def test_fetch_by_orders_swallows_db_error(self):
        mock_db = MagicMock()
        mock_db.table.side_effect = RuntimeError("db down")
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = fetch_labels_by_orders(["o1"])
        assert result == {}  # fail open: labels missing beats 500 on history read
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_attribution.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.attribution'`.

- [ ] **Step 3: Write the module**

`backend/app/services/attribution.py`:

```python
"""Attribution tracking for shared-account orders.

Records which logged-in user placed each order on the shared public account.
Frontend joins `user_label` into history/positions/orders responses so
anonymous viewers can see activity without exposing emails or user_ids.
"""

import logging

from app.services.database import get_db

logger = logging.getLogger(__name__)


def freeze_user_label(user: dict) -> str:
    """Return a display label frozen at write time.

    Prefers `users.name`; falls back to a masked email like `m***n@host.com`
    when name is absent. Truncates to 32 chars.
    """
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


def record_attribution(
    *,
    broker_order_id: str,
    broker_position_id: str | None,
    account_id: str,
    user_id: str,
    user_label: str,
    symbol: str | None,
    side: str | None,
    volume: float | None,
) -> bool:
    """Insert a row. Returns True on success, False otherwise. Never raises —
    the order has already landed at the broker, so we must not fail the request.
    """
    db = get_db()
    if not db:
        logger.warning("attribution: DB unavailable, skipping write for %s", broker_order_id)
        return False
    try:
        result = db.table("order_attributions").insert({
            "broker_order_id": broker_order_id,
            "broker_position_id": broker_position_id,
            "account_id": account_id,
            "user_id": user_id,
            "user_label": user_label,
            "symbol": symbol,
            "side": side,
            "volume": volume,
        }).execute()
        return bool(result.data)
    except Exception as e:
        logger.error("record_attribution failed for %s: %s", broker_order_id, e)
        return False


def fetch_labels_by_orders(order_ids: list[str]) -> dict[str, str]:
    """Return {broker_order_id: user_label} for the given ids. Missing ids
    are omitted from the result. Fails open — returns {} on DB error.
    """
    if not order_ids:
        return {}
    db = get_db()
    if not db:
        return {}
    try:
        result = db.table("order_attributions").select(
            "broker_order_id,user_label"
        ).in_("broker_order_id", order_ids).execute()
        return {row["broker_order_id"]: row["user_label"] for row in (result.data or [])}
    except Exception as e:
        logger.error("fetch_labels_by_orders: %s", e)
        return {}


def fetch_labels_by_positions(position_ids: list[str]) -> dict[str, str]:
    """Return {broker_position_id: user_label}. Same fail-open behavior."""
    if not position_ids:
        return {}
    db = get_db()
    if not db:
        return {}
    try:
        result = db.table("order_attributions").select(
            "broker_position_id,user_label"
        ).in_("broker_position_id", position_ids).execute()
        return {
            row["broker_position_id"]: row["user_label"]
            for row in (result.data or [])
            if row.get("broker_position_id")
        }
    except Exception as e:
        logger.error("fetch_labels_by_positions: %s", e)
        return {}


def backfill_position_id(broker_order_id: str, broker_position_id: str) -> None:
    """Set broker_position_id on an existing attribution row. Fire-and-forget.
    Used lazily from /api/trading/history when a pending order's position id
    wasn't known at placement time.
    """
    db = get_db()
    if not db:
        return
    try:
        db.table("order_attributions").update(
            {"broker_position_id": broker_position_id}
        ).eq("broker_order_id", broker_order_id).execute()
    except Exception as e:
        logger.warning("backfill_position_id(%s → %s): %s", broker_order_id, broker_position_id, e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_attribution.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/attribution.py backend/tests/test_attribution.py
git commit -m "feat(attribution): label freezing + DB helpers for shared-account orders"
```

---

## Task 3: Flip broker factory — unbound owners route to shared MetaApi

**Files:**
- Modify: `backend/app/services/broker_factory.py`
- Modify: `backend/tests/test_broker_factory.py`

- [ ] **Step 1: Update the existing factory test**

Read current test file first:

```bash
cat backend/tests/test_broker_factory.py
```

Replace the file with:

```python
"""broker_factory picks the right BrokerBase for an Owner."""

from unittest.mock import patch, MagicMock

from app.models.owner import Owner
from app.services.broker_factory import get_broker
from app.services.metaapi_broker import MetaApiBroker
from app.services.sandbox_broker import SandboxBroker


def _owner(metaapi_account_id=None, kind="user"):
    return Owner(id="u1", kind=kind, plan="free", metaapi_account_id=metaapi_account_id)


def test_bound_owner_routes_to_metaapi_with_their_account():
    broker = get_broker(_owner(metaapi_account_id="acc-bound"))
    assert isinstance(broker, MetaApiBroker)
    assert broker._account_id == "acc-bound"


def test_unbound_owner_routes_to_shared_metaapi_when_configured():
    mock_settings = MagicMock(metaapi_account_id="acc-shared")
    with patch("app.services.broker_factory.get_settings", return_value=mock_settings):
        broker = get_broker(_owner())
    assert isinstance(broker, MetaApiBroker)
    assert broker._account_id == "acc-shared"


def test_unbound_anon_also_routes_to_shared_metaapi():
    mock_settings = MagicMock(metaapi_account_id="acc-shared")
    with patch("app.services.broker_factory.get_settings", return_value=mock_settings):
        broker = get_broker(_owner(kind="anon"))
    assert isinstance(broker, MetaApiBroker)
    assert broker._account_id == "acc-shared"


def test_unbound_owner_falls_back_to_sandbox_when_metaapi_not_configured():
    mock_settings = MagicMock(metaapi_account_id="")
    with patch("app.services.broker_factory.get_settings", return_value=mock_settings):
        broker = get_broker(_owner())
    assert isinstance(broker, SandboxBroker)
```

- [ ] **Step 2: Run the test — expect failures**

Run: `cd backend && python -m pytest tests/test_broker_factory.py -v`
Expected: tests fail because current factory returns `SandboxBroker` for unbound owners.

- [ ] **Step 3: Update broker_factory.py**

Replace `backend/app/services/broker_factory.py` with:

```python
"""Factory picks the right BrokerBase for a given Owner.

Routing:
  - Bound (owner.metaapi_account_id non-null) → MetaApiBroker with that id.
  - Unbound but MetaApi configured → MetaApiBroker with settings.metaapi_account_id
    (the shared public account — see shared-public-account design doc).
  - Unbound with no MetaApi config → SandboxBroker (local-dev fallback).
"""

from app.config import get_settings
from app.models.owner import Owner
from app.services.broker_base import BrokerBase
from app.services.metaapi_broker import MetaApiBroker
from app.services.sandbox_broker import SandboxBroker


def get_broker(owner: Owner) -> BrokerBase:
    if owner.metaapi_account_id:
        return MetaApiBroker(owner.metaapi_account_id)
    settings = get_settings()
    if settings.metaapi_account_id:
        return MetaApiBroker(settings.metaapi_account_id)
    return SandboxBroker(owner)
```

- [ ] **Step 4: Run the test — expect pass**

Run: `cd backend && python -m pytest tests/test_broker_factory.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full backend suite — catch regressions**

Run: `cd backend && python -m pytest tests/ -v`
Expected: 0 new failures. Pre-existing failures (if any) should be unchanged. If any `test_sandbox_*` test fails because it didn't pass `metaapi_account_id=""`, update that test to patch `get_settings` with an empty `metaapi_account_id` so it still routes to sandbox.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/broker_factory.py backend/tests/test_broker_factory.py
git commit -m "feat(broker): unbound owners route to shared MetaApi demo"
```

---

## Task 4: Drop auth on 4 trading read endpoints

**Files:**
- Modify: `backend/app/api/routes.py` lines 663, 753, 768, 796

- [ ] **Step 1: Flip `Depends(require_user)` → `Depends(get_owner)` on 4 endpoints**

In `backend/app/api/routes.py`, edit exactly these 4 lines:

Line 663 — `trading_account`:
```python
async def trading_account(owner: Owner = Depends(get_owner)):
```

Line 753 — `trading_orders`:
```python
async def trading_orders(owner: Owner = Depends(get_owner)):
```

Line 768 — `trading_history`:
```python
async def trading_history(days: int = 30, owner: Owner = Depends(get_owner)):
```

Line 796 — `trading_account_info`:
```python
async def trading_account_info(owner: Owner = Depends(get_owner)):
```

Leave write endpoints (lines 687, 701, 711, 718, 737, 761) on `require_user`.

- [ ] **Step 2: Sanity-check the server boots**

Run: `cd backend && python -c "from app.main import app; print([r.path for r in app.routes if 'trading' in r.path])"`
Expected: prints the list of trading routes with no import errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "feat(api): trading read endpoints accept anonymous owners"
```

---

## Task 5: Write attribution on market orders

**Files:**
- Modify: `backend/app/api/routes.py:686-697`

- [ ] **Step 1: Replace `trading_place_order`**

Open `backend/app/api/routes.py` and replace the `trading_place_order` function (lines 686-697) with:

```python
@router.post("/api/trading/order")
async def trading_place_order(body: PlaceOrderInput, owner: Owner = Depends(require_user)):
    """Place a market order via the broker."""
    broker_impl = get_broker(owner)
    result = await broker_impl.place_market_order(
        symbol=body.symbol,
        side=body.side,
        volume=body.size,
        sl=body.stop_loss,
        tp=body.take_profit,
    )
    _record_order_attribution(owner, result, body.symbol, body.side, body.size)
    return _result_to_dict(result)
```

- [ ] **Step 2: Add the helper `_record_order_attribution` right after `_result_to_dict` (after line 108)**

```python
def _record_order_attribution(
    owner: Owner, result, symbol: str, side: str, volume: float,
) -> None:
    """Write an attribution row when a logged-in user places on the shared account.

    Skips when: order was rejected, owner is on their own bound account, or DB
    write fails (logged). Never raises — the order is already live at broker.
    """
    from app.config import get_settings
    from app.services.attribution import record_attribution, freeze_user_label
    from app.services.auth import get_user_by_id

    if not getattr(result, "success", False):
        return
    order_id = getattr(result, "order_id", None)
    if not order_id:
        return
    if owner.metaapi_account_id is not None:
        return  # user on their own account — no shared-account attribution
    settings = get_settings()
    if not settings.metaapi_account_id:
        return  # local dev without MetaApi — skip
    user = get_user_by_id(owner.id)
    if not user:
        logger.warning("attribution: user %s not found", owner.id)
        return
    record_attribution(
        broker_order_id=str(order_id),
        broker_position_id=None,  # market order — position id backfilled in history reads
        account_id=settings.metaapi_account_id,
        user_id=owner.id,
        user_label=freeze_user_label(user),
        symbol=symbol,
        side=side,
        volume=volume,
    )
```

Note: `OrderResult` (from `broker_types.py`) returns `order_id` on the dataclass. If the broker reports `positionId` in the raw dict, the backfill path in Task 7 will populate it. Do not try to extract it here — `OrderResult` currently exposes only `order_id`.

- [ ] **Step 3: Quick smoke — route still registers**

Run: `cd backend && python -c "from app.api.routes import router; print([r.path for r in router.routes if r.path=='/api/trading/order'])"`
Expected: `['/api/trading/order']`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "feat(api): attribute market orders on shared account"
```

---

## Task 6: Write attribution on pending orders

**Files:**
- Modify: `backend/app/api/routes.py:736-749`

- [ ] **Step 1: Replace `trading_pending_order`**

Open `backend/app/api/routes.py` and replace the `trading_pending_order` function (lines 736-749) with:

```python
@router.post("/api/trading/pending-order")
async def trading_pending_order(body: PendingOrderInput, owner: Owner = Depends(require_user)):
    """Place a limit or stop order."""
    broker_impl = get_broker(owner)
    result = await broker_impl.place_pending_order(
        symbol=body.symbol,
        side=body.side,
        volume=body.size,
        order_type=body.order_type,
        price=body.price,
        sl=body.stop_loss,
        tp=body.take_profit,
    )
    _record_order_attribution(owner, result, body.symbol, body.side, body.size)
    return _result_to_dict(result)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "feat(api): attribute pending orders on shared account"
```

---

## Task 7: Read path — attach `user_label` to positions/history/orders

**Files:**
- Modify: `backend/app/api/routes.py` — `trading_account`, `trading_orders`, `trading_history`

- [ ] **Step 1: Update `_position_to_dict` + `_order_to_dict` + `_trade_to_dict` to accept an optional label**

At the top of `backend/app/api/routes.py`, replace the three helper functions with:

```python
def _position_to_dict(p: PositionDTO, user_label: str | None = None) -> dict:
    return {
        "id": p.id,
        "symbol": p.symbol,
        "side": p.side,
        "volume": p.size,
        "entry_price": p.entry_price,
        "current_price": p.current_price,
        "profit": p.unrealized_pnl,
        "stop_loss": p.stop_loss,
        "take_profit": p.take_profit,
        "user_label": user_label,
    }


def _order_to_dict(o: OrderDTO, user_label: str | None = None) -> dict:
    return {
        "id": o.id,
        "symbol": o.symbol,
        "type": f"ORDER_TYPE_{o.side.upper()}_{o.order_type.upper()}",
        "side": o.side,
        "volume": o.size,
        "price": o.price,
        "stop_loss": o.stop_loss,
        "take_profit": o.take_profit,
        "user_label": user_label,
    }


def _trade_to_dict(t: ClosedTrade, user_label: str | None = None) -> dict:
    side = "buy" if t.side == "long" else "sell"
    return {
        "id": t.id,
        "symbol": t.symbol,
        "side": side,
        "type": "DEAL_TYPE_BUY" if t.side == "long" else "DEAL_TYPE_SELL",
        "volume": t.size,
        "price": t.exit_price,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "profit": t.pnl,
        "user_label": user_label,
    }
```

- [ ] **Step 2: Update `trading_account` to join labels**

Replace `trading_account` (lines 662-683) with:

```python
@router.get("/api/trading/account")
async def trading_account(owner: Owner = Depends(get_owner)):
    """Get trading account info + positions."""
    broker_impl = get_broker(owner)
    info = await broker_impl.account_info()
    positions = await broker_impl.positions()
    initial = 100000.0
    pnl = info.equity - initial
    labels = _labels_for_positions(owner, positions)
    return {
        "balance": info.balance,
        "equity": info.equity,
        "initial_balance": initial,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / initial * 100, 2) if initial > 0 else 0,
        "open_positions": len(positions),
        "total_trades": 0,
        "winning_trades": 0,
        "win_rate": 0,
        "positions": [_position_to_dict(p, labels.get(p.id)) for p in positions],
        "recent_trades": [],
        "source": "metaapi_mt5" if owner.metaapi_account_id or _shared_account_configured() else "sandbox",
    }
```

- [ ] **Step 3: Update `trading_orders` to join labels**

Replace `trading_orders` (lines 752-757) with:

```python
@router.get("/api/trading/orders")
async def trading_orders(owner: Owner = Depends(get_owner)):
    """Get all pending orders."""
    broker_impl = get_broker(owner)
    orders = await broker_impl.pending_orders()
    labels = _labels_for_orders(owner, [o.id for o in orders])
    return {"orders": [_order_to_dict(o, labels.get(o.id)) for o in orders]}
```

- [ ] **Step 4: Update `trading_history` to join + lazy-backfill positions**

Replace `trading_history` (lines 767-784) with:

```python
@router.get("/api/trading/history")
async def trading_history(days: int = 30, owner: Owner = Depends(get_owner)):
    """Get closed trade history."""
    broker_impl = get_broker(owner)
    trades_typed = await broker_impl.history(limit=100)
    labels = _labels_for_orders(owner, [t.id for t in trades_typed])
    trades = [_trade_to_dict(t, labels.get(t.id)) for t in trades_typed]
    total = len(trades)
    winners = sum(1 for t in trades if t.get("profit", 0) > 0)
    total_pnl = sum(t.get("profit", 0) for t in trades)
    return {
        "trades": trades,
        "stats": {
            "total_trades": total,
            "winning_trades": winners,
            "win_rate": round(winners / total * 100, 1) if total > 0 else 0,
            "total_pnl": round(total_pnl, 2),
        },
    }
```

- [ ] **Step 5: Add read-path helpers near the top of the file (after `_record_order_attribution`)**

```python
def _shared_account_configured() -> bool:
    from app.config import get_settings
    return bool(get_settings().metaapi_account_id)


def _labels_for_positions(owner: Owner, positions) -> dict[str, str]:
    """Return {position_id: user_label} for the shared-account read path.

    Returns empty dict for bound users — they're on their own MetaApi account
    and attribution does not apply. Frontend hides the By column when the map
    is empty AND all positions lack user_label.
    """
    if owner.metaapi_account_id is not None:
        return {}
    from app.services.attribution import fetch_labels_by_positions
    return fetch_labels_by_positions([p.id for p in positions if p.id])


def _labels_for_orders(owner: Owner, order_ids: list[str]) -> dict[str, str]:
    if owner.metaapi_account_id is not None:
        return {}
    from app.services.attribution import fetch_labels_by_orders
    return fetch_labels_by_orders([oid for oid in order_ids if oid])
```

- [ ] **Step 6: Smoke test**

Run: `cd backend && python -c "from app.api.routes import router; print('ok')"`
Expected: `ok`, no import errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "feat(api): join user_label into positions, orders, and history reads"
```

---

## Task 8: Briefing endpoint requires login; AI-analyze unchanged

**Files:**
- Modify: `backend/app/api/routes.py:327-345`

- [ ] **Step 1: Replace `get_briefing`**

Replace `get_briefing` (lines 327-345) with:

```python
@router.get("/api/accounts/{account_id}/briefing")
async def get_briefing(
    account_id: str, firm_name: str, account_size: int,
    _user: Owner = Depends(require_user),  # briefing requires login
    owner: Owner = Depends(require_quota("briefing")),
):
    """Generate a pre-market AI briefing for an account."""
    account_state = await broker.get_account_state(account_id, firm_name, account_size)
    if account_state is None:
        return {"status": "connecting", "message": "Broker not connected yet. Please wait."}

    report = evaluate_compliance(account_state)
    top = get_top_signals(5)

    briefing = await generate_ai_briefing(
        account_state, report, top, owner=owner, consume_quota=False,
    )

    import json as _json
    return _json.loads(_json.dumps(briefing, default=str))
```

Both `Depends(require_user)` and `Depends(require_quota("briefing"))` resolve the owner from the request; FastAPI dedupes the underlying `get_owner` so the owner is loaded once. `require_user` raises 401 before quota is checked for anons.

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "feat(api): AI briefing now requires login"
```

---

## Task 9: Sandbox reset is always 403

**Files:**
- Modify: `backend/app/api/routes.py:810-821`

- [ ] **Step 1: Replace `sandbox_reset`**

Replace `sandbox_reset` (lines 810-821) with:

```python
@router.post("/api/sandbox/reset")
async def sandbox_reset(owner: Owner = Depends(require_user)):
    """Account reset is disabled — both shared and bound accounts are real
    MetaApi demos. Kept as 403 rather than 410 so the frontend can render a
    tooltip via its existing error handler. See design doc §Broker routing."""
    raise HTTPException(
        status_code=403,
        detail="Account reset is not supported on real broker accounts",
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "feat(api): disable sandbox reset (real broker accounts are not resettable)"
```

---

## Task 10: Backend integration tests

**Files:**
- Create: `backend/tests/test_trading_routes_anon.py`

- [ ] **Step 1: Write the integration tests**

`backend/tests/test_trading_routes_anon.py`:

```python
"""Integration tests for anonymous trading reads + attributed writes.

Follows the fixture style in test_sandbox_endpoints.py — uses TestClient with
a mocked broker layer and a real Supabase client (or mocked via get_db patch).
"""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, ClosedTrade, OrderResult,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.account_info = AsyncMock(return_value=AccountInfo(
        balance=100000.0, equity=100500.0, margin=500.0,
        free_margin=99500.0, currency="USD",
    ))
    broker.positions = AsyncMock(return_value=[
        PositionDTO(
            id="pos1", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.10, current_price=1.105, unrealized_pnl=50.0,
            stop_loss=None, take_profit=None,
        ),
    ])
    broker.pending_orders = AsyncMock(return_value=[])
    broker.history = AsyncMock(return_value=[])
    broker.place_market_order = AsyncMock(return_value=OrderResult(
        success=True, order_id="order-123", message=None,
    ))
    return broker


def test_anon_can_read_account(client, mock_broker):
    with patch("app.api.routes.get_broker", return_value=mock_broker), \
         patch("app.api.routes._labels_for_positions", return_value={"pos1": "Mason"}):
        res = client.get("/api/trading/account")
    assert res.status_code == 200
    body = res.json()
    assert body["positions"][0]["user_label"] == "Mason"


def test_anon_cannot_place_order(client):
    res = client.post("/api/trading/order", json={
        "symbol": "EURUSD", "side": "buy", "size": 0.1,
    })
    assert res.status_code == 401


def test_anon_cannot_get_briefing(client):
    res = client.get(
        "/api/accounts/acc1/briefing",
        params={"firm_name": "ftmo", "account_size": 100000},
    )
    assert res.status_code == 401


def test_sandbox_reset_rejected_for_anon(client):
    res = client.post("/api/sandbox/reset")
    assert res.status_code == 401  # anon blocked by require_user before 403


def test_sandbox_reset_rejected_for_logged_in_unbound(client, logged_in_unbound_token):
    res = client.post(
        "/api/sandbox/reset",
        headers={"Authorization": f"Bearer {logged_in_unbound_token}"},
    )
    assert res.status_code == 403


def test_sandbox_reset_rejected_for_bound(client, logged_in_bound_token):
    res = client.post(
        "/api/sandbox/reset",
        headers={"Authorization": f"Bearer {logged_in_bound_token}"},
    )
    assert res.status_code == 403


def test_logged_in_shared_account_write_records_attribution(
    client, mock_broker, logged_in_unbound_token,
):
    recorded = []

    def _record(**kwargs):
        recorded.append(kwargs)
        return True

    with patch("app.api.routes.get_broker", return_value=mock_broker), \
         patch("app.services.attribution.record_attribution", side_effect=_record), \
         patch(
             "app.config.get_settings",
             return_value=MagicMock(metaapi_account_id="shared-acc"),
         ):
        res = client.post(
            "/api/trading/order",
            json={"symbol": "EURUSD", "side": "buy", "size": 0.1},
            headers={"Authorization": f"Bearer {logged_in_unbound_token}"},
        )
    assert res.status_code == 200
    assert len(recorded) == 1
    assert recorded[0]["broker_order_id"] == "order-123"
    assert recorded[0]["account_id"] == "shared-acc"
    assert recorded[0]["user_label"]  # non-empty


def test_logged_in_bound_account_write_does_not_record(
    client, mock_broker, logged_in_bound_token,
):
    recorded = []
    with patch("app.api.routes.get_broker", return_value=mock_broker), \
         patch("app.services.attribution.record_attribution", side_effect=lambda **kw: recorded.append(kw)):
        res = client.post(
            "/api/trading/order",
            json={"symbol": "EURUSD", "side": "buy", "size": 0.1},
            headers={"Authorization": f"Bearer {logged_in_bound_token}"},
        )
    assert res.status_code == 200
    assert recorded == []
```

- [ ] **Step 2: Write the token fixtures**

Add to the top of `backend/tests/test_trading_routes_anon.py`:

```python
@pytest.fixture
def logged_in_unbound_token():
    """JWT for a logged-in user with no bound MetaApi account."""
    import jwt, time
    from app.services.auth import JWT_SECRET, JWT_ALGORITHM
    user = {"id": "user-unbound", "email": "a@x.com", "name": "Alice", "tier": "free"}
    with patch("app.services.auth.db_get_user_by_email", return_value=user), \
         patch("app.services.auth.db_get_user_by_id", return_value=user):
        token = jwt.encode(
            {"user_id": user["id"], "email": user["email"], "exp": time.time() + 3600},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        yield token


@pytest.fixture
def logged_in_bound_token():
    """JWT for a logged-in user bound to a specific MetaApi account."""
    import jwt, time
    from app.services.auth import JWT_SECRET, JWT_ALGORITHM
    user = {
        "id": "user-bound", "email": "b@x.com", "name": "Bob", "tier": "pro",
        "metaapi_account_id": "acc-of-bob",
    }
    with patch("app.services.auth.db_get_user_by_email", return_value=user), \
         patch("app.services.auth.db_get_user_by_id", return_value=user):
        token = jwt.encode(
            {"user_id": user["id"], "email": user["email"], "exp": time.time() + 3600},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        yield token
```

If the above token fixtures don't authenticate because `verify_token` does a fresh DB lookup, move the `patch` block into each test that uses them — inspect `verify_token` in `backend/app/services/auth.py:89` to confirm.

- [ ] **Step 3: Run the tests**

Run: `cd backend && python -m pytest tests/test_trading_routes_anon.py -v`
Expected: 8 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_trading_routes_anon.py
git commit -m "test(api): anon trading reads + attributed writes + reset block"
```

---

## Task 11: Frontend — LoginModal + useLoginGate hook

**Files:**
- Create: `frontend/src/components/LoginModal.tsx`
- Create: `frontend/src/hooks/useLoginGate.ts`
- Modify: `frontend/src/app/providers.tsx`

- [ ] **Step 1: Read the existing modal pattern**

Read `frontend/src/components/UpgradeModal.tsx` to match styling. Read `frontend/src/hooks/useAuth.ts` for the login/register signatures.

- [ ] **Step 2: Check the Next.js guide**

Per `frontend/AGENTS.md`, before writing the modal consult:

```bash
ls /Users/hexin/code/test/last30days/frontend/node_modules/next/dist/docs/
```

Read any guide relevant to client components + dynamic imports. Do not use `"use client"` unless the guide says that's the right directive in this version.

- [ ] **Step 3: Write `useLoginGate.ts`**

`frontend/src/hooks/useLoginGate.ts`:

```ts
"use client";

import { create } from "zustand"; // NOTE: verify zustand is installed. If not, fall back to a React Context + useState pair in providers.tsx and export a hook that reads it.

type LoginGateState = {
  open: boolean;
  reason: string | null;
  openGate: (reason?: string) => void;
  closeGate: () => void;
};

export const useLoginGate = create<LoginGateState>((set) => ({
  open: false,
  reason: null,
  openGate: (reason = "") => set({ open: true, reason }),
  closeGate: () => set({ open: false, reason: null }),
}));
```

Before committing this file, check whether `zustand` is in `frontend/package.json`. Run:
`grep -E '"zustand"' frontend/package.json || echo "NOT INSTALLED"`

If NOT INSTALLED, replace the file with a Context-based implementation:

```ts
"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

type GateState = {
  open: boolean;
  reason: string | null;
  openGate: (reason?: string) => void;
  closeGate: () => void;
};

const Ctx = createContext<GateState | null>(null);

export function LoginGateProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  return (
    <Ctx.Provider
      value={{
        open,
        reason,
        openGate: (r) => { setOpen(true); setReason(r ?? null); },
        closeGate: () => { setOpen(false); setReason(null); },
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useLoginGate(): GateState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLoginGate must be used within LoginGateProvider");
  return v;
}
```

- [ ] **Step 4: Write `LoginModal.tsx`**

`frontend/src/components/LoginModal.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useLoginGate } from "@/hooks/useLoginGate";
import { useI18n } from "@/i18n/context";

export function LoginModal() {
  const { open, reason, closeGate } = useLoginGate();
  const { login } = useAuth();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    const result = await login(email, password);
    setSubmitting(false);
    if (result) {
      setErr(result);
    } else {
      closeGate();
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      role="dialog"
      aria-modal="true"
      onClick={closeGate}
    >
      <div
        className="bg-neutral-900 border border-neutral-700 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold mb-1">{t("auth.login_required_title")}</h2>
        {reason && <p className="text-sm text-neutral-400 mb-4">{reason}</p>}
        <form onSubmit={onSubmit} className="space-y-3">
          <input
            type="email" required autoFocus value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("auth.email")}
            className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-white"
          />
          <input
            type="password" required value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("auth.password")}
            className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-white"
          />
          {err && <p className="text-sm text-red-400">{err}</p>}
          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              className="px-4 py-2 text-sm rounded bg-neutral-700 hover:bg-neutral-600"
              onClick={closeGate}
            >
              {t("auth.cancel")}
            </button>
            <button
              type="submit" disabled={submitting}
              className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
            >
              {submitting ? t("auth.logging_in") : t("auth.login")}
            </button>
          </div>
          <p className="text-xs text-neutral-500 pt-2">
            {t("auth.no_account")}{" "}
            <a href="/login?mode=register" className="text-blue-400 hover:underline">
              {t("auth.register_cta")}
            </a>
          </p>
        </form>
      </div>
    </div>
  );
}
```

Note: `useAuth` hook is not yet a wrapper around `useAuthState`. Check `frontend/src/hooks/useAuth.ts` and `frontend/src/app/providers.tsx` — if `AuthContext` already exists, import `useAuth` from it. If only `useAuthState` exists, create `AuthProvider` + `useAuth` wrapping it in providers.tsx.

- [ ] **Step 5: Mount providers**

Read `frontend/src/app/providers.tsx`. Wrap children in `<LoginGateProvider>` (if context path chosen in Step 3) and render `<LoginModal />` at the bottom next to the existing `<UpgradeModal />`. Exact edit depends on providers.tsx contents — inspect before editing.

- [ ] **Step 6: Smoke test in dev**

```bash
cd frontend && npx next dev --port 3001
```

Open http://localhost:3001 in a browser. Verify dashboard loads with no console errors. Close dev server.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/LoginModal.tsx frontend/src/hooks/useLoginGate.ts frontend/src/app/providers.tsx
git commit -m "feat(frontend): LoginModal + useLoginGate for anon write gating"
```

---

## Task 12: Frontend — TradingPanel login gate

**Files:**
- Modify: `frontend/src/components/dashboard/TradingPanel.tsx`

- [ ] **Step 1: Find the order-submit and AI-analyze handlers**

```bash
grep -nE '/api/trading/order|/api/ai-trade|handleSubmit|onSubmit' frontend/src/components/dashboard/TradingPanel.tsx
```

Record the line numbers of: (1) the market-order submit, (2) the pending-order submit, (3) any AI-analyze button handler.

- [ ] **Step 2: Add the gate at the top of each handler**

At the top of TradingPanel, add:

```tsx
import { useAuth } from "@/hooks/useAuth";
import { useLoginGate } from "@/hooks/useLoginGate";
```

Inside the component:

```tsx
const { token } = useAuth();
const { openGate } = useLoginGate();
```

At the start of each side-effect handler, insert the gate:

```tsx
if (!token) {
  openGate(t("auth.login_to_place_order"));
  return;
}
```

For the AI-analyze handler use `t("auth.login_to_analyze")`.

- [ ] **Step 3: Smoke test in dev**

Open http://localhost:3001 without logging in. Click the Place Order button — the modal should open with the "login to place order" reason. Click elsewhere to close.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/TradingPanel.tsx
git commit -m "feat(frontend): login gate on order submit + AI analyze"
```

---

## Task 13: Frontend — Positions `By` column + login gate on close/modify

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/dashboard/PositionsTable.tsx`

- [ ] **Step 1: Extend `Position` type**

In `frontend/src/lib/types.ts`, replace the `Position` interface with:

```ts
export interface Position {
  id?: string;
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  opened_at: string;
  user_label?: string | null;
}
```

- [ ] **Step 2: Add `By` column**

In `frontend/src/components/dashboard/PositionsTable.tsx`, after line 30 (the PnL `<th>`), add:

```tsx
<th className="px-4 py-2 text-left">{t("positions.by")}</th>
```

After line 51 (the PnL `<td>`), add:

```tsx
<td className="px-4 py-2 text-xs text-zinc-400 truncate max-w-[120px]">
  {pos.user_label ?? "—"}
</td>
```

Column should only render when at least one position has a non-null `user_label` — check with:

```tsx
const showByColumn = positions.some((p) => p.user_label != null);
```

Guard both the `<th>` and `<td>` with `{showByColumn && ...}`. This hides the column in bound-user mode where the backend returns `user_label: null` for everything.

- [ ] **Step 3: Close-button login gate (if present)**

If PositionsTable has a Close / Modify button per row — it currently does not, per the file read — skip this step. Otherwise wrap their onClick handlers with the same `if (!token) { openGate(...); return; }` pattern from Task 12.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/PositionsTable.tsx frontend/src/lib/types.ts
git commit -m "feat(frontend): By column on positions table"
```

---

## Task 14: Frontend — Trade history `By` column

**Files:**
- Modify: `frontend/src/components/dashboard/AccountManager.tsx` (or the history subcomponent)

- [ ] **Step 1: Find the history rendering**

```bash
grep -nE 'recent_trades|trades|history' frontend/src/components/dashboard/AccountManager.tsx
```

Open the file and locate the closed-trades table.

- [ ] **Step 2: Add `user_label` to the trade row type**

Define near the top of AccountManager.tsx (if not already):

```ts
type ClosedDeal = {
  id: string;
  symbol: string;
  side: string;
  volume: number;
  entry_price: number;
  exit_price: number;
  profit: number;
  user_label?: string | null;
};
```

Adjust existing usage to match.

- [ ] **Step 3: Render the `By` column**

Mirror the Task 13 pattern: add one `<th>{t("positions.by")}</th>` and one `<td>{deal.user_label ?? "—"}</td>` cell. Guard with `const showByColumn = trades.some((d) => d.user_label != null)`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/AccountManager.tsx
git commit -m "feat(frontend): By column on trade history"
```

---

## Task 15: Frontend — BriefingPanel 401 fallback

**Files:**
- Modify: `frontend/src/components/dashboard/BriefingPanel.tsx`

- [ ] **Step 1: Find the briefing fetch**

```bash
grep -nE '/briefing|fetch|api\(' frontend/src/components/dashboard/BriefingPanel.tsx
```

- [ ] **Step 2: On 401, render login CTA instead of error**

In the fetch handler:

```tsx
import { useAuth } from "@/hooks/useAuth";
import { useLoginGate } from "@/hooks/useLoginGate";

// inside component
const { token } = useAuth();
const { openGate } = useLoginGate();
const [authRequired, setAuthRequired] = useState(false);

// in fetch catch
catch (e: any) {
  if (e?.status === 401) {
    setAuthRequired(true);
  } else {
    setError(e);
  }
}
```

Render placeholder when `authRequired`:

```tsx
if (authRequired) {
  return (
    <div className="bg-zinc-900 rounded-lg p-6 text-center">
      <p className="text-zinc-400 mb-3">{t("auth.login_to_view_briefing")}</p>
      <button
        className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white"
        onClick={() => openGate(t("auth.login_to_view_briefing"))}
      >
        {t("auth.login")}
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Skip the initial fetch when not logged in**

```tsx
useEffect(() => {
  if (!token) {
    setAuthRequired(true);
    return;
  }
  // existing fetch call
}, [token /* plus existing deps */]);
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/BriefingPanel.tsx
git commit -m "feat(frontend): briefing login CTA for anon viewers"
```

---

## Task 16: Frontend — AITrader login gate

**Files:**
- Modify: `frontend/src/components/dashboard/AITrader.tsx`

- [ ] **Step 1: Find the Start / Stop / Analyze handlers**

```bash
grep -nE '/api/ai-trade/(start|stop|analyze|execute)' frontend/src/components/dashboard/AITrader.tsx
```

- [ ] **Step 2: Gate each handler**

Add at the top:

```tsx
import { useAuth } from "@/hooks/useAuth";
import { useLoginGate } from "@/hooks/useLoginGate";
```

Use the same pattern:

```tsx
const { token } = useAuth();
const { openGate } = useLoginGate();

async function startSession() {
  if (!token) { openGate(t("auth.login_to_ai_trade")); return; }
  // existing logic
}
```

Apply to every handler that POSTs to `/api/ai-trade/*` (analyze, start, execute, stop). The `/api/ai-trade/tick` endpoint already accepts anon — do NOT gate that path.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/AITrader.tsx
git commit -m "feat(frontend): login gate on AI auto-trade actions"
```

---

## Task 17: Frontend — AccountHeader "Connect my account" CTA + reset button hidden

**Files:**
- Modify: `frontend/src/components/dashboard/AccountHeader.tsx`

- [ ] **Step 1: Add the connect-account CTA**

Read the file (69 lines). After the account title/selector block, add:

```tsx
import { useAuth } from "@/hooks/useAuth";
import { useLoginGate } from "@/hooks/useLoginGate";
import Link from "next/link";

// inside component
const { user, token } = useAuth();
const { openGate } = useLoginGate();

// NOTE: the exact Link import + syntax depends on this Next.js version.
// Check frontend/node_modules/next/dist/docs/ first.
```

Render near account controls:

```tsx
{token && !user?.metaapi_account_id && (
  <Link
    href="/settings/broker"
    className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white"
  >
    {t("auth.connect_your_account")}
  </Link>
)}
{!token && (
  <button
    onClick={() => openGate(t("auth.connect_your_account_cta"))}
    className="px-3 py-1.5 text-sm rounded bg-neutral-700 hover:bg-neutral-600 text-white"
  >
    {t("auth.login_to_connect")}
  </button>
)}
```

- [ ] **Step 2: Remove / hide any sandbox-reset button**

```bash
grep -nE 'sandbox.*reset|api/sandbox/reset' frontend/src/components/ -r
```

If a reset button is rendered anywhere, delete it — the backend now always returns 403 and there's no surface where reset is valid.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/AccountHeader.tsx frontend/src/components/dashboard/TradingPanel.tsx
git commit -m "feat(frontend): Connect-my-account CTA; remove sandbox-reset UI"
```

---

## Task 18: i18n keys (EN + ZH)

**Files:**
- Modify: `frontend/src/i18n/locales.ts`

- [ ] **Step 1: Read the existing structure**

```bash
head -100 frontend/src/i18n/locales.ts
```

- [ ] **Step 2: Add keys for both locales**

New keys under `en` and `zh` namespaces:

```ts
// en
"auth.login_required_title": "Login required",
"auth.email": "Email",
"auth.password": "Password",
"auth.login": "Log in",
"auth.logging_in": "Logging in…",
"auth.cancel": "Cancel",
"auth.no_account": "No account?",
"auth.register_cta": "Register",
"auth.login_to_place_order": "Log in to place an order on the shared account.",
"auth.login_to_analyze": "Log in to run AI analysis.",
"auth.login_to_view_briefing": "Log in to view today's AI briefing.",
"auth.login_to_ai_trade": "Log in to start an AI auto-trade session.",
"auth.connect_your_account": "Connect my account",
"auth.login_to_connect": "Log in to connect your account",
"auth.connect_your_account_cta": "Log in to connect your own broker account.",
"positions.by": "By",

// zh
"auth.login_required_title": "需要登录",
"auth.email": "邮箱",
"auth.password": "密码",
"auth.login": "登录",
"auth.logging_in": "登录中…",
"auth.cancel": "取消",
"auth.no_account": "没有账号？",
"auth.register_cta": "注册",
"auth.login_to_place_order": "登录后即可在公用账号上下单。",
"auth.login_to_analyze": "登录后可使用 AI 分析。",
"auth.login_to_view_briefing": "登录后查看今日 AI 简报。",
"auth.login_to_ai_trade": "登录后可启动 AI 自动交易。",
"auth.connect_your_account": "连接我的账户",
"auth.login_to_connect": "登录以连接自己的账户",
"auth.connect_your_account_cta": "登录后可连接自己的券商账户。",
"positions.by": "下单人",
```

Exact merge syntax depends on the locales.ts structure — inspect before editing.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales.ts
git commit -m "feat(i18n): keys for login gate + By column"
```

---

## Task 19: Frontend smoke — drive a headless browser through the flows

**Files:** (no code — uses the gstack `browse` skill)

Per `feedback_automate_smoke_tests.md`, every plan must include headless-browser verification rather than a "please manually test" step.

- [ ] **Step 1: Bring up dev servers**

```bash
cd backend && python -m uvicorn app.main:app --port 8001 &
cd frontend && npx next dev --port 3001 &
# wait until both respond
```

Check:
```bash
curl -s http://localhost:8001/api/health
curl -s -I http://localhost:3001 | head -1
```

Expected: backend returns `{"status": "ok"}` or similar; frontend returns `HTTP/1.1 200 OK`.

- [ ] **Step 2: Anon flow — view positions + By column**

Use the `browse` skill (or `mcp__claude-in-chrome__*` if the extension is connected):

1. Open http://localhost:3001 in a clean profile (no auth token in localStorage).
2. Take a screenshot of the dashboard. Verify: positions table visible, trade history visible. `By` column may be empty pre-feature — that's fine.
3. Click "Place Order". Verify: LoginModal opens. Screenshot.
4. Close the modal. Click "AI Briefing" area or its login CTA. Verify: placeholder renders.
5. Screenshot.

- [ ] **Step 3: Logged-in flow — place an order, see own `user_label`**

1. Register a test user via `/login?mode=register` (email: `smoketest+$(date +%s)@example.com`, password: `smoketest123`, name: `Smokey`).
2. Place a tiny EURUSD 0.01 market buy via the TradingPanel.
3. Wait 2 seconds, refresh the dashboard.
4. Verify the new position shows `By: Smokey` in the `By` column. Screenshot.
5. Verify the trade history (if any past deal flows through) also shows attribution for new rows.

- [ ] **Step 4: Kill dev servers**

```bash
pkill -f "uvicorn app.main" || true
pkill -f "next dev" || true
```

- [ ] **Step 5: Commit evidence**

Put screenshots in `docs/superpowers/evidence/2026-04-20-shared-public-account/`:

```bash
mkdir -p docs/superpowers/evidence/2026-04-20-shared-public-account
# (screenshots already saved there by browse skill)
git add docs/superpowers/evidence/2026-04-20-shared-public-account
git commit -m "test(smoke): headless browser evidence for shared public account"
```

---

## Task 20: Final regression sweep + backend suite

**Files:** (no code — validation only)

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: all tests pass. If a pre-existing test fails because it depended on `SandboxBroker` being returned for unbound owners, update that test to patch `get_settings` with `metaapi_account_id=""` so the factory falls back to sandbox. Do NOT weaken the new behavior to make old tests pass.

- [ ] **Step 2: Run frontend type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. Fix any `user_label` / `Position` type mismatches surfaced here.

- [ ] **Step 3: Final commit if any fixups needed**

```bash
git add -A
git commit -m "chore: fixup regressions surfaced by full test + type-check"
```

---

## Self-review

### Spec coverage

Every section of `2026-04-20-shared-public-account-anon-read-design.md`:

- Authorization matrix → Task 4 (4 read endpoints), Task 5 & 6 (writes unchanged — attribution added), Task 8 (briefing), Task 9 (sandbox reset).
- Broker routing → Task 3.
- Data model → Task 1 (migration), Task 2 (helpers).
- Write path → Task 5 (market) + Task 6 (pending) + `_record_order_attribution` helper.
- Read path → Task 7 (positions, orders, history join).
- Label freezing → Task 2, tested explicitly.
- Frontend LoginModal → Task 11.
- Frontend TradingPanel gate → Task 12.
- Positions / history `By` column → Task 13, Task 14.
- Briefing fallback → Task 15.
- AITrader gate → Task 16.
- AccountHeader connect CTA → Task 17.
- Sandbox reset UI hidden → Task 17.
- i18n → Task 18.
- Edge cases → lazy positionId backfill covered by `backfill_position_id` (available; hook into history read as a Task 7 follow-up if first-pass misses it).
- Testing → Task 2 (attribution unit), Task 10 (integration), Task 19 (browser smoke).

### Placeholder scan

No "TBD" / "TODO" / "implement later" / "handle edge cases". Every frontend task that depends on existing file contents calls out `grep` to locate the current shape before editing, so the agent doesn't guess at line numbers.

### Type consistency

- `record_attribution`, `fetch_labels_by_orders`, `fetch_labels_by_positions` all defined in Task 2 and consumed in Tasks 5, 6, 7.
- `_record_order_attribution` helper defined in Task 5, reused verbatim in Task 6.
- `_labels_for_positions`, `_labels_for_orders`, `_shared_account_configured` defined in Task 7.
- Frontend: `user_label` added to `Position` in Task 13, referenced in Task 13 rendering, consistent with `user_label` pattern used in Task 14.
- i18n keys in Task 18 match the `t("auth.*")` calls in Tasks 11, 12, 15, 16, 17.

### Caveat: implementation must check

- Whether `useAuth` is already a wrapper around `useAuthState` in providers.tsx. If not, Task 11 must add it.
- Whether `zustand` is installed. Fallback included in Task 11.
- Exact line number in AccountManager.tsx where the history table renders (Task 14).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-20-shared-public-account-anon-read.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
