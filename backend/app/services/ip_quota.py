"""Per-IP daily caps for anonymous AI actions.

PR 2b review I1: an attacker clearing cookies gets unlimited anon
allowance. IP cap kicks in before per-owner consume so rotating cookies
alone doesn't bypass it. Paid users (with valid JWT) skip the IP cap.
"""

import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.services.database import get_db
from app.services.quota import QuotaExceeded

logger = logging.getLogger(__name__)


def _today_utc_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _ip_limit_for(action: str) -> int | None:
    settings = get_settings()
    mapping = {
        "ai_trade_tick": settings.ip_quota_ai_trade_tick,
        "ai_score": settings.ip_quota_ai_score,
    }
    return mapping.get(action)


def check_ip(ip_hash: str | None, action: str) -> None:
    """Raises QuotaExceeded if IP cap reached. No-op if ip_hash is None or
    the action is uncapped. Fail-open on DB errors (consistent with
    per-owner quota)."""
    if not ip_hash:
        return
    limit = _ip_limit_for(action)
    if limit is None:
        return
    db = get_db()
    if not db:
        return

    today = _today_utc_iso()
    try:
        result = db.rpc("ip_quota_consume", {
            "p_ip_hash": ip_hash,
            "p_action": action,
            "p_date": today,
            "p_limit": limit,
        }).execute()
        new_count = result.data
        if new_count is None:
            # Prefix with "ip:" so the frontend can distinguish abuse-cap
            # from normal upgrade-cap in the 402 response.
            raise QuotaExceeded(
                action=f"ip:{action}",
                limit=limit, used=limit, plan="anon-ip",
            )
    except QuotaExceeded:
        raise
    except Exception as e:
        logger.error(f"ip_quota check: {e}")
        # Fail-open.
