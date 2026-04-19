-- PropGuard AI — Atomic quota consumption via Postgres RPC.
-- Replaces the SELECT-then-UPSERT pattern in check_and_consume so concurrent
-- requests can't lose a consumption. See PR 2b review I2.

create or replace function quota_consume(
  p_owner_id uuid,
  p_owner_kind text,
  p_action text,
  p_date date,
  p_limit integer
) returns integer language plpgsql as $$
declare
  result_count integer;
begin
  insert into owner_quota_usage (owner_id, owner_kind, action, date, count)
    values (p_owner_id, p_owner_kind, p_action, p_date, 1)
  on conflict (owner_id, action, date) do update
    set count = owner_quota_usage.count + 1
    where owner_quota_usage.count < p_limit
  returning count into result_count;
  -- result_count is NULL iff the WHERE clause blocked the update (limit hit).
  return result_count;
end $$;
