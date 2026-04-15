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
    """Check daily loss limit compliance."""
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
        limit_usd = account.initial_balance * (limit_value / 100)
    else:
        limit_usd = limit_value

    current_loss = abs(min(account.daily_pnl, 0))
    remaining = limit_usd - current_loss
    remaining_pct = (remaining / limit_usd * 100) if limit_usd > 0 else 100.0

    alert_level = _get_alert_level(remaining_pct)
    message = _build_daily_loss_message(
        alert_level, remaining, limit_usd, current_loss, firm_rules["firm_name"]
    )

    return RuleCheckResult(
        rule_type="daily_loss",
        rule_description=rule.get("description", "Daily loss limit"),
        current_value=current_loss,
        limit_value=limit_usd,
        remaining=remaining,
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
    """Check maximum drawdown compliance."""
    limit_value = _resolve_rule_value(rule, account.account_size)
    if limit_value is None:
        return None

    unit = rule.get("unit", "")
    is_trailing = rule.get("trailing", False)

    if "percent" in unit:
        if is_trailing:
            limit_usd = account.equity_high_watermark * (limit_value / 100)
            floor = account.equity_high_watermark - limit_usd
        else:
            limit_usd = account.initial_balance * (limit_value / 100)
            floor = account.initial_balance - limit_usd
    else:
        limit_usd = limit_value
        if is_trailing:
            floor = account.equity_high_watermark - limit_usd
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
    dd_type = "trailing" if is_trailing else "static"

    if alert_level == AlertLevel.BREACHED:
        message = f"BREACHED: Max drawdown ({dd_type}) exceeded! Account equity ${account.current_equity:.2f} below floor ${floor:.2f}."
    elif alert_level == AlertLevel.DANGER:
        message = f"DANGER: ${remaining:.2f} from max drawdown ({dd_type}) breach! Equity floor: ${floor:.2f}."
    elif alert_level == AlertLevel.CRITICAL:
        message = f"CRITICAL: ${remaining:.2f} remaining before max drawdown ({dd_type}) breach."
    elif alert_level == AlertLevel.WARNING:
        message = f"WARNING: ${remaining:.2f} remaining before max drawdown ({dd_type}) limit."
    else:
        message = f"Drawdown ({dd_type}): ${current_drawdown:.2f} of ${limit_usd:.2f} max. ${remaining:.2f} remaining."

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


# Map rule types to checker functions
RULE_CHECKERS = {
    "daily_loss": check_daily_loss,
    "max_drawdown": check_max_drawdown,
    "position_size": check_position_size,
    "min_trading_days": check_min_trading_days,
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
