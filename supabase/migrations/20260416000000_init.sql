-- PropGuard AI — Initial Schema
-- Migration: 20260416000000_init

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  name text default '',
  password_hash text not null,
  tier text default 'free' check (tier in ('free', 'pro', 'premium')),
  telegram_chat_id text,
  created_at timestamptz default now()
);

create table if not exists trading_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  account_id text not null,
  firm_name text not null,
  account_size int not null,
  broker_type text default 'mock',
  label text default '',
  created_at timestamptz default now(),
  unique(user_id, account_id)
);

create table if not exists signals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  source_id text,
  source_name text,
  symbol text not null,
  direction text not null,
  entry_price float,
  stop_loss float,
  take_profit float,
  raw_text text,
  score int,
  risk_level text,
  rationale text,
  received_at timestamptz default now()
);

create table if not exists alerts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  account_id text,
  firm_name text,
  rule_type text not null,
  alert_level text not null,
  message text,
  remaining float,
  remaining_pct float,
  created_at timestamptz default now()
);

create table if not exists signal_source_stats (
  source_id text primary key,
  source_name text,
  source_type text default 'telegram',
  win_rate float,
  avg_rr float,
  sample_size int default 0,
  last_updated timestamptz default now()
);

create index if not exists idx_signals_user on signals(user_id, received_at desc);
create index if not exists idx_alerts_user on alerts(user_id, created_at desc);
create index if not exists idx_trading_accounts_user on trading_accounts(user_id);
