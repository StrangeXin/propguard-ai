"""
Trading statistics — calculates challenge progress, profit targets,
win rate, and performance metrics from account data.
"""

from datetime import datetime
from app.models.account import AccountState


def calculate_challenge_progress(account: AccountState, firm_rules: dict) -> dict:
    """Calculate overall challenge progress including profit target."""
    initial = account.initial_balance
    equity = account.current_equity
    total_pnl = account.total_pnl

    # Find profit target from firm rules
    profit_target_pct = None
    accounts = firm_rules.get("accounts", [])
    for acc in accounts:
        if acc.get("size") == account.account_size:
            profit_target_pct = acc.get("profit_target_phase1_pct") or acc.get("profit_target_pct")
            break

    # Default to first account's target if not found
    if profit_target_pct is None and accounts:
        profit_target_pct = accounts[0].get("profit_target_phase1_pct") or accounts[0].get("profit_target_pct", 10)

    profit_target_usd = initial * (profit_target_pct / 100) if profit_target_pct else initial * 0.1
    profit_progress_pct = (max(total_pnl, 0) / profit_target_usd * 100) if profit_target_usd > 0 else 0

    # Drawdown usage
    dd_rule = next((r for r in firm_rules.get("rules", []) if r["type"] == "max_drawdown"), None)
    dd_limit = 0
    dd_used = 0
    if dd_rule:
        val = dd_rule.get("value")
        if val and "percent" in dd_rule.get("unit", ""):
            dd_limit = initial * (float(val) / 100)
        elif val:
            dd_limit = float(val)
        dd_used = max(
            (account.equity_high_watermark if dd_rule.get("trailing") else initial) - equity,
            0,
        )

    dd_used_pct = (dd_used / dd_limit * 100) if dd_limit > 0 else 0

    # Trading days
    min_days_rule = next((r for r in firm_rules.get("rules", []) if r["type"] == "min_trading_days"), None)
    min_days = int(min_days_rule["value"]) if min_days_rule and min_days_rule.get("value") else 0

    # Days since start
    days_elapsed = 0
    if account.challenge_start_date:
        days_elapsed = (datetime.now() - account.challenge_start_date).days

    return {
        "profit_target": round(profit_target_usd, 2),
        "profit_target_pct": profit_target_pct,
        "current_profit": round(max(total_pnl, 0), 2),
        "profit_progress_pct": round(min(profit_progress_pct, 100), 1),
        "drawdown_limit": round(dd_limit, 2),
        "drawdown_used": round(dd_used, 2),
        "drawdown_used_pct": round(min(dd_used_pct, 100), 1),
        "drawdown_remaining": round(max(dd_limit - dd_used, 0), 2),
        "trading_days": account.trading_days_count,
        "min_trading_days": min_days,
        "days_elapsed": days_elapsed,
        "account_size": account.account_size,
        "initial_balance": initial,
        "current_equity": round(equity, 2),
        "total_pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl / initial * 100, 2) if initial > 0 else 0,
    }
