-- PropGuard AI — Order attribution for the shared public account
-- Migration: 20260424000000_order_attributions
-- Spec: docs/superpowers/specs/2026-04-20-shared-public-account-anon-read-design.md

create table if not exists order_attributions (
  broker_order_id text primary key,
  broker_position_id text,
  account_id text not null,
  user_id uuid references users(id) on delete set null,
  user_label text not null,
  symbol text,
  side text check (side in ('buy','sell')),
  volume numeric,
  placed_at timestamptz default now()
);

create index if not exists idx_attr_position on order_attributions(broker_position_id);
create index if not exists idx_attr_account_time on order_attributions(account_id, placed_at desc);
