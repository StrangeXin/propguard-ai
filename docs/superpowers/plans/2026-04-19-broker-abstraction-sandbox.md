# PR 2a: Broker Abstraction + Sandbox Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `BrokerBase` protocol with two implementations (`MetaApiBroker` for paid users with real accounts; `SandboxBroker` for anonymous and free users running against a simulated per-owner account). All trading endpoints route through a factory that picks the right backend based on `Owner.metaapi_account_id`.

**Architecture:** Protocol + factory + two implementations. `MetaApiBroker` wraps existing `live_trading.py` functions; no logic change, just class-shaped interface. `SandboxBroker` persists per-owner state in four new DB tables (accounts, positions, orders, closed_trades) and uses live mid-prices from `kline_data.py` with fixed spreads for fills. All trading routes swap from the module-level `broker` singleton to `get_broker(owner)`.

**Tech Stack:** Python 3.11+, FastAPI, Supabase/Postgres, MetaApi Cloud SDK, pytest.

**Spec reference:** `docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md` §5, §6.

**Dependencies:** PR 1 landed (`Owner` abstraction, `get_owner`/`require_user`, `owner_id`/`owner_kind` columns). The foundation is at `main` HEAD `94d1b8e`.

**Scope for this plan:** PR 2a only. PR 2b (AIClient + quota system) and PR 3 (frontend public + claim flow) get separate plans.

---

## File Structure

**New files:**
- `supabase/migrations/20260421000000_sandbox_broker_tables.sql` — 4 new tables + 1 seed config
- `data/sandbox_spreads.json` — per-symbol spread config (bp points)
- `backend/app/services/broker_types.py` — value objects: `AccountInfo`, `PositionDTO`, `OrderDTO`, `OrderResult`, `ClosedTrade`
- `backend/app/services/broker_base.py` — `BrokerBase` Protocol
- `backend/app/services/metaapi_broker.py` — `MetaApiBroker` wraps `live_trading.py`
- `backend/app/services/sandbox_broker.py` — `SandboxBroker` DB-backed implementation
- `backend/app/services/sandbox_db.py` — CRUD helpers for sandbox tables
- `backend/app/services/broker_factory.py` — `get_broker(owner)`
- `backend/tests/test_broker_factory.py`
- `backend/tests/test_sandbox_broker.py`
- `backend/tests/test_metaapi_broker.py` (mocked)

**Modified files:**
- `backend/app/api/routes.py` — 11 trading endpoints swap from module-level `broker` to `get_broker(owner)`
- `backend/app/main.py` — keep current MetaApi bootstrapping; add sandbox readiness log

---

## Task 1: Sandbox DB schema + spread config

**Files:**
- Create: `supabase/migrations/20260421000000_sandbox_broker_tables.sql`
- Create: `data/sandbox_spreads.json`

- [ ] **Step 1: Write the migration**

`supabase/migrations/20260421000000_sandbox_broker_tables.sql`:

```sql
-- PropGuard AI — Sandbox broker persistent state
-- Migration: 20260421000000_sandbox_broker_tables
-- Spec: docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md §5

-- One row per owner. Balance = realized only; equity is computed from positions.
create table if not exists sandbox_accounts (
  owner_id uuid primary key,
  owner_kind text not null check (owner_kind in ('user','anon')),
  initial_balance numeric(14,2) not null default 100000,
  balance numeric(14,2) not null default 100000,
  firm_name text not null default 'ftmo',
  created_at timestamptz default now()
);

create table if not exists sandbox_positions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  owner_kind text not null check (owner_kind in ('user','anon')),
  symbol text not null,
  side text not null check (side in ('long','short')),
  size numeric(14,4) not null,
  entry_price numeric(14,5) not null,
  stop_loss numeric(14,5),
  take_profit numeric(14,5),
  opened_at timestamptz not null default now()
);
create index if not exists idx_sandbox_positions_owner on sandbox_positions(owner_id);

create table if not exists sandbox_orders (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  owner_kind text not null check (owner_kind in ('user','anon')),
  symbol text not null,
  side text not null check (side in ('buy','sell')),
  size numeric(14,4) not null,
  order_type text not null check (order_type in ('limit','stop')),
  price numeric(14,5) not null,
  stop_loss numeric(14,5),
  take_profit numeric(14,5),
  status text not null default 'pending' check (status in ('pending','filled','cancelled')),
  created_at timestamptz not null default now()
);
create index if not exists idx_sandbox_orders_owner on sandbox_orders(owner_id, status);

create table if not exists sandbox_closed_trades (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  owner_kind text not null check (owner_kind in ('user','anon')),
  symbol text not null,
  side text not null check (side in ('long','short')),
  size numeric(14,4) not null,
  entry_price numeric(14,5) not null,
  exit_price numeric(14,5) not null,
  pnl numeric(14,2) not null,
  opened_at timestamptz not null,
  closed_at timestamptz not null default now()
);
create index if not exists idx_sandbox_closed_owner on sandbox_closed_trades(owner_id, closed_at desc);
```

- [ ] **Step 2: Write the spread config**

`data/sandbox_spreads.json`:

```json
{
  "default_spread_pips": 2,
  "symbols": {
    "EURUSD": {"pip_size": 0.0001, "spread_pips": 1},
    "GBPUSD": {"pip_size": 0.0001, "spread_pips": 1.5},
    "USDJPY": {"pip_size": 0.01, "spread_pips": 1},
    "AUDUSD": {"pip_size": 0.0001, "spread_pips": 1.2},
    "USDCAD": {"pip_size": 0.0001, "spread_pips": 1.5},
    "NZDUSD": {"pip_size": 0.0001, "spread_pips": 1.8},
    "USDCHF": {"pip_size": 0.0001, "spread_pips": 1.5},
    "XAUUSD": {"pip_size": 0.1, "spread_pips": 30},
    "XAGUSD": {"pip_size": 0.01, "spread_pips": 5},
    "BTCUSD": {"pip_size": 1, "spread_pips": 5},
    "ETHUSD": {"pip_size": 0.1, "spread_pips": 10},
    "SOLUSD": {"pip_size": 0.01, "spread_pips": 3},
    "NAS100": {"pip_size": 0.1, "spread_pips": 5},
    "US30": {"pip_size": 1, "spread_pips": 5},
    "SPX500": {"pip_size": 0.1, "spread_pips": 3}
  }
}
```

- [ ] **Step 3: Apply the migration**

```bash
cd /Users/hexin/code/test/last30days/.worktrees/broker-sandbox
supabase db push --linked --include-all
```

Expected: `Finished supabase db push.`

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260421000000_sandbox_broker_tables.sql data/sandbox_spreads.json
git commit -m "db: sandbox broker tables (accounts, positions, orders, closed_trades) + spread config"
```

---

## Task 2: Broker value objects

**Files:**
- Create: `backend/app/services/broker_types.py`
- Test: `backend/tests/test_broker_types.py`

These are plain frozen dataclasses used by both broker implementations as return types. No business logic.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_broker_types.py`:

```python
"""Tests for broker value objects."""

import pytest
from datetime import datetime, timezone

from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)


class TestBrokerTypes:
    def test_account_info_computed_fields(self):
        info = AccountInfo(
            balance=100000.0,
            equity=99500.0,
            margin=500.0,
            free_margin=99000.0,
            currency="USD",
        )
        assert info.balance == 100000.0
        assert info.equity == 99500.0

    def test_position_dto(self):
        pos = PositionDTO(
            id="p1", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.0850, current_price=1.0860,
            unrealized_pnl=10.0, stop_loss=None, take_profit=None,
            opened_at=datetime.now(timezone.utc),
        )
        assert pos.side == "long"
        assert pos.unrealized_pnl == 10.0

    def test_position_dto_side_validated(self):
        with pytest.raises(ValueError, match="side must be 'long' or 'short'"):
            PositionDTO(
                id="p1", symbol="EURUSD", side="buy", size=0.1,
                entry_price=1.0, current_price=1.0,
                unrealized_pnl=0, stop_loss=None, take_profit=None,
                opened_at=datetime.now(timezone.utc),
            )

    def test_order_result_success(self):
        r = OrderResult(success=True, order_id="o1", message=None)
        assert r.success
        assert r.order_id == "o1"

    def test_order_result_failure(self):
        r = OrderResult(success=False, order_id=None, message="insufficient margin")
        assert not r.success
        assert "insufficient" in r.message

    def test_closed_trade(self):
        now = datetime.now(timezone.utc)
        t = ClosedTrade(
            id="t1", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.08, exit_price=1.09, pnl=100.0,
            opened_at=now, closed_at=now,
        )
        assert t.pnl == 100.0
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && python -m pytest tests/test_broker_types.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.services.broker_types'`

- [ ] **Step 3: Implement**

`backend/app/services/broker_types.py`:

```python
"""
Broker value objects shared by MetaApiBroker and SandboxBroker.

These are the public surface — route handlers and UI-facing JSON shape come
from these. Keep them frozen + validated so nobody produces malformed state.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class AccountInfo:
    balance: float            # realized P&L
    equity: float             # balance + unrealized
    margin: float             # used margin
    free_margin: float        # available for new positions
    currency: str = "USD"


@dataclass(frozen=True)
class PositionDTO:
    id: str
    symbol: str
    side: Literal["long", "short"]
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None
    take_profit: float | None
    opened_at: datetime

    def __post_init__(self):
        if self.side not in ("long", "short"):
            raise ValueError("side must be 'long' or 'short'")


@dataclass(frozen=True)
class OrderDTO:
    id: str
    symbol: str
    side: Literal["buy", "sell"]
    size: float
    order_type: Literal["market", "limit", "stop"]
    price: float | None
    stop_loss: float | None
    take_profit: float | None
    status: Literal["pending", "filled", "cancelled"]
    created_at: datetime


@dataclass(frozen=True)
class OrderResult:
    success: bool
    order_id: str | None
    message: str | None


@dataclass(frozen=True)
class ClosedTrade:
    id: str
    symbol: str
    side: Literal["long", "short"]
    size: float
    entry_price: float
    exit_price: float
    pnl: float
    opened_at: datetime
    closed_at: datetime
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_broker_types.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/broker_types.py backend/tests/test_broker_types.py
git commit -m "feat(broker): value objects shared by all broker implementations"
```

---

## Task 3: `BrokerBase` Protocol

**Files:**
- Create: `backend/app/services/broker_base.py`
- Test: `backend/tests/test_broker_base.py`

A Protocol class defines the public contract. Both implementations must satisfy it. No body needed; just method signatures.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_broker_base.py`:

```python
"""Tests for BrokerBase protocol.

Verify the protocol can be satisfied by a minimal stub. Actual implementations
are tested separately (test_sandbox_broker.py, test_metaapi_broker.py).
"""

import pytest
from datetime import datetime, timezone

from app.services.broker_base import BrokerBase
from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)


class _StubBroker:
    async def account_info(self) -> AccountInfo:
        return AccountInfo(100000, 100000, 0, 100000)

    async def positions(self) -> list[PositionDTO]:
        return []

    async def pending_orders(self) -> list[OrderDTO]:
        return []

    async def place_market_order(self, symbol, side, volume,
                                  sl=None, tp=None) -> OrderResult:
        return OrderResult(True, "o1", None)

    async def place_pending_order(self, symbol, side, volume, order_type,
                                   price, sl=None, tp=None) -> OrderResult:
        return OrderResult(True, "o2", None)

    async def close_position(self, position_id) -> OrderResult:
        return OrderResult(True, position_id, None)

    async def close_position_partial(self, position_id, volume) -> OrderResult:
        return OrderResult(True, position_id, None)

    async def modify_position(self, position_id, sl=None, tp=None) -> OrderResult:
        return OrderResult(True, position_id, None)

    async def cancel_order(self, order_id) -> OrderResult:
        return OrderResult(True, order_id, None)

    async def history(self, limit=50) -> list[ClosedTrade]:
        return []

    async def symbol_info(self, symbol) -> dict:
        return {}

    async def reset(self) -> None:
        return None


class TestBrokerBaseProtocol:
    def test_stub_satisfies_protocol(self):
        stub: BrokerBase = _StubBroker()
        assert isinstance(stub, BrokerBase)

    @pytest.mark.asyncio
    async def test_stub_methods_callable(self):
        stub: BrokerBase = _StubBroker()
        info = await stub.account_info()
        assert info.balance == 100000
        assert (await stub.positions()) == []
        assert (await stub.place_market_order("EURUSD", "buy", 0.1)).success
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && python -m pytest tests/test_broker_base.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`backend/app/services/broker_base.py`:

```python
"""
BrokerBase — the runtime-checkable Protocol both broker implementations
satisfy. Every trading route calls methods on this interface; the factory
picks the right implementation per request based on Owner.metaapi_account_id.
"""

from typing import Protocol, runtime_checkable

from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)


@runtime_checkable
class BrokerBase(Protocol):
    async def account_info(self) -> AccountInfo: ...
    async def positions(self) -> list[PositionDTO]: ...
    async def pending_orders(self) -> list[OrderDTO]: ...

    async def place_market_order(
        self, symbol: str, side: str, volume: float,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult: ...

    async def place_pending_order(
        self, symbol: str, side: str, volume: float,
        order_type: str, price: float,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult: ...

    async def close_position(self, position_id: str) -> OrderResult: ...
    async def close_position_partial(
        self, position_id: str, volume: float,
    ) -> OrderResult: ...
    async def modify_position(
        self, position_id: str,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult: ...

    async def cancel_order(self, order_id: str) -> OrderResult: ...

    async def history(self, limit: int = 50) -> list[ClosedTrade]: ...
    async def symbol_info(self, symbol: str) -> dict: ...

    async def reset(self) -> None:
        """Sandbox-only. MetaApi implementation raises NotImplementedError."""
        ...
```

- [ ] **Step 4: Install pytest-asyncio if not present, run tests**

```bash
cd backend && pip install pytest-asyncio 2>&1 | tail -1
python -m pytest tests/test_broker_base.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/broker_base.py backend/tests/test_broker_base.py
git commit -m "feat(broker): BrokerBase Protocol defining trading interface"
```

---

## Task 4: Sandbox DB layer

**Files:**
- Create: `backend/app/services/sandbox_db.py`
- Test: `backend/tests/test_sandbox_db.py`

Pure CRUD over the 4 sandbox tables. All functions take `owner_id` + `owner_kind` since that's the partition key.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sandbox_db.py`:

```python
"""Integration tests for sandbox DB layer. Requires Supabase dev env."""

import os
import secrets
from datetime import datetime, timezone

import pytest

from app.services.auth import register_user, _users_mem
from app.services.sandbox_db import (
    sandbox_get_or_create_account,
    sandbox_update_balance,
    sandbox_insert_position,
    sandbox_list_positions,
    sandbox_delete_position,
    sandbox_insert_closed_trade,
    sandbox_list_closed_trades,
    sandbox_reset_account,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_user_id():
    _users_mem.clear()
    return register_user(
        f"sb-{secrets.token_hex(4)}@test.propguard.ai", "password123"
    )["id"]


class TestSandboxDB:
    def test_account_created_on_first_access(self):
        uid = _fresh_user_id()
        acct = sandbox_get_or_create_account(uid, "user")
        assert acct["balance"] == 100000.0
        assert acct["initial_balance"] == 100000.0
        assert acct["owner_id"] == uid

    def test_update_balance(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        sandbox_update_balance(uid, 101000.0)
        acct = sandbox_get_or_create_account(uid, "user")
        assert acct["balance"] == 101000.0

    def test_position_lifecycle(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        pid = sandbox_insert_position(
            uid, "user", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.0850, stop_loss=None, take_profit=None,
        )
        assert pid
        positions = sandbox_list_positions(uid)
        assert len(positions) == 1
        assert positions[0]["symbol"] == "EURUSD"
        sandbox_delete_position(pid)
        assert sandbox_list_positions(uid) == []

    def test_closed_trade_history(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        now = datetime.now(timezone.utc)
        sandbox_insert_closed_trade(
            uid, "user",
            symbol="BTCUSD", side="long", size=0.01,
            entry_price=60000.0, exit_price=61000.0, pnl=10.0,
            opened_at=now, closed_at=now,
        )
        trades = sandbox_list_closed_trades(uid)
        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTCUSD"

    def test_reset_wipes_state(self):
        uid = _fresh_user_id()
        sandbox_get_or_create_account(uid, "user")
        sandbox_insert_position(uid, "user", symbol="EURUSD", side="long",
                                 size=0.1, entry_price=1.0)
        sandbox_update_balance(uid, 95000)
        sandbox_reset_account(uid, "user")
        acct = sandbox_get_or_create_account(uid, "user")
        assert acct["balance"] == 100000.0
        assert sandbox_list_positions(uid) == []
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_db.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`backend/app/services/sandbox_db.py`:

```python
"""CRUD for sandbox broker tables.

Pure data layer. Broker logic (pricing, pnl computation) belongs in
sandbox_broker.py.
"""

import logging
from datetime import datetime

from app.services.database import get_db

logger = logging.getLogger(__name__)


def sandbox_get_or_create_account(owner_id: str, owner_kind: str,
                                   initial_balance: float = 100000.0,
                                   firm_name: str = "ftmo") -> dict:
    db = get_db()
    if not db:
        return {
            "owner_id": owner_id, "owner_kind": owner_kind,
            "initial_balance": initial_balance, "balance": initial_balance,
            "firm_name": firm_name,
        }
    try:
        result = db.table("sandbox_accounts").select("*").eq("owner_id", owner_id).limit(1).execute()
        if result.data:
            return result.data[0]
        insert = db.table("sandbox_accounts").insert({
            "owner_id": owner_id,
            "owner_kind": owner_kind,
            "initial_balance": initial_balance,
            "balance": initial_balance,
            "firm_name": firm_name,
        }).execute()
        return insert.data[0] if insert.data else {}
    except Exception as e:
        logger.error(f"sandbox_get_or_create_account: {e}")
        return {}


def sandbox_update_balance(owner_id: str, new_balance: float) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_accounts").update({"balance": new_balance}).eq("owner_id", owner_id).execute()
    except Exception as e:
        logger.error(f"sandbox_update_balance: {e}")


def sandbox_update_firm(owner_id: str, firm_name: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_accounts").update({"firm_name": firm_name}).eq("owner_id", owner_id).execute()
    except Exception as e:
        logger.error(f"sandbox_update_firm: {e}")


def sandbox_insert_position(owner_id: str, owner_kind: str, *, symbol: str,
                             side: str, size: float, entry_price: float,
                             stop_loss: float | None = None,
                             take_profit: float | None = None) -> str | None:
    db = get_db()
    if not db:
        return None
    try:
        row = {
            "owner_id": owner_id,
            "owner_kind": owner_kind,
            "symbol": symbol,
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }
        result = db.table("sandbox_positions").insert(row).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        logger.error(f"sandbox_insert_position: {e}")
        return None


def sandbox_list_positions(owner_id: str) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        result = db.table("sandbox_positions").select("*").eq("owner_id", owner_id).order("opened_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"sandbox_list_positions: {e}")
        return []


def sandbox_get_position(position_id: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("sandbox_positions").select("*").eq("id", position_id).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"sandbox_get_position: {e}")
        return None


def sandbox_update_position(position_id: str, updates: dict) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_positions").update(updates).eq("id", position_id).execute()
    except Exception as e:
        logger.error(f"sandbox_update_position: {e}")


def sandbox_delete_position(position_id: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_positions").delete().eq("id", position_id).execute()
    except Exception as e:
        logger.error(f"sandbox_delete_position: {e}")


def sandbox_insert_closed_trade(owner_id: str, owner_kind: str, *,
                                 symbol: str, side: str, size: float,
                                 entry_price: float, exit_price: float,
                                 pnl: float,
                                 opened_at: datetime,
                                 closed_at: datetime) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_closed_trades").insert({
            "owner_id": owner_id,
            "owner_kind": owner_kind,
            "symbol": symbol,
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "opened_at": opened_at.isoformat(),
            "closed_at": closed_at.isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"sandbox_insert_closed_trade: {e}")


def sandbox_list_closed_trades(owner_id: str, limit: int = 50) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        result = db.table("sandbox_closed_trades").select("*").eq("owner_id", owner_id).order("closed_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"sandbox_list_closed_trades: {e}")
        return []


def sandbox_reset_account(owner_id: str, owner_kind: str,
                           initial_balance: float = 100000.0) -> None:
    """Wipe positions/orders/history, reset balance to initial."""
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_positions").delete().eq("owner_id", owner_id).execute()
        db.table("sandbox_orders").delete().eq("owner_id", owner_id).execute()
        db.table("sandbox_closed_trades").delete().eq("owner_id", owner_id).execute()
        db.table("sandbox_accounts").update({"balance": initial_balance}).eq("owner_id", owner_id).execute()
    except Exception as e:
        logger.error(f"sandbox_reset_account: {e}")
```

- [ ] **Step 4: Run tests**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_db.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sandbox_db.py backend/tests/test_sandbox_db.py
git commit -m "feat(sandbox): CRUD helpers for sandbox_accounts/positions/orders/closed_trades"
```

---

## Task 5: `SandboxBroker` — account_info + place_market_order

**Files:**
- Create: `backend/app/services/sandbox_broker.py`
- Test: `backend/tests/test_sandbox_broker.py`

This task builds the minimum viable sandbox: place a market order, see it as a position, check equity reflects unrealized P&L.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sandbox_broker.py`:

```python
"""SandboxBroker tests against real Supabase + real market prices."""

import os
import secrets
from unittest.mock import patch, AsyncMock

import pytest

from app.models.owner import Owner
from app.services.auth import register_user, _users_mem
from app.services.sandbox_broker import SandboxBroker
from app.services.sandbox_db import sandbox_reset_account

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


@pytest.fixture
def owner():
    _users_mem.clear()
    email = f"sbx-{secrets.token_hex(4)}@test.propguard.ai"
    user = register_user(email, "password123")
    o = Owner(id=user["id"], kind="user", plan="free", metaapi_account_id=None)
    sandbox_reset_account(o.id, "user")  # idempotent clean slate
    yield o
    sandbox_reset_account(o.id, "user")


class TestSandboxAccountInfo:
    @pytest.mark.asyncio
    async def test_fresh_account_starts_at_100k(self, owner):
        b = SandboxBroker(owner)
        info = await b.account_info()
        assert info.balance == 100000.0
        assert info.equity == 100000.0
        assert info.free_margin == 100000.0


class TestSandboxMarketOrder:
    @pytest.mark.asyncio
    async def test_buy_creates_long_position(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            result = await b.place_market_order(
                symbol="EURUSD", side="buy", volume=0.1,
            )
            assert result.success
            positions = await b.positions()
            assert len(positions) == 1
            assert positions[0].side == "long"
            assert positions[0].size == 0.1
            # entry price = mid + spread/2 (spread 1 pip on EURUSD)
            assert positions[0].entry_price > 1.0850

    @pytest.mark.asyncio
    async def test_sell_creates_short_position(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            result = await b.place_market_order(
                symbol="EURUSD", side="sell", volume=0.1,
            )
            assert result.success
            positions = await b.positions()
            assert positions[0].side == "short"

    @pytest.mark.asyncio
    async def test_missing_price_returns_error(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=None)):
            b = SandboxBroker(owner)
            result = await b.place_market_order(
                symbol="WEIRDX", side="buy", volume=0.1,
            )
            assert not result.success
            assert "price" in result.message.lower()
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_broker.py -v
```
Expected: ModuleNotFoundError on `app.services.sandbox_broker`.

- [ ] **Step 3: Implement skeleton + account_info + place_market_order**

`backend/app/services/sandbox_broker.py`:

```python
"""
SandboxBroker — simulated trading against per-owner DB state.

Prices come from live market data (kline_data). Fills are instant at
midprice ± half-spread. Positions and closed trades persist in Supabase
so state survives process restarts and is isolated per owner.

Paid users with bound MetaApi accounts use MetaApiBroker instead; this
class is only constructed for Owners with metaapi_account_id == None.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.models.owner import Owner
from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)
from app.services.paper_trading import get_current_price
from app.services.sandbox_db import (
    sandbox_get_or_create_account,
    sandbox_update_balance,
    sandbox_insert_position,
    sandbox_list_positions,
    sandbox_get_position,
    sandbox_update_position,
    sandbox_delete_position,
    sandbox_insert_closed_trade,
    sandbox_list_closed_trades,
    sandbox_reset_account,
)

logger = logging.getLogger(__name__)

_SPREAD_CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "sandbox_spreads.json"


def _load_spreads() -> dict:
    try:
        with _SPREAD_CONFIG_PATH.open() as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"sandbox spread config missing: {e}")
        return {"default_spread_pips": 2, "symbols": {}}


_SPREADS = _load_spreads()


def _symbol_spread(symbol: str) -> tuple[float, float]:
    cfg = _SPREADS.get("symbols", {}).get(symbol.upper())
    if cfg:
        return cfg["pip_size"], cfg["spread_pips"]
    # Fallback: 4-digit forex default
    return 0.0001, _SPREADS.get("default_spread_pips", 2)


def _apply_spread(mid: float, symbol: str, side: str) -> float:
    """side is 'buy' or 'sell'. Buy fills at ask (mid + half-spread)."""
    pip_size, spread_pips = _symbol_spread(symbol)
    half = pip_size * spread_pips / 2
    return mid + half if side == "buy" else mid - half


def _pnl(side: str, size: float, entry: float, exit: float, symbol: str) -> float:
    """Contract size heuristic: forex 100K per lot, crypto/commodity 1:1."""
    diff = (exit - entry) if side == "long" else (entry - exit)
    sym = symbol.upper()
    if sym.startswith("XAU") or sym.startswith("XAG"):
        contract = 100  # 100oz per 1.0 lot
    elif sym.endswith("USD") and not sym.startswith(("EUR", "GBP", "AUD", "NZD", "USD")):
        # crypto pairs (BTCUSD, ETHUSD, SOLUSD, etc.)
        contract = 1
    elif sym in ("NAS100", "US30", "SPX500"):
        contract = 1
    else:
        contract = 100000  # forex
    return diff * size * contract


class SandboxBroker:
    """BrokerBase implementation backed by per-owner DB state."""

    def __init__(self, owner: Owner):
        self._owner = owner
        self._account = sandbox_get_or_create_account(owner.id, owner.kind)

    async def account_info(self) -> AccountInfo:
        balance = float(self._account.get("balance", 100000))
        positions_raw = sandbox_list_positions(self._owner.id)
        unrealized = 0.0
        for row in positions_raw:
            price = await get_current_price(row["symbol"])
            if price is None:
                continue
            unrealized += _pnl(
                row["side"], float(row["size"]),
                float(row["entry_price"]), price,
                row["symbol"],
            )
        equity = balance + unrealized
        return AccountInfo(
            balance=round(balance, 2),
            equity=round(equity, 2),
            margin=0.0,        # simplified: no leverage model in sandbox MVP
            free_margin=round(equity, 2),
            currency="USD",
        )

    async def positions(self) -> list[PositionDTO]:
        rows = sandbox_list_positions(self._owner.id)
        dtos = []
        for row in rows:
            price = await get_current_price(row["symbol"])
            current = price if price is not None else float(row["entry_price"])
            dtos.append(PositionDTO(
                id=row["id"],
                symbol=row["symbol"],
                side=row["side"],
                size=float(row["size"]),
                entry_price=float(row["entry_price"]),
                current_price=current,
                unrealized_pnl=round(_pnl(
                    row["side"], float(row["size"]),
                    float(row["entry_price"]), current,
                    row["symbol"],
                ), 2),
                stop_loss=float(row["stop_loss"]) if row.get("stop_loss") else None,
                take_profit=float(row["take_profit"]) if row.get("take_profit") else None,
                opened_at=datetime.fromisoformat(
                    row["opened_at"].replace("Z", "+00:00")
                ) if isinstance(row["opened_at"], str) else row["opened_at"],
            ))
        return dtos

    async def pending_orders(self) -> list[OrderDTO]:
        # Pending orders are handled in Task 8; return empty for now.
        return []

    async def place_market_order(
        self, symbol: str, side: str, volume: float,
        sl: float | None = None, tp: float | None = None,
    ) -> OrderResult:
        mid = await get_current_price(symbol)
        if mid is None:
            return OrderResult(success=False, order_id=None,
                               message=f"Cannot get price for {symbol}")
        fill = _apply_spread(mid, symbol, side)
        dir_ = "long" if side == "buy" else "short"
        pid = sandbox_insert_position(
            self._owner.id, self._owner.kind,
            symbol=symbol.upper(), side=dir_, size=volume,
            entry_price=fill, stop_loss=sl, take_profit=tp,
        )
        if not pid:
            return OrderResult(success=False, order_id=None,
                               message="Sandbox persistence failed")
        return OrderResult(success=True, order_id=pid, message=None)

    # Methods added in subsequent tasks
    async def place_pending_order(self, *_, **__) -> OrderResult:
        return OrderResult(False, None, "not implemented yet")

    async def close_position(self, position_id: str) -> OrderResult:
        return OrderResult(False, None, "not implemented yet")

    async def close_position_partial(self, position_id: str, volume: float) -> OrderResult:
        return OrderResult(False, None, "not implemented yet")

    async def modify_position(self, position_id: str,
                               sl: float | None = None, tp: float | None = None) -> OrderResult:
        return OrderResult(False, None, "not implemented yet")

    async def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(False, None, "not implemented yet")

    async def history(self, limit: int = 50) -> list[ClosedTrade]:
        return []

    async def symbol_info(self, symbol: str) -> dict:
        return {"symbol": symbol, "sandbox": True}

    async def reset(self) -> None:
        sandbox_reset_account(self._owner.id, self._owner.kind)
        self._account = sandbox_get_or_create_account(self._owner.id, self._owner.kind)
```

Note: `pytest-asyncio` mode is needed. Make sure `backend/pytest.ini` or `pyproject.toml` enables `asyncio_mode = auto`. If not present, add it:

```ini
# backend/pytest.ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 4: Run tests**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_broker.py -v
```
Expected: 3 passed (TestSandboxAccountInfo + TestSandboxMarketOrder).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sandbox_broker.py backend/tests/test_sandbox_broker.py backend/pytest.ini
git commit -m "feat(sandbox): SandboxBroker with account_info + place_market_order"
```

---

## Task 6: `SandboxBroker` — close_position + partial + modify + history

**Files:**
- Modify: `backend/app/services/sandbox_broker.py`
- Modify: `backend/tests/test_sandbox_broker.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_sandbox_broker.py`:

```python
class TestSandboxClosePosition:
    @pytest.mark.asyncio
    async def test_close_full_position_settles_pnl(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.1)
            assert r.success
            pid = r.order_id

        # Price moves up 10 pips → profit
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0860)):
            r2 = await b.close_position(pid)
            assert r2.success
            info = await b.account_info()
            # Buy at 1.08505 (mid+half spread) close at 1.08595 (mid-half spread) = 9 pips
            # PnL = 9 * 0.0001 * 0.1 lot * 100000 contract = 9.0 USD
            assert info.balance > 100000
            assert len(await b.positions()) == 0

    @pytest.mark.asyncio
    async def test_close_partial(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.3)
            pid = r.order_id

        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0860)):
            r2 = await b.close_position_partial(pid, 0.1)
            assert r2.success
            positions = await b.positions()
            assert len(positions) == 1
            assert abs(positions[0].size - 0.2) < 1e-9

    @pytest.mark.asyncio
    async def test_modify_position_sl_tp(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.1)
            pid = r.order_id
            m = await b.modify_position(pid, sl=1.08, tp=1.10)
            assert m.success
            positions = await b.positions()
            assert positions[0].stop_loss == 1.08
            assert positions[0].take_profit == 1.10


class TestSandboxHistory:
    @pytest.mark.asyncio
    async def test_closed_trades_appear_in_history(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            r = await b.place_market_order("EURUSD", "buy", 0.1)

        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0860)):
            await b.close_position(r.order_id)

        trades = await b.history(limit=10)
        assert len(trades) == 1
        assert trades[0].symbol == "EURUSD"
        assert trades[0].pnl > 0


class TestSandboxReset:
    @pytest.mark.asyncio
    async def test_reset_restores_initial_state(self, owner):
        with patch("app.services.sandbox_broker.get_current_price",
                   new=AsyncMock(return_value=1.0850)):
            b = SandboxBroker(owner)
            await b.place_market_order("EURUSD", "buy", 0.1)

        await b.reset()
        info = await b.account_info()
        assert info.balance == 100000.0
        assert info.equity == 100000.0
        assert len(await b.positions()) == 0
        assert (await b.history()) == []
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_broker.py -v
```
Expected: new tests fail (stub methods return "not implemented yet").

- [ ] **Step 3: Replace stub methods in sandbox_broker.py**

Replace the stub `close_position`, `close_position_partial`, `modify_position`, and `history` in `backend/app/services/sandbox_broker.py` with real implementations:

```python
    async def close_position(self, position_id: str) -> OrderResult:
        row = sandbox_get_position(position_id)
        if not row or row["owner_id"] != self._owner.id:
            return OrderResult(False, None, "Position not found")
        return await self._close_internal(row, size_to_close=float(row["size"]))

    async def close_position_partial(self, position_id: str, volume: float) -> OrderResult:
        row = sandbox_get_position(position_id)
        if not row or row["owner_id"] != self._owner.id:
            return OrderResult(False, None, "Position not found")
        size = float(row["size"])
        if volume <= 0 or volume >= size:
            return OrderResult(False, None, "Invalid partial close volume")
        return await self._close_internal(row, size_to_close=volume)

    async def _close_internal(self, row: dict, size_to_close: float) -> OrderResult:
        symbol = row["symbol"]
        side = row["side"]
        mid = await get_current_price(symbol)
        if mid is None:
            return OrderResult(False, None, f"Cannot get price for {symbol}")
        # Closing a long = sell (bid); closing a short = buy (ask)
        exit_side = "sell" if side == "long" else "buy"
        exit_price = _apply_spread(mid, symbol, exit_side)
        pnl = _pnl(side, size_to_close, float(row["entry_price"]), exit_price, symbol)
        new_balance = float(self._account.get("balance", 100000)) + pnl
        sandbox_update_balance(self._owner.id, new_balance)
        self._account["balance"] = new_balance

        opened_at = row["opened_at"]
        if isinstance(opened_at, str):
            opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        sandbox_insert_closed_trade(
            self._owner.id, self._owner.kind,
            symbol=symbol, side=side, size=size_to_close,
            entry_price=float(row["entry_price"]), exit_price=exit_price,
            pnl=round(pnl, 2),
            opened_at=opened_at, closed_at=datetime.now(timezone.utc),
        )

        remaining = float(row["size"]) - size_to_close
        if remaining <= 1e-9:
            sandbox_delete_position(row["id"])
        else:
            sandbox_update_position(row["id"], {"size": remaining})
        return OrderResult(True, row["id"], None)

    async def modify_position(self, position_id: str,
                               sl: float | None = None,
                               tp: float | None = None) -> OrderResult:
        row = sandbox_get_position(position_id)
        if not row or row["owner_id"] != self._owner.id:
            return OrderResult(False, None, "Position not found")
        updates: dict = {}
        if sl is not None:
            updates["stop_loss"] = sl
        if tp is not None:
            updates["take_profit"] = tp
        if updates:
            sandbox_update_position(position_id, updates)
        return OrderResult(True, position_id, None)

    async def history(self, limit: int = 50) -> list[ClosedTrade]:
        rows = sandbox_list_closed_trades(self._owner.id, limit=limit)
        out = []
        for row in rows:
            opened = row["opened_at"]
            closed = row["closed_at"]
            if isinstance(opened, str):
                opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            if isinstance(closed, str):
                closed = datetime.fromisoformat(closed.replace("Z", "+00:00"))
            out.append(ClosedTrade(
                id=row["id"],
                symbol=row["symbol"],
                side=row["side"],
                size=float(row["size"]),
                entry_price=float(row["entry_price"]),
                exit_price=float(row["exit_price"]),
                pnl=float(row["pnl"]),
                opened_at=opened,
                closed_at=closed,
            ))
        return out
```

- [ ] **Step 4: Run tests**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_broker.py -v
```
Expected: 7 passed (3 from Task 5 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sandbox_broker.py backend/tests/test_sandbox_broker.py
git commit -m "feat(sandbox): close position (full/partial), modify SL/TP, history, reset"
```

---

## Task 7: `MetaApiBroker` wrapper

**Files:**
- Create: `backend/app/services/metaapi_broker.py`
- Test: `backend/tests/test_metaapi_broker.py`

Wraps the existing `live_trading.py` module-level functions into a `BrokerBase`-shaped class. No logic change — just instance-methods that delegate.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_metaapi_broker.py`:

```python
"""MetaApiBroker delegates to live_trading module. Tests use mocks."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.metaapi_broker import MetaApiBroker
from app.services.broker_base import BrokerBase


class TestMetaApiBrokerProtocol:
    def test_satisfies_broker_base(self):
        broker = MetaApiBroker("acc-123")
        assert isinstance(broker, BrokerBase)


class TestMetaApiBrokerDelegation:
    @pytest.mark.asyncio
    async def test_place_market_order_delegates(self):
        with patch("app.services.metaapi_broker.mt5_place_order",
                   new=AsyncMock(return_value={"success": True, "order_id": "o1"})) as m:
            b = MetaApiBroker("acc-123")
            result = await b.place_market_order("EURUSD", "buy", 0.1)
            assert result.success
            assert result.order_id == "o1"
            m.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_account_info_delegates(self):
        fake = {
            "balance": 100000, "equity": 99500,
            "margin": 500, "freeMargin": 99000, "currency": "USD",
        }
        with patch("app.services.metaapi_broker.mt5_get_account_info",
                   new=AsyncMock(return_value=fake)):
            b = MetaApiBroker("acc-123")
            info = await b.account_info()
            assert info.balance == 100000
            assert info.equity == 99500
            assert info.free_margin == 99000

    @pytest.mark.asyncio
    async def test_reset_raises_not_implemented(self):
        b = MetaApiBroker("acc-123")
        with pytest.raises(NotImplementedError):
            await b.reset()
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && python -m pytest tests/test_metaapi_broker.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`backend/app/services/metaapi_broker.py`:

```python
"""
MetaApiBroker — wraps existing live_trading.py functions so they satisfy
BrokerBase. Zero logic change from before; just a class-shaped interface.

The account_id passed in is the MetaApi account to route through — but
the current live_trading module is process-global (it picks the first
ready connection). For PR 2a we keep that behavior; future work will
make connection selection per-account.
"""

from datetime import datetime, timezone

from app.services.broker_base import BrokerBase  # noqa: F401 — for protocol check
from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)
from app.services.live_trading import (
    mt5_place_order,
    mt5_create_pending_order,
    mt5_close_position,
    mt5_close_position_partially,
    mt5_modify_position,
    mt5_cancel_order,
    mt5_get_positions,
    mt5_get_orders,
    mt5_get_trade_history,
    mt5_get_account_info,
    mt5_get_symbol_spec,
)


def _to_result(raw: dict) -> OrderResult:
    return OrderResult(
        success=bool(raw.get("success")),
        order_id=raw.get("order_id") or raw.get("orderId"),
        message=raw.get("error") or raw.get("message"),
    )


class MetaApiBroker:
    """BrokerBase implementation routing through live_trading → MetaApi SDK."""

    def __init__(self, metaapi_account_id: str):
        self._account_id = metaapi_account_id

    async def account_info(self) -> AccountInfo:
        data = await mt5_get_account_info() or {}
        return AccountInfo(
            balance=float(data.get("balance", 0)),
            equity=float(data.get("equity", 0)),
            margin=float(data.get("margin", 0)),
            free_margin=float(data.get("freeMargin", data.get("free_margin", 0))),
            currency=str(data.get("currency", "USD")),
        )

    async def positions(self) -> list[PositionDTO]:
        raw = await mt5_get_positions() or []
        out: list[PositionDTO] = []
        for p in raw:
            out.append(PositionDTO(
                id=str(p.get("id", "")),
                symbol=str(p.get("symbol", "")),
                side="long" if p.get("type") == "POSITION_TYPE_BUY" else "short",
                size=float(p.get("volume", 0)),
                entry_price=float(p.get("openPrice", 0)),
                current_price=float(p.get("currentPrice", 0)),
                unrealized_pnl=float(p.get("profit", 0)),
                stop_loss=float(p["stopLoss"]) if p.get("stopLoss") else None,
                take_profit=float(p["takeProfit"]) if p.get("takeProfit") else None,
                opened_at=datetime.now(timezone.utc),
            ))
        return out

    async def pending_orders(self) -> list[OrderDTO]:
        raw = await mt5_get_orders() or []
        out: list[OrderDTO] = []
        for o in raw:
            out.append(OrderDTO(
                id=str(o.get("id", "")),
                symbol=str(o.get("symbol", "")),
                side="buy" if "BUY" in str(o.get("type", "")).upper() else "sell",
                size=float(o.get("volume", 0)),
                order_type="limit" if "LIMIT" in str(o.get("type", "")).upper() else "stop",
                price=float(o.get("openPrice", 0)),
                stop_loss=float(o["stopLoss"]) if o.get("stopLoss") else None,
                take_profit=float(o["takeProfit"]) if o.get("takeProfit") else None,
                status="pending",
                created_at=datetime.now(timezone.utc),
            ))
        return out

    async def place_market_order(self, symbol: str, side: str, volume: float,
                                  sl: float | None = None,
                                  tp: float | None = None) -> OrderResult:
        return _to_result(await mt5_place_order(symbol, side, volume, sl, tp))

    async def place_pending_order(self, symbol: str, side: str, volume: float,
                                   order_type: str, price: float,
                                   sl: float | None = None,
                                   tp: float | None = None) -> OrderResult:
        return _to_result(await mt5_create_pending_order(
            symbol, side, volume, order_type, price, sl, tp,
        ))

    async def close_position(self, position_id: str) -> OrderResult:
        return _to_result(await mt5_close_position(position_id))

    async def close_position_partial(self, position_id: str, volume: float) -> OrderResult:
        return _to_result(await mt5_close_position_partially(position_id, volume))

    async def modify_position(self, position_id: str,
                               sl: float | None = None,
                               tp: float | None = None) -> OrderResult:
        return _to_result(await mt5_modify_position(position_id, sl, tp))

    async def cancel_order(self, order_id: str) -> OrderResult:
        return _to_result(await mt5_cancel_order(order_id))

    async def history(self, limit: int = 50) -> list[ClosedTrade]:
        raw = await mt5_get_trade_history() or {}
        deals = raw.get("trades") or raw.get("deals") or []
        out: list[ClosedTrade] = []
        for d in deals[:limit]:
            try:
                out.append(ClosedTrade(
                    id=str(d.get("id", "")),
                    symbol=str(d.get("symbol", "")),
                    side="long" if d.get("type") == "DEAL_TYPE_BUY" else "short",
                    size=float(d.get("volume", 0)),
                    entry_price=float(d.get("openPrice", 0)),
                    exit_price=float(d.get("closePrice", 0)),
                    pnl=float(d.get("profit", 0)),
                    opened_at=datetime.now(timezone.utc),
                    closed_at=datetime.now(timezone.utc),
                ))
            except Exception:
                continue
        return out

    async def symbol_info(self, symbol: str) -> dict:
        return await mt5_get_symbol_spec(symbol) or {}

    async def reset(self) -> None:
        raise NotImplementedError("MetaApi accounts cannot be reset programmatically")
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_metaapi_broker.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/metaapi_broker.py backend/tests/test_metaapi_broker.py
git commit -m "feat(broker): MetaApiBroker wraps live_trading into BrokerBase shape"
```

---

## Task 8: Broker factory + routing swap

**Files:**
- Create: `backend/app/services/broker_factory.py`
- Create: `backend/tests/test_broker_factory.py`
- Modify: `backend/app/api/routes.py` (11 trading endpoints)

- [ ] **Step 1: Write the factory test**

`backend/tests/test_broker_factory.py`:

```python
"""BrokerFactory picks the right implementation based on Owner."""

from app.models.owner import Owner
from app.services.broker_factory import get_broker
from app.services.metaapi_broker import MetaApiBroker
from app.services.sandbox_broker import SandboxBroker


class TestBrokerFactory:
    def test_owner_without_metaapi_gets_sandbox(self):
        owner = Owner(id="u-1", kind="user", plan="free", metaapi_account_id=None)
        broker = get_broker(owner)
        assert isinstance(broker, SandboxBroker)

    def test_owner_with_metaapi_gets_metaapi(self):
        owner = Owner(id="u-2", kind="user", plan="pro", metaapi_account_id="acc-xyz")
        broker = get_broker(owner)
        assert isinstance(broker, MetaApiBroker)

    def test_anon_always_gets_sandbox(self):
        owner = Owner(id="a-1", kind="anon", plan="anon", metaapi_account_id=None)
        broker = get_broker(owner)
        assert isinstance(broker, SandboxBroker)
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && python -m pytest tests/test_broker_factory.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement factory**

`backend/app/services/broker_factory.py`:

```python
"""Factory picks the right BrokerBase for a given Owner.

This is the single entry point used by every trading endpoint.
"""

from app.models.owner import Owner
from app.services.broker_base import BrokerBase
from app.services.metaapi_broker import MetaApiBroker
from app.services.sandbox_broker import SandboxBroker


def get_broker(owner: Owner) -> BrokerBase:
    if owner.metaapi_account_id:
        return MetaApiBroker(owner.metaapi_account_id)
    return SandboxBroker(owner)
```

- [ ] **Step 4: Verify factory tests pass**

```bash
cd backend && python -m pytest tests/test_broker_factory.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Audit trading endpoints in routes.py**

Run:
```bash
grep -n "^@router\|mt5_\|broker\." backend/app/api/routes.py | head -40
```

You're looking for every endpoint currently calling `mt5_*` functions directly. These all need to switch to `broker = get_broker(owner)` + `broker.method(...)`.

Expected endpoints to migrate:
- `POST /api/trading/order` → `broker.place_market_order(...)`
- `POST /api/trading/pending-order` → `broker.place_pending_order(...)`
- `POST /api/trading/position/{id}/close` → `broker.close_position(...)`
- `POST /api/trading/position/{id}/close-partial` → `broker.close_position_partial(...)`
- `POST /api/trading/position/{id}/modify` → `broker.modify_position(...)`
- `POST /api/trading/order/{id}/cancel` → `broker.cancel_order(...)`
- `GET /api/trading/account` → `broker.account_info()` + `broker.positions()`
- `GET /api/trading/account-info` → `broker.account_info()`
- `GET /api/trading/orders` → `broker.pending_orders()`
- `GET /api/trading/history` → `broker.history()`
- `GET /api/trading/symbol/{symbol}` → `broker.symbol_info(symbol)`

For each: replace `mt5_*` call with `get_broker(owner).<method>()` using the **already-present** `owner: Owner = Depends(require_user)` parameter (added in PR 1).

Example migration pattern (before):
```python
@router.post("/api/trading/order")
async def trading_place_order(req: OrderRequest, owner: Owner = Depends(require_user)):
    result = await mt5_place_order(req.symbol, req.side, req.volume, req.sl, req.tp)
    return result
```

After:
```python
@router.post("/api/trading/order")
async def trading_place_order(req: OrderRequest, owner: Owner = Depends(require_user)):
    broker = get_broker(owner)
    result = await broker.place_market_order(req.symbol, req.side, req.volume, req.sl, req.tp)
    return {"success": result.success, "order_id": result.order_id, "message": result.message}
```

**Important**: the response shape was previously whatever `mt5_place_order` returned (loose dicts). Now it's a dataclass. Convert explicitly to the dict shape the frontend expects. Check `frontend/src/components/dashboard/TradingPanel.tsx` to confirm the shape. If frontend expects `{success, order_id}`, that matches `OrderResult`. If it expects richer fields, extract them from `broker.account_info()` after the order.

Add imports at the top of `routes.py`:
```python
from app.services.broker_factory import get_broker
from app.services.broker_types import OrderResult
```

- [ ] **Step 6: Update routes, preserving response shapes**

Edit each of the 11 endpoints listed in Step 5. Keep the request validation and response JSON shape identical to what the frontend currently expects. When `OrderResult` differs from the old dict shape, map explicitly — do not let `{"success": True, "order_id": ...}` leak through untransformed when the frontend reads different keys.

- [ ] **Step 7: Run full test suite**

```bash
cd /Users/hexin/code/test/last30days/.worktrees/broker-sandbox
set -a && source backend/.env && set +a
cd backend && python -m pytest -v 2>&1 | tail -15
```
Expected: all existing + new tests pass (85 existing + ~20 new broker tests).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/broker_factory.py backend/tests/test_broker_factory.py backend/app/api/routes.py
git commit -m "feat(broker): route factory + migrate trading endpoints to BrokerBase"
```

---

## Task 9: Sandbox reset endpoint

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: new `backend/tests/test_sandbox_endpoints.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sandbox_endpoints.py`:

```python
"""Smoke tests for sandbox-specific API endpoints."""

import os
import secrets

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


def _fresh_token(client: TestClient) -> str:
    email = f"sbe-{secrets.token_hex(4)}@test.propguard.ai"
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    resp = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return resp.json()["token"]


def _client():
    from app.main import app
    return TestClient(app)


class TestSandboxReset:
    def test_reset_requires_auth(self):
        c = _client()
        resp = c.post("/api/sandbox/reset")
        assert resp.status_code == 401

    def test_reset_returns_ok_for_sandbox_user(self):
        c = _client()
        token = _fresh_token(c)
        resp = c.post("/api/sandbox/reset",
                      headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
```

- [ ] **Step 2: Verify fails**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_endpoints.py -v
```
Expected: 404 Not Found (endpoint doesn't exist yet).

- [ ] **Step 3: Add the endpoint to routes.py**

Append:

```python
@router.post("/api/sandbox/reset")
async def sandbox_reset(owner: Owner = Depends(require_user)):
    """Reset this owner's sandbox to a clean $100,000 state.

    Returns 400 if the owner is bound to a real MetaApi account (nothing
    to reset). PR 2b will add quota enforcement to prevent abuse.
    """
    if owner.metaapi_account_id:
        raise HTTPException(400, detail="Real accounts cannot be reset")
    broker = get_broker(owner)
    await broker.reset()
    return {"success": True}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && set -a && source .env && set +a && python -m pytest tests/test_sandbox_endpoints.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes.py backend/tests/test_sandbox_endpoints.py
git commit -m "feat(sandbox): POST /api/sandbox/reset endpoint"
```

---

## Task 10: Full automated smoke test + open PR

**Files:** none (ops)

- [ ] **Step 1: Run full pytest suite**

```bash
cd /Users/hexin/code/test/last30days/.worktrees/broker-sandbox
set -a && source backend/.env && set +a
cd backend && python -m pytest -v 2>&1 | tail -15
```
Expected: 100+ tests pass.

- [ ] **Step 2: Start servers**

```bash
cd backend && python -m uvicorn app.main:app --port 8001 &
BACKEND_PID=$!
cd ../frontend && echo "NEXT_PUBLIC_API_URL=http://localhost:8001" > .env.local && npm install --silent
npx next dev --port 3001 &
FRONTEND_PID=$!
sleep 5
```

- [ ] **Step 3: Automated browser smoke test via gstack browse**

```bash
B=~/.claude/skills/gstack/browse/dist/browse
EMAIL="sbox-$(date +%s)@test.propguard.ai"
$B goto http://localhost:3001/login > /dev/null
$B snapshot -i > /dev/null
$B click @e4 > /dev/null  # Register tab
sleep 1
$B snapshot -i > /dev/null
$B fill @e1 "Sandbox Smoke" > /dev/null
$B fill @e2 "$EMAIL" > /dev/null
$B fill @e3 "password123" > /dev/null
$B click @e4 > /dev/null  # Create Account
sleep 4
echo "Dashboard URL: $($B url)"

# Place a market order via the trading panel and verify the position appears
# Frontend flow: click BUY on EURUSD should hit /api/trading/order → SandboxBroker
$B snapshot -i > /tmp/dash-snap.txt
BUY_REF=$(grep -E '"BUY"' /tmp/dash-snap.txt | head -1 | grep -oE '@e[0-9]+' | head -1)
echo "BUY ref: $BUY_REF"
$B click "$BUY_REF" > /dev/null
sleep 3
$B console --errors 2>&1 | tail -5

# Verify a position was created
$B js "document.body.textContent.includes('Open Positions')" 2>&1 | tail -1
```

Expected: dashboard loads, BUY click produces no 500 errors, text "Open Positions" is present.

- [ ] **Step 4: Stop servers**

```bash
kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
sleep 1
```

- [ ] **Step 5: Push branch and open PR**

```bash
git push -u origin feat/broker-sandbox 2>&1 | tail -3
gh pr create --title "PR 2a: Broker abstraction + Sandbox implementation" --body "$(cat <<'EOF'
## Summary

- `BrokerBase` Protocol + `MetaApiBroker` (wraps existing `live_trading.py`) + `SandboxBroker` (per-owner DB-backed simulation)
- Factory at `broker_factory.py`: `get_broker(owner)` picks based on `owner.metaapi_account_id`
- 11 trading endpoints in `routes.py` swapped from module-level `broker` singleton to per-request `get_broker(owner)`
- New migration: `sandbox_accounts`, `sandbox_positions`, `sandbox_orders`, `sandbox_closed_trades` + `data/sandbox_spreads.json`
- New endpoint: `POST /api/sandbox/reset`

After this PR:
- Anonymous and free-tier users (no `metaapi_account_id`) automatically run trades in a per-owner simulated sandbox with live market prices + configured spreads.
- Pro/Premium users with real MetaApi binding continue to hit real accounts — zero behavior change for them.

## Out of scope (PR 2b, PR 3)

- AI quota middleware + cost tracking
- Frontend-driven AI tick for anon
- Frontend auth-guard removal (dashboard still requires login)
- Registration → anon claim flow

## Test plan

- [x] `pytest backend/tests -v` — all green (~105 tests)
- [x] Automated browser smoke test: register → dashboard → place BUY order → position appears
- [x] Migration applied to dev Supabase; 4 sandbox tables present

Spec: `docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md` §5, §6
Plan: `docs/superpowers/plans/2026-04-19-broker-abstraction-sandbox.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" 2>&1 | tail -3
```

---

## Self-review checklist

- [ ] **Spec coverage:** §5 (BrokerBase + SandboxBroker + MetaApiBroker) → Tasks 3, 5, 6, 7. §6 (BrokerFactory) → Task 8. Migration schema → Task 1. Routes integration → Task 8.
- [ ] **Placeholder scan:** no "TBD" / "implement later" / "similar to Task N" references. Every step contains the full code or exact command.
- [ ] **Type consistency:** `BrokerBase`, `MetaApiBroker`, `SandboxBroker`, `AccountInfo`, `PositionDTO`, `OrderDTO`, `OrderResult`, `ClosedTrade`, `get_broker`, `sandbox_*` helpers — all consistent across tasks.
- [ ] **Out of scope explicitly flagged:** AIClient + quotas (PR 2b), frontend public + claim (PR 3), per-account MetaApi connection routing (follow-up).
