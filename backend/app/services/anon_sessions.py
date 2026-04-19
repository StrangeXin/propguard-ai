"""
Anon session DB layer — minimal CRUD over the anon_sessions table.
"""

import logging
from datetime import datetime, timezone

from app.services.database import get_db

logger = logging.getLogger(__name__)


def create_anon_session(ip_hash: str | None = None,
                        user_agent: str | None = None) -> str | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("anon_sessions").insert({
            "ip_hash": ip_hash,
            "user_agent": user_agent,
        }).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        logger.error(f"create_anon_session: {e}")
    return None


def get_anon_session(session_id: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("anon_sessions").select("*").eq("id", session_id).limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"get_anon_session: {e}")
    return None


def touch_anon_session(session_id: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("anon_sessions").update({
            "last_active_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.error(f"touch_anon_session: {e}")


def claim_anon_session(session_id: str, user_id: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("anon_sessions").update({
            "claimed_by_user_id": user_id,
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.error(f"claim_anon_session: {e}")
