"""
Alert history — persists compliance alerts to Supabase.
Falls back to in-memory if Supabase unavailable.
"""

from datetime import datetime
from app.services.database import db_save_alert, db_get_alerts

# In-memory fallback
_history_mem: list[dict] = []
MAX_HISTORY = 200


def record_alert(
    account_id: str,
    firm_name: str,
    rule_type: str,
    alert_level: str,
    message: str,
    remaining: float,
    remaining_pct: float,
    user_id: str | None = None,
):
    alert = {
        "account_id": account_id,
        "firm_name": firm_name,
        "rule_type": rule_type,
        "alert_level": alert_level,
        "message": message,
        "remaining": remaining,
        "remaining_pct": remaining_pct,
    }

    # Try Supabase
    db_save_alert(user_id, alert)

    # Always keep in memory too for fast access
    _history_mem.append({**alert, "timestamp": datetime.now().isoformat()})
    if len(_history_mem) > MAX_HISTORY:
        _history_mem.pop(0)


def get_alert_history(account_id: str | None = None, user_id: str | None = None, limit: int = 50) -> list[dict]:
    # Try Supabase first
    db_alerts = db_get_alerts(user_id=user_id, account_id=account_id, limit=limit)
    if db_alerts:
        return [
            {
                "timestamp": a.get("created_at", ""),
                "account_id": a.get("account_id", ""),
                "firm_name": a.get("firm_name", ""),
                "rule_type": a.get("rule_type", ""),
                "alert_level": a.get("alert_level", ""),
                "message": a.get("message", ""),
                "remaining": a.get("remaining", 0),
                "remaining_pct": a.get("remaining_pct", 0),
            }
            for a in db_alerts
        ]

    # Fallback to memory
    items = _history_mem
    if account_id:
        items = [a for a in items if a.get("account_id") == account_id]
    return list(reversed(items[-limit:]))
