-- PropGuard AI — Nightly cleanup of expired unclaimed anon sessions.
-- owner_id is polymorphic (no FK cascade) so the function must explicitly
-- delete dependent rows before pruning anon_sessions.
--
-- Returns the number of anon_sessions rows removed.
-- Invoke nightly via Supabase Scheduled Functions / pg_cron:
--   select cron.schedule('propguard-anon-cleanup', '0 3 * * *', 'select cleanup_expired_anon()');

create or replace function cleanup_expired_anon() returns integer language plpgsql as $$
declare
  deleted_sessions integer;
begin
  -- Snapshot of expired session IDs reused across every delete.
  create temp table _expired_anon_ids on commit drop as
    select id from anon_sessions
    where claimed_by_user_id is null
      and last_active_at < now() - interval '30 days';

  delete from sandbox_positions      where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from sandbox_orders         where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from sandbox_closed_trades  where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from sandbox_accounts       where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from ai_trade_logs          where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from signals                where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from alerts                 where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from owner_quota_usage      where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);
  delete from ai_cost_ledger         where owner_kind = 'anon' and owner_id in (select id from _expired_anon_ids);

  delete from anon_sessions where id in (select id from _expired_anon_ids);
  get diagnostics deleted_sessions = row_count;
  return deleted_sessions;
end $$;
