"""
PropGuard Rule Engine — loads prop firm rules from JSON and evaluates
account state against them in real-time.
"""

import json
from pathlib import Path
from datetime import datetime

from app.models.account import (
    AccountState,
    AlertLevel,
    ComplianceReport,
    RuleCheckResult,
)
from app.config import get_settings

# Find rules dir: works both locally (backend/../data) and in Docker (/app/data)
_engine_dir = Path(__file__).parent  # app/rules/
_candidates = [
    _engine_dir.parent.parent.parent / "data" / "prop_firm_rules",  # local: backend/../data
    _engine_dir.parent.parent / "data" / "prop_firm_rules",         # docker: /app/data
]
RULES_DIR = next((p for p in _candidates if p.exists()), _candidates[0])


def load_firm_rules(firm_name: str) -> dict:
    """Load rules JSON for a specific prop firm."""
    path = RULES_DIR / f"{firm_name.lower()}.json"
    if not path.exists():
        raise FileNotFoundError(f"No rules found for firm: {firm_name}")
    with open(path) as f:
        return json.load(f)


def list_available_firms() -> list[dict]:
    """Return metadata for all available prop firm rule sets."""
    firms = []
    for path in RULES_DIR.glob("*.json"):
        if path.name == "schema.json":
            continue
        with open(path) as f:
            data = json.load(f)
            firms.append({
                "firm_name": data["firm_name"],
                "markets": data["markets"],
                "evaluation_type": data["evaluation_type"],
                "version": data["version"],
                "effective_date": data["effective_date"],
                "account_sizes": [a["size"] for a in data.get("accounts", [])],
            })
    return firms


def _get_alert_level(remaining_pct: float) -> AlertLevel:
    """Determine alert level based on percentage of limit remaining."""
    settings = get_settings()
    if remaining_pct <= 0:
        return AlertLevel.BREACHED
    if remaining_pct <= settings.alert_threshold_danger:
        return AlertLevel.DANGER
    if remaining_pct <= settings.alert_threshold_critical:
        return AlertLevel.CRITICAL
    if remaining_pct <= settings.alert_threshold_warning:
        return AlertLevel.WARNING
    return AlertLevel.SAFE


def _resolve_rule_value(rule: dict, account_size: int) -> float | None:
    """Get rule value, handling per-account-size rules."""
    if "value" in rule and rule["value"] is not None:
        return float(rule["value"])
    if "value_by_account" in rule:
        size_key = str(account_size)
        if size_key in rule["value_by_account"]:
            return float(rule["value_by_account"][size_key])
    return None


def check_daily_loss(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """
    Check daily loss limit compliance.

    FTMO: Floor = max(balance_at_midnight, initial_balance) - 5% * initial_balance
          The 5% is always of INITIAL balance, but the reference point is
          the higher of midnight balance or initial balance.
    TopStep: Fixed USD amount, resets at 5PM CT. NOT a violation, just liquidation.
    Breakout: Percent of initial balance. Breach = permanent account loss.
    """
    if rule.get("has_daily_limit") is False:
        return RuleCheckResult(
            rule_type="daily_loss",
            rule_description="No daily loss limit for this firm",
            current_value=abs(min(account.daily_pnl, 0)),
            limit_value=0,
            remaining=999999.0,
            remaining_pct=100.0,
            alert_level=AlertLevel.SAFE,
            message=f"{firm_rules['firm_name']} does not enforce a daily loss limit.",
        )

    limit_value = _resolve_rule_value(rule, account.account_size)
    if limit_value is None:
        return None

    unit = rule.get("unit", "")
    if "percent" in unit:
        # FTMO/Breakout: percentage of initial balance
        limit_usd = account.initial_balance * (limit_value / 100)

        # FTMO specific: floor is based on max(midnight_balance, initial) - limit
        # Since we don't have midnight snapshot, use max(current_balance, initial) as approximation
        # This is conservative (may show less room than reality)
        reference = max(account.current_balance, account.initial_balance)
        floor = reference - limit_usd
        current_loss = max(reference - account.current_equity, 0)
    else:
        # TopStep: fixed USD amount
        limit_usd = limit_value
        current_loss = abs(min(account.daily_pnl, 0))

    remaining = limit_usd - current_loss
    remaining_pct = (remaining / limit_usd * 100) if limit_usd > 0 else 100.0

    alert_level = _get_alert_level(remaining_pct)

    # Add breach consequence to message
    is_violation = rule.get("is_violation", True)
    consequence = "Account violation!" if is_violation else "Positions liquidated, trading paused until next session."

    message = _build_daily_loss_message(
        alert_level, remaining, limit_usd, current_loss, firm_rules["firm_name"]
    )
    if alert_level == AlertLevel.BREACHED:
        message += f" {consequence}"

    return RuleCheckResult(
        rule_type="daily_loss",
        rule_description=rule.get("description", "Daily loss limit"),
        current_value=round(current_loss, 2),
        limit_value=round(limit_usd, 2),
        remaining=round(max(remaining, 0), 2),
        remaining_pct=max(remaining_pct, 0),
        alert_level=alert_level,
        message=message,
    )


def _build_daily_loss_message(
    level: AlertLevel, remaining: float, limit: float, current: float, firm: str
) -> str:
    if level == AlertLevel.BREACHED:
        return f"BREACHED: Daily loss limit exceeded! Lost ${current:.2f} / ${limit:.2f} allowed by {firm}."
    if level == AlertLevel.DANGER:
        return f"DANGER: Only ${remaining:.2f} left before daily loss limit! Stop trading now."
    if level == AlertLevel.CRITICAL:
        return f"CRITICAL: ${remaining:.2f} remaining before daily loss limit. Consider closing positions."
    if level == AlertLevel.WARNING:
        return f"WARNING: ${remaining:.2f} remaining before daily loss limit ({firm})."
    return f"Daily loss: ${current:.2f} used of ${limit:.2f} limit. ${remaining:.2f} remaining."


def check_max_drawdown(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """
    Check maximum drawdown compliance.

    FTMO: Static 10% of initial balance. Floor never moves.
    TopStep: END-OF-DAY trailing. Floor trails highest END-OF-DAY BALANCE
             (not intraday equity). Once floor reaches initial balance, it locks.
    Breakout: Static. 6% Classic / 5% Pro / 3% Turbo.
    """
    limit_value = _resolve_rule_value(rule, account.account_size)
    if limit_value is None:
        return None

    unit = rule.get("unit", "")
    is_trailing = rule.get("trailing", False)
    trailing_type = rule.get("trailing_type", "")

    if "percent" in unit:
        if is_trailing:
            # TopStep: trailing from equity high watermark
            # In production, this should be end-of-day balance high watermark
            # Using equity_high_watermark as best available approximation
            # NOTE: This is MORE conservative than official (intraday vs EOD)
            hwm = account.equity_high_watermark
            limit_usd = hwm * (limit_value / 100)
            floor = hwm - limit_usd
            # TopStep: once floor reaches initial balance, it locks
            floor = max(floor, account.initial_balance - limit_usd)
        else:
            limit_usd = account.initial_balance * (limit_value / 100)
            floor = account.initial_balance - limit_usd
    else:
        limit_usd = limit_value
        if is_trailing:
            # TopStep USD-based: trails highest EOD balance
            hwm = account.equity_high_watermark
            floor = hwm - limit_usd
        else:
            floor = account.initial_balance - limit_usd

    current_drawdown = max(
        (account.equity_high_watermark if is_trailing else account.initial_balance)
        - account.current_equity,
        0,
    )
    remaining = limit_usd - current_drawdown
    remaining_pct = (remaining / limit_usd * 100) if limit_usd > 0 else 100.0

    alert_level = _get_alert_level(remaining_pct)

    if is_trailing and trailing_type == "end_of_day_balance":
        dd_label = "EOD trailing"
        note = f" Floor: ${floor:.2f} (trails EOD balance, currently at HWM ${account.equity_high_watermark:.2f})"
    elif is_trailing:
        dd_label = "trailing"
        note = f" Floor: ${floor:.2f}"
    else:
        dd_label = "static"
        note = f" Floor: ${floor:.2f} (fixed)"

    if alert_level == AlertLevel.BREACHED:
        message = f"BREACHED: Max drawdown ({dd_label}) exceeded! Equity ${account.current_equity:.2f} below floor ${floor:.2f}."
    elif alert_level == AlertLevel.DANGER:
        message = f"DANGER: ${remaining:.2f} from max drawdown breach!{note}"
    elif alert_level == AlertLevel.CRITICAL:
        message = f"CRITICAL: ${remaining:.2f} remaining before max drawdown breach.{note}"
    elif alert_level == AlertLevel.WARNING:
        message = f"WARNING: ${remaining:.2f} remaining before max drawdown limit.{note}"
    else:
        message = f"Drawdown ({dd_label}): ${current_drawdown:.2f} of ${limit_usd:.2f} max. ${remaining:.2f} remaining.{note}"

    return RuleCheckResult(
        rule_type="max_drawdown",
        rule_description=rule.get("description", "Maximum drawdown"),
        current_value=current_drawdown,
        limit_value=limit_usd,
        remaining=remaining,
        remaining_pct=max(remaining_pct, 0),
        alert_level=alert_level,
        message=message,
    )


def check_position_size(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """Check position size limits."""
    limit = _resolve_rule_value(rule, account.account_size)
    if limit is None:
        return None

    total_positions = sum(abs(p.size) for p in account.open_positions)
    remaining = limit - total_positions
    remaining_pct = (remaining / limit * 100) if limit > 0 else 100.0

    alert_level = _get_alert_level(remaining_pct)
    message = f"Position size: {total_positions:.1f} / {limit:.0f} {rule.get('unit', 'contracts')}. {remaining:.1f} remaining."

    return RuleCheckResult(
        rule_type="position_size",
        rule_description=rule.get("description", "Position size limit"),
        current_value=total_positions,
        limit_value=limit,
        remaining=remaining,
        remaining_pct=max(remaining_pct, 0),
        alert_level=alert_level,
        message=message,
    )


def check_min_trading_days(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """Check minimum trading days progress."""
    required = rule.get("value")
    if required is None:
        return None

    remaining = max(required - account.trading_days_count, 0)

    return RuleCheckResult(
        rule_type="min_trading_days",
        rule_description=rule.get("description", "Minimum trading days"),
        current_value=float(account.trading_days_count),
        limit_value=float(required),
        remaining=float(remaining),
        remaining_pct=(account.trading_days_count / required * 100) if required > 0 else 100.0,
        alert_level=AlertLevel.SAFE,
        message=f"Trading days: {account.trading_days_count} / {required} required.",
    )


def check_news_restriction(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """Check if currently in a news restriction period."""
    if not rule.get("value"):
        return RuleCheckResult(
            rule_type="news_restriction",
            rule_description="No news trading restrictions",
            current_value=0, limit_value=0, remaining=999999, remaining_pct=100,
            alert_level=AlertLevel.SAFE,
            message=f"{firm_rules['firm_name']} has no news trading restrictions.",
        )

    # Check if any position was opened recently (potential news trade)
    from datetime import datetime, timedelta
    now = datetime.now()
    recent_positions = [
        p for p in account.open_positions
        if (now - p.opened_at).total_seconds() < 300  # opened in last 5 min
    ]

    if recent_positions:
        return RuleCheckResult(
            rule_type="news_restriction",
            rule_description=rule.get("description", "News trading restriction"),
            current_value=float(len(recent_positions)),
            limit_value=0, remaining=0, remaining_pct=50,
            alert_level=AlertLevel.WARNING,
            message=f"Warning: {len(recent_positions)} position(s) opened recently. Check economic calendar for high-impact news events.",
        )

    return RuleCheckResult(
        rule_type="news_restriction",
        rule_description=rule.get("description", "News trading restriction active"),
        current_value=0, limit_value=0, remaining=999999, remaining_pct=100,
        alert_level=AlertLevel.SAFE,
        message="No recent trades near news events. Check calendar before opening positions.",
    )


def check_trading_hours(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """Check if current time is within allowed trading hours."""
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Mon, 6=Sun

    # CME futures: Sunday 5pm - Friday 4pm CT (roughly)
    # Simplified: no trading on weekends
    is_weekend = weekday >= 5

    if is_weekend and account.open_positions:
        return RuleCheckResult(
            rule_type="trading_hours",
            rule_description=rule.get("description", "Trading hours restriction"),
            current_value=float(len(account.open_positions)),
            limit_value=0, remaining=0, remaining_pct=0,
            alert_level=AlertLevel.WARNING,
            message=f"Weekend: {len(account.open_positions)} position(s) open. Check if overnight/weekend holding is allowed.",
        )

    return RuleCheckResult(
        rule_type="trading_hours",
        rule_description=rule.get("description", "Trading hours"),
        current_value=0, limit_value=0, remaining=999999, remaining_pct=100,
        alert_level=AlertLevel.SAFE,
        message="Within trading hours." if not is_weekend else "Weekend — market closed.",
    )


def check_leverage(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """Check leverage limits per asset."""
    value_by_asset = rule.get("value_by_asset")
    if not value_by_asset:
        return None

    # Check each position against leverage limits
    violations = []
    for pos in account.open_positions:
        symbol = pos.symbol.upper()
        for asset, max_lev in value_by_asset.items():
            if asset.upper() in symbol:
                # Simplified leverage check
                notional = pos.size * pos.current_price
                account_equity = account.current_equity
                effective_leverage = notional / account_equity if account_equity > 0 else 0
                if effective_leverage > max_lev:
                    violations.append(f"{symbol}: {effective_leverage:.1f}x (max {max_lev}x)")

    if violations:
        return RuleCheckResult(
            rule_type="leverage",
            rule_description=rule.get("description", "Leverage limits"),
            current_value=float(len(violations)),
            limit_value=0, remaining=0, remaining_pct=0,
            alert_level=AlertLevel.DANGER,
            message=f"Leverage exceeded: {', '.join(violations)}",
        )

    return RuleCheckResult(
        rule_type="leverage",
        rule_description=rule.get("description", "Leverage limits"),
        current_value=0, limit_value=0, remaining=999999, remaining_pct=100,
        alert_level=AlertLevel.SAFE,
        message="All positions within leverage limits.",
    )


def check_time_limit(
    account: AccountState, rule: dict, firm_rules: dict
) -> RuleCheckResult | None:
    """Check challenge time limit."""
    if rule.get("value") is None:
        return RuleCheckResult(
            rule_type="time_limit",
            rule_description="No time limit",
            current_value=0, limit_value=0, remaining=999999, remaining_pct=100,
            alert_level=AlertLevel.SAFE,
            message=f"{firm_rules['firm_name']}: No time limit. Trade at your own pace.",
        )

    limit_days = float(rule["value"])
    if account.challenge_start_date:
        from datetime import datetime
        elapsed = (datetime.now() - account.challenge_start_date).days
        remaining = max(limit_days - elapsed, 0)
        remaining_pct = (remaining / limit_days * 100) if limit_days > 0 else 100
        alert_level = _get_alert_level(remaining_pct)
        return RuleCheckResult(
            rule_type="time_limit",
            rule_description=rule.get("description", "Challenge time limit"),
            current_value=float(elapsed),
            limit_value=limit_days,
            remaining=remaining,
            remaining_pct=remaining_pct,
            alert_level=alert_level,
            message=f"Day {elapsed} of {int(limit_days)}. {int(remaining)} days remaining.",
        )

    return None


# Map rule types to checker functions
RULE_CHECKERS = {
    "daily_loss": check_daily_loss,
    "max_drawdown": check_max_drawdown,
    "position_size": check_position_size,
    "min_trading_days": check_min_trading_days,
    "news_restriction": check_news_restriction,
    "trading_hours": check_trading_hours,
    "leverage": check_leverage,
    "time_limit": check_time_limit,
}


def evaluate_compliance(account: AccountState) -> ComplianceReport:
    """
    Run all applicable rule checks for an account and return a compliance report.
    This is the main entry point for the rule engine.
    """
    firm_rules = load_firm_rules(account.firm_name)
    checks: list[RuleCheckResult] = []

    for rule in firm_rules["rules"]:
        checker = RULE_CHECKERS.get(rule["type"])
        if checker:
            result = checker(account, rule, firm_rules)
            if result:
                checks.append(result)

    # Overall status is the worst alert level across all checks
    if not checks:
        overall = AlertLevel.SAFE
    else:
        priority = [AlertLevel.BREACHED, AlertLevel.DANGER, AlertLevel.CRITICAL, AlertLevel.WARNING, AlertLevel.SAFE]
        overall = AlertLevel.SAFE
        for level in priority:
            if any(c.alert_level == level for c in checks):
                overall = level
                break

    return ComplianceReport(
        account_id=account.account_id,
        firm_name=account.firm_name,
        timestamp=datetime.now(),
        overall_status=overall,
        checks=checks,
    )
