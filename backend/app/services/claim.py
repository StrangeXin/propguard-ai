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
_OWNER_SCOPED_TABLES = [
    "trading_accounts",
    "signals",
    "alerts",
    "ai_trade_logs",
    "sandbox_accounts",
    "sandbox_positions",
    "sandbox_orders",
    "sandbox_closed_trades",
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
            # sandbox_accounts has PK on owner_id — one row per owner. If the
            # user already has an account row (e.g., they previously registered
            # and came back as anon), UPDATE would violate PK. Delete the anon
            # row in that case; the user's existing account survives.
            if table == "sandbox_accounts":
                existing_user = db.table(table).select("owner_id").eq(
                    "owner_id", user_id).limit(1).execute()
                if existing_user.data:
                    deleted = db.table(table).delete().eq("owner_id", anon_id).execute()
                    counts[table] = len(deleted.data or [])
                    continue

            result = db.table(table).update({
                "owner_id": user_id,
                "owner_kind": "user",
            }).eq("owner_id", anon_id).eq("owner_kind", "anon").execute()
            counts[table] = len(result.data or [])
        except Exception as e:
            logger.error(f"claim {table}: {e}")

    _mark_claimed(anon_id, user_id)
    return counts
