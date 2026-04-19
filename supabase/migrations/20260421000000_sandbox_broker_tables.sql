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
