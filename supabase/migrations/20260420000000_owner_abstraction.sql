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
-- Pattern: delete orphan rows → add nullable columns → backfill → set not null.
-- Polymorphic owner_id has no FK (references either users or anon_sessions).
--
-- Orphan rows (user_id IS NULL) are pre-existing test/webhook data with no
-- user association; they are unreachable through the app and deleted here so
-- SET NOT NULL can succeed.
delete from trading_accounts where user_id is null;
delete from signals          where user_id is null;
delete from alerts           where user_id is null;
delete from ai_trade_logs    where user_id is null;

alter table trading_accounts add column if not exists owner_id uuid;
alter table trading_accounts add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update trading_accounts set owner_id = user_id, owner_kind = 'user'
  where owner_id is null;
alter table trading_accounts alter column owner_id set not null;
alter table trading_accounts alter column owner_kind set not null;
create index if not exists idx_trading_accounts_owner
  on trading_accounts(owner_id);

alter table signals add column if not exists owner_id uuid;
alter table signals add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update signals set owner_id = user_id, owner_kind = 'user'
  where owner_id is null;
alter table signals alter column owner_id set not null;
alter table signals alter column owner_kind set not null;
create index if not exists idx_signals_owner
  on signals(owner_id, received_at desc);

alter table alerts add column if not exists owner_id uuid;
alter table alerts add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update alerts set owner_id = user_id, owner_kind = 'user'
  where owner_id is null;
alter table alerts alter column owner_id set not null;
alter table alerts alter column owner_kind set not null;
create index if not exists idx_alerts_owner
  on alerts(owner_id, created_at desc);

alter table ai_trade_logs add column if not exists owner_id uuid;
alter table ai_trade_logs add column if not exists owner_kind text
  check (owner_kind in ('user','anon'));
update ai_trade_logs set owner_id = user_id, owner_kind = 'user'
  where owner_id is null;
alter table ai_trade_logs alter column owner_id set not null;
alter table ai_trade_logs alter column owner_kind set not null;
create index if not exists idx_ai_trade_logs_owner
  on ai_trade_logs(owner_id, created_at desc);

-- NOTE: user_id columns are kept during the deprecation window.
-- A follow-up migration after PR 3 ships will drop them.
