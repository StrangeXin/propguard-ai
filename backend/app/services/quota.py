"""
Per-owner quota enforcement.

- `plan_quotas` defines limits per (plan, action).
- `owner_quota_usage` tracks daily consumption per (owner_id, action, date).
- `check_and_consume(owner, action)` bumps the counter and raises
  `QuotaExceeded` if the limit is reached.
- `require_quota(action)` is a FastAPI dependency factory that returns 402
  with a machine-readable error payload on miss.

Daily counters roll over at UTC midnight. `total_limit` (e.g. saved_strategies)
is checked against actual row counts in the target table, not this counter.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException

from app.models.owner import Owner
from app.services.database import get_db
from app.services.owner_resolver import get_owner

logger = logging.getLogger(__name__)


@dataclass
class QuotaExceeded(Exception):
    action: str
    limit: int
    used: int
    plan: str

    def __str__(self):
        return f"{self.action} limit reached: {self.used}/{self.limit} on plan '{self.plan}'"

    def __post_init__(self):
        super().__init__(str(self))


def _today_utc_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _resets_at_iso() -> str:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow.isoformat().replace("+00:00", "Z")


def _plan_limit(plan: str, action: str) -> tuple[int | None, int | None] | None:
    """Returns (daily_limit, total_limit) if the row exists, or None if the
    (plan, action) pair is not configured. Distinguishing "row exists with
    nulls (unlimited)" from "row missing (unconfigured)" matters — the first
    must allow calls, the second must reject them.
    """
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("plan_quotas").select("*").eq("plan", plan).eq("action", action).limit(1).execute()
        if result.data:
            row = result.data[0]
            return row.get("daily_limit"), row.get("total_limit")
    except Exception as e:
        logger.error(f"plan_limit lookup: {e}")
    return None


def check_and_consume(owner: Owner, action: str) -> bool:
    """Raises QuotaExceeded if over limit. Otherwise increments counter, returns True.

    Fails open on transient DB errors (logs + returns True) to avoid blocking the
    whole app on Supabase hiccups. Alerts surface via logs.
    """
    limits = _plan_limit(owner.plan, action)

    # Unconfigured (plan, action) pair — reject (safer than unbounded calls).
    if limits is None:
        raise QuotaExceeded(action=action, limit=0, used=0, plan=owner.plan)

    daily_limit, _total_limit = limits

    # Unlimited daily (e.g. premium tier has row with daily_limit=null).
    if daily_limit is None:
        return True

    today = _today_utc_iso()
    db = get_db()
    if not db:
        return True

    try:
        # Atomic insert-or-conditional-increment via Postgres RPC.
        # Returns the new count, or NULL if the limit was already hit.
        result = db.rpc("quota_consume", {
            "p_owner_id": owner.id,
            "p_owner_kind": owner.kind,
            "p_action": action,
            "p_date": today,
            "p_limit": daily_limit,
        }).execute()
        new_count = result.data
        if new_count is None:
            # Re-read the current count for the error payload so the user
            # sees "used: 20 / limit: 20" rather than zeros.
            existing = db.table("owner_quota_usage").select("count").eq(
                "owner_id", owner.id).eq("action", action).eq("date", today).limit(1).execute()
            used = existing.data[0]["count"] if existing.data else daily_limit
            raise QuotaExceeded(action=action, limit=daily_limit, used=used, plan=owner.plan)
        return True
    except QuotaExceeded:
        raise
    except Exception as e:
        logger.error(f"quota consume: {e}")
        return True


def require_quota(action: str):
    """FastAPI dependency factory.

    Checks and consumes `action` quota for the resolved Owner. On miss raises
    HTTP 402 with a machine-readable detail body: `{code, action, message,
    limit, used, plan, upgrade_url, resets_at}`.

    For anonymous owners, also consults the per-IP daily cap before the
    per-owner quota. Cookie-rotation alone doesn't bypass the IP cap.
    """
    from fastapi import Request as _Request
    from app.services.owner_resolver import _hash_ip

    def _check(request: _Request, owner: Owner = Depends(get_owner)) -> Owner:
        try:
            # Anonymous users also face an IP-level cap (PR 3b T2).
            if owner.kind == "anon":
                from app.services.ip_quota import check_ip
                ip = request.client.host if request.client else None
                ip_hash = _hash_ip(ip)
                check_ip(ip_hash, action)
            check_and_consume(owner, action)
        except QuotaExceeded as e:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "action": e.action,
                    "message": str(e),
                    "limit": e.limit,
                    "used": e.used,
                    "plan": e.plan,
                    "upgrade_url": "/pricing",
                    "resets_at": _resets_at_iso(),
                },
            )
        return owner
    return _check


def _reset_for_test(owner_id: str, action: str) -> None:
    """Testing helper: wipe today's counter. Not called in production."""
    db = get_db()
    if not db:
        return
    today = _today_utc_iso()
    try:
        db.table("owner_quota_usage").delete().eq("owner_id", owner_id).eq("action", action).eq("date", today).execute()
    except Exception as e:
        logger.warning(f"_reset_for_test: {e}")
