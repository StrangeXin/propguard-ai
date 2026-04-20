"""
Supabase database layer — replaces all in-memory storage.
Single module for all DB operations.
"""

import logging
from datetime import datetime
from app.config import get_settings

logger = logging.getLogger(__name__)

_client = None


def get_db():
    global _client
    if _client is None:
        from supabase import create_client
        settings = get_settings()
        if settings.supabase_url and settings.supabase_key:
            _client = create_client(settings.supabase_url, settings.supabase_key)
            logger.info("Supabase connected")
        else:
            logger.warning("Supabase not configured")
    return _client


## ── Users ───────────────────────────────────────────────────────


def db_create_user(email: str, name: str, password_hash: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("users").insert({
            "email": email,
            "name": name,
            "password_hash": password_hash,
            "tier": "free",
        }).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"db_create_user: {e}")
    return None


def db_get_user_by_email(email: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("users").select("*").eq("email", email).limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"db_get_user_by_email: {e}")
    return None


def db_get_user_by_id(user_id: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("users").select("*").eq("id", user_id).limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"db_get_user_by_id: {e}")
    return None


def db_update_user(user_id: str, updates: dict) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("users").update(updates).eq("id", user_id).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"db_update_user: {e}")
    return None


## ── Signals ─────────────────────────────────────────────────────


def db_save_signal(user_id: str | None, signal: dict, score: dict | None) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        row = {
            "source_id": signal.get("source_id"),
            "source_name": signal.get("source_name"),
            "symbol": signal.get("symbol"),
            "direction": signal.get("direction"),
            "entry_price": signal.get("entry_price"),
            "stop_loss": signal.get("stop_loss"),
            "take_profit": signal.get("take_profit"),
            "raw_text": signal.get("raw_text", "")[:1000],
        }
        if user_id:
            row["user_id"] = user_id
            row["owner_id"] = user_id
            row["owner_kind"] = "user"
        if score:
            row["score"] = score.get("score")
            row["risk_level"] = score.get("risk_level")
            row["rationale"] = score.get("rationale", "")[:500]

        result = db.table("signals").insert(row).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"db_save_signal: {e}")
    return None


def db_get_signals(user_id: str | None = None, limit: int = 20) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        q = db.table("signals").select("*").order("received_at", desc=True).limit(limit)
        if user_id:
            q = q.eq("user_id", user_id)
        result = q.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"db_get_signals: {e}")
        return []


## ── Alerts ──────────────────────────────────────────────────────


def db_save_alert(user_id: str | None, alert: dict) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        row = {
            "account_id": alert.get("account_id"),
            "firm_name": alert.get("firm_name"),
            "rule_type": alert.get("rule_type"),
            "alert_level": alert.get("alert_level"),
            "message": alert.get("message", "")[:500],
            "remaining": alert.get("remaining"),
            "remaining_pct": alert.get("remaining_pct"),
        }
        if user_id:
            row["user_id"] = user_id
            row["owner_id"] = user_id
            row["owner_kind"] = "user"
        result = db.table("alerts").insert(row).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"db_save_alert: {e}")
    return None


def db_get_alerts(user_id: str | None = None, account_id: str | None = None, limit: int = 50) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        q = db.table("alerts").select("*").order("created_at", desc=True).limit(limit)
        if user_id:
            q = q.eq("user_id", user_id)
        if account_id:
            q = q.eq("account_id", account_id)
        result = q.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"db_get_alerts: {e}")
        return []


## ── AI Trade Logs ───────────────────────────────────────────────


def db_save_ai_trade_log(
    user_id: str | None = None,
    strategy_name: str = "",
    symbols: str = "",
    analysis: str = "",
    actions_planned: int = 0,
    actions_executed: int = 0,
    prompt: str = "",
    result: dict | None = None,
    dry_run: bool = True,
    *,
    owner_id: str | None = None,
    owner_kind: str | None = None,
) -> dict | None:
    """Insert an AI trade log row.

    Accepts either legacy `user_id` (for user callers) or explicit
    `owner_id`/`owner_kind` (needed for anon owners since `user_id` has
    an FK to `users`). When `user_id` is given, derives owner fields.
    """
    db = get_db()
    if not db:
        return None
    try:
        import json
        # Derive owner from legacy user_id param when caller didn't pass explicit.
        if owner_id is None and user_id is not None:
            owner_id = user_id
            owner_kind = "user"
        if owner_id is None or owner_kind is None:
            logger.warning("db_save_ai_trade_log: no owner context — skipping log")
            return None

        row = {
            "strategy_name": strategy_name,
            "symbols": symbols,
            "analysis": analysis[:2000] if analysis else "",
            "actions_planned": actions_planned,
            "actions_executed": actions_executed,
            "prompt": prompt[:5000] if prompt else "",
            "result": json.dumps(result, default=str)[:5000] if result else "{}",
            "dry_run": dry_run,
            "owner_id": owner_id,
            "owner_kind": owner_kind,
        }
        # user_id has FK to users, so only set it for 'user' kind.
        if owner_kind == "user":
            row["user_id"] = owner_id
        result_db = db.table("ai_trade_logs").insert(row).execute()
        if result_db.data:
            return result_db.data[0]
    except Exception as e:
        logger.error(f"db_save_ai_trade_log: {e}")
    return None


def db_get_ai_trade_logs(user_id: str | None = None, limit: int = 20) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        q = db.table("ai_trade_logs").select("*").order("created_at", desc=True).limit(limit)
        if user_id:
            q = q.eq("user_id", user_id)
        result = q.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"db_get_ai_trade_logs: {e}")
        return []


## ── Trading Strategies ──────────────────────────────────────────


def db_save_strategy(user_id: str, strategy: dict) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        row = {
            "user_id": user_id,
            "name": strategy.get("name", ""),
            "symbols": strategy.get("symbols", ""),
            "kline_period": strategy.get("kline_period", "1h"),
            "rules": strategy.get("rules", ""),
        }
        result = db.table("trading_strategies").insert(row).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"db_save_strategy: {e}")
        return None


def db_update_strategy(strategy_id: str, updates: dict) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        updates["updated_at"] = "now()"
        result = db.table("trading_strategies").update(updates).eq("id", strategy_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"db_update_strategy: {e}")
        return None


def db_get_strategies(user_id: str) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        result = db.table("trading_strategies").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"db_get_strategies: {e}")
        return []


def db_delete_strategy(strategy_id: str) -> bool:
    db = get_db()
    if not db:
        return False
    try:
        db.table("trading_strategies").delete().eq("id", strategy_id).execute()
        return True
    except Exception as e:
        logger.error(f"db_delete_strategy: {e}")
        return False


## ── Trading Accounts ────────────────────────────────────────────


def db_save_trading_account(user_id: str, account: dict) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        row = {
            "user_id": user_id,
            "owner_id": user_id,
            "owner_kind": "user",
            "account_id": account.get("account_id"),
            "firm_name": account.get("firm_name"),
            "account_size": account.get("account_size"),
            "broker_type": account.get("broker_type", "mock"),
            "label": account.get("label", ""),
        }
        result = db.table("trading_accounts").upsert(row, on_conflict="user_id,account_id").execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"db_save_trading_account: {e}")
    return None


def db_get_trading_accounts(user_id: str) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        result = db.table("trading_accounts").select("*").eq("user_id", user_id).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"db_get_trading_accounts: {e}")
        return []


def db_delete_trading_account(user_id: str, account_id: str) -> bool:
    db = get_db()
    if not db:
        return False
    try:
        db.table("trading_accounts").delete().eq("user_id", user_id).eq("account_id", account_id).execute()
        return True
    except Exception as e:
        logger.error(f"db_delete_trading_account: {e}")
        return False
