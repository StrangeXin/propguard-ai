"""
Atomic migration of anon-session-owned rows to a newly registered user.

Called from the register endpoint when a valid `anon_session_id` cookie
was present on the request. Updates `owner_id` / `owner_kind` across every
user-owned table, then marks the anon_session as claimed.

Polymorphic owner_id means no FK cascade. This function explicitly
enumerates the tables; any new owner-scoped table added in the future
must be added to _OWNER_SCOPED_TABLES here.
"""

import logging

from app.services.anon_sessions import claim_anon_session as _mark_claimed
from app.services.database import get_db

logger = logging.getLogger(__name__)

# Tables that carry (owner_id, owner_kind) per the PR 1 + PR 2a migrations.
# The sandbox_* tables from the retired SandboxBroker are no longer listed —
# nothing writes to them after the broker-factory flip to shared MetaApi.
_OWNER_SCOPED_TABLES = [
    "trading_accounts",
    "signals",
    "alerts",
    "ai_trade_logs",
    "owner_quota_usage",
    "ai_cost_ledger",
]


def claim_anon_data(anon_id: str, user_id: str) -> dict[str, int]:
    """Re-own all rows from anon_id to user_id. Returns per-table row counts.

    Idempotent: running twice moves zero rows the second time because the
    WHERE clause filters on owner_id='<anon_id>' AND owner_kind='anon'.
    """
    db = get_db()
    counts: dict[str, int] = {t: 0 for t in _OWNER_SCOPED_TABLES}
    if not db:
        return counts

    for table in _OWNER_SCOPED_TABLES:
        try:
            result = db.table(table).update({
                "owner_id": user_id,
                "owner_kind": "user",
            }).eq("owner_id", anon_id).eq("owner_kind", "anon").execute()
            counts[table] = len(result.data or [])
        except Exception as e:
            logger.error(f"claim {table}: {e}")

    _mark_claimed(anon_id, user_id)
    return counts
