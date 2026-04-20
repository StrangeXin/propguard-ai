-- The table may have been created in a non-public schema (or PostgREST's
-- cache is otherwise stuck). Drop and recreate it explicitly in `public`
-- so PostgREST's schema cache sees the table. No rows are lost because
-- record_attribution has been failing write-side since PGRST205 started,
-- so the table is empty.

drop table if exists public.order_attributions;

create table public.order_attributions (
  broker_order_id text primary key,
  broker_position_id text,
  account_id text not null,
  user_id uuid references public.users(id) on delete set null,
  user_label text not null,
  symbol text,
  side text check (side in ('buy','sell')),
  volume numeric,
  placed_at timestamptz default now()
);

create index if not exists idx_attr_position on public.order_attributions(broker_position_id);
create index if not exists idx_attr_account_time on public.order_attributions(account_id, placed_at desc);

notify pgrst, 'reload schema';
