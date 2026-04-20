-- PropGuard AI — IP-level anonymous quota backstop + retention prunes.
-- PR 2b review I1: anonymous users can clear cookies to bypass per-owner
-- quota. Per-IP daily cap kicks in first so cookie-rotation doesn't buy
-- unlimited AI budget.
--
-- Also adds retention prune functions for ip_quota_usage (30d) and
-- ai_cost_ledger (90d). Schedule nightly via Supabase Scheduled Functions.

create table if not exists ip_quota_usage (
  ip_hash text not null,
  action text not null,
  date date not null,
  count integer not null default 0,
  primary key (ip_hash, action, date)
);

create index if not exists idx_ip_quota_usage_date on ip_quota_usage(date);

-- Atomic consume mirroring quota_consume.
create or replace function ip_quota_consume(
  p_ip_hash text, p_action text, p_date date, p_limit integer
) returns integer language plpgsql as $$
declare
  result_count integer;
begin
  insert into ip_quota_usage (ip_hash, action, date, count)
    values (p_ip_hash, p_action, p_date, 1)
  on conflict (ip_hash, action, date) do update
    set count = ip_quota_usage.count + 1
    where ip_quota_usage.count < p_limit
  returning count into result_count;
  return result_count;
end $$;

-- Retention: prune ip_quota_usage rows older than 30 days.
create or replace function prune_ip_quota_old() returns integer language plpgsql as $$
declare
  deleted integer;
begin
  delete from ip_quota_usage where date < current_date - interval '30 days';
  get diagnostics deleted = row_count;
  return deleted;
end $$;

-- Retention for ai_cost_ledger: prune >90 days (M4 from PR 2b review).
create or replace function prune_ai_cost_ledger_old() returns integer language plpgsql as $$
declare
  deleted integer;
begin
  delete from ai_cost_ledger where date < current_date - interval '90 days';
  get diagnostics deleted = row_count;
  return deleted;
end $$;
