"""CRUD for sandbox broker tables.

Pure data layer. Broker logic (pricing, pnl computation) belongs in
sandbox_broker.py.
"""

import logging
from datetime import datetime

from app.services.database import get_db

logger = logging.getLogger(__name__)


def sandbox_get_or_create_account(owner_id: str, owner_kind: str,
                                   initial_balance: float = 100000.0,
                                   firm_name: str = "ftmo") -> dict:
    db = get_db()
    if not db:
        return {
            "owner_id": owner_id, "owner_kind": owner_kind,
            "initial_balance": initial_balance, "balance": initial_balance,
            "firm_name": firm_name,
        }
    try:
        result = db.table("sandbox_accounts").select("*").eq("owner_id", owner_id).limit(1).execute()
        if result.data:
            return result.data[0]
        insert = db.table("sandbox_accounts").insert({
            "owner_id": owner_id,
            "owner_kind": owner_kind,
            "initial_balance": initial_balance,
            "balance": initial_balance,
            "firm_name": firm_name,
        }).execute()
        return insert.data[0] if insert.data else {}
    except Exception as e:
        logger.error(f"sandbox_get_or_create_account: {e}")
        return {}


def sandbox_update_balance(owner_id: str, new_balance: float) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_accounts").update({"balance": new_balance}).eq("owner_id", owner_id).execute()
    except Exception as e:
        logger.error(f"sandbox_update_balance: {e}")


def sandbox_update_firm(owner_id: str, firm_name: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_accounts").update({"firm_name": firm_name}).eq("owner_id", owner_id).execute()
    except Exception as e:
        logger.error(f"sandbox_update_firm: {e}")


def sandbox_insert_position(owner_id: str, owner_kind: str, *, symbol: str,
                             side: str, size: float, entry_price: float,
                             stop_loss: float | None = None,
                             take_profit: float | None = None) -> str | None:
    db = get_db()
    if not db:
        return None
    try:
        row = {
            "owner_id": owner_id,
            "owner_kind": owner_kind,
            "symbol": symbol,
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }
        result = db.table("sandbox_positions").insert(row).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        logger.error(f"sandbox_insert_position: {e}")
        return None


def sandbox_list_positions(owner_id: str) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        result = db.table("sandbox_positions").select("*").eq("owner_id", owner_id).order("opened_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"sandbox_list_positions: {e}")
        return []


def sandbox_get_position(position_id: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        result = db.table("sandbox_positions").select("*").eq("id", position_id).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"sandbox_get_position: {e}")
        return None


def sandbox_update_position(position_id: str, updates: dict) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_positions").update(updates).eq("id", position_id).execute()
    except Exception as e:
        logger.error(f"sandbox_update_position: {e}")


def sandbox_delete_position(position_id: str) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_positions").delete().eq("id", position_id).execute()
    except Exception as e:
        logger.error(f"sandbox_delete_position: {e}")


def sandbox_insert_closed_trade(owner_id: str, owner_kind: str, *,
                                 symbol: str, side: str, size: float,
                                 entry_price: float, exit_price: float,
                                 pnl: float,
                                 opened_at: datetime,
                                 closed_at: datetime) -> None:
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_closed_trades").insert({
            "owner_id": owner_id,
            "owner_kind": owner_kind,
            "symbol": symbol,
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "opened_at": opened_at.isoformat(),
            "closed_at": closed_at.isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"sandbox_insert_closed_trade: {e}")


def sandbox_list_closed_trades(owner_id: str, limit: int = 50) -> list[dict]:
    db = get_db()
    if not db:
        return []
    try:
        result = db.table("sandbox_closed_trades").select("*").eq("owner_id", owner_id).order("closed_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"sandbox_list_closed_trades: {e}")
        return []


def sandbox_reset_account(owner_id: str, owner_kind: str,
                           initial_balance: float = 100000.0) -> None:
    """Wipe positions/orders/history, reset balance to initial."""
    db = get_db()
    if not db:
        return
    try:
        db.table("sandbox_positions").delete().eq("owner_id", owner_id).execute()
        db.table("sandbox_orders").delete().eq("owner_id", owner_id).execute()
        db.table("sandbox_closed_trades").delete().eq("owner_id", owner_id).execute()
        db.table("sandbox_accounts").update({"balance": initial_balance}).eq("owner_id", owner_id).execute()
    except Exception as e:
        logger.error(f"sandbox_reset_account: {e}")
