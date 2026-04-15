"""
Alert service — sends compliance alerts via Telegram and stores alert history.
"""

import logging
from datetime import datetime

from app.models.account import AlertLevel, ComplianceReport, RuleCheckResult
from app.config import get_settings

logger = logging.getLogger(__name__)


# Track last alert level per account+rule to avoid spam
_last_alerts: dict[str, AlertLevel] = {}


def _alert_key(account_id: str, rule_type: str) -> str:
    return f"{account_id}:{rule_type}"


def should_send_alert(account_id: str, check: RuleCheckResult) -> bool:
    """Only alert when the level escalates (gets worse), not on every tick."""
    key = _alert_key(account_id, check.rule_type)
    previous = _last_alerts.get(key, AlertLevel.SAFE)

    severity_order = [AlertLevel.SAFE, AlertLevel.WARNING, AlertLevel.CRITICAL, AlertLevel.DANGER, AlertLevel.BREACHED]

    current_idx = severity_order.index(check.alert_level)
    previous_idx = severity_order.index(previous)

    if current_idx > previous_idx:
        _last_alerts[key] = check.alert_level
        return True

    # Reset tracking if the situation improves back to SAFE
    if check.alert_level == AlertLevel.SAFE and previous != AlertLevel.SAFE:
        _last_alerts[key] = AlertLevel.SAFE

    return False


def format_telegram_alert(report: ComplianceReport, check: RuleCheckResult) -> str:
    """Format a compliance alert for Telegram."""
    emoji = {
        AlertLevel.WARNING: "⚠️",
        AlertLevel.CRITICAL: "🔴",
        AlertLevel.DANGER: "🚨",
        AlertLevel.BREACHED: "💀",
    }.get(check.alert_level, "ℹ️")

    lines = [
        f"{emoji} *PropGuard Alert — {report.firm_name}*",
        f"Account: `{report.account_id}`",
        f"Rule: {check.rule_type.replace('_', ' ').title()}",
        "",
        check.message,
        "",
        f"Remaining: ${check.remaining:.2f} ({check.remaining_pct:.1f}%)",
        f"Time: {report.timestamp.strftime('%H:%M:%S %Z')}",
    ]

    if check.alert_level == AlertLevel.DANGER:
        lines.append("\n*⛔ RECOMMENDATION: Stop trading for today.*")
    elif check.alert_level == AlertLevel.BREACHED:
        lines.append("\n*💀 LIMIT BREACHED — Account may be violated.*")

    return "\n".join(lines)


async def send_telegram_alert(chat_id: str, message: str):
    """Send alert via Telegram Bot API."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, skipping alert")
        return

    try:
        import httpx
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            })
        logger.info(f"Telegram alert sent to {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")


async def get_user_telegram_chat_id(account_id: str) -> str | None:
    """Look up the Telegram chat_id for the user who owns this account."""
    try:
        from app.services.database import get_db
        db = get_db()
        if db:
            # Find user by their trading account
            result = db.table("trading_accounts").select("user_id").eq("account_id", account_id).limit(1).execute()
            if result.data:
                user_id = result.data[0]["user_id"]
                user = db.table("users").select("telegram_chat_id").eq("id", user_id).limit(1).execute()
                if user.data and user.data[0].get("telegram_chat_id"):
                    return user.data[0]["telegram_chat_id"]
    except Exception:
        pass
    return None


async def process_compliance_alerts(
    report: ComplianceReport, telegram_chat_id: str | None = None
) -> list[str]:
    """
    Check compliance report for alerts that need to be sent.
    Returns list of alert messages that were triggered.
    """
    triggered: list[str] = []

    from app.services.alert_history import record_alert

    for check in report.checks:
        if check.alert_level in (AlertLevel.WARNING, AlertLevel.CRITICAL, AlertLevel.DANGER, AlertLevel.BREACHED):
            if should_send_alert(report.account_id, check):
                message = format_telegram_alert(report, check)
                triggered.append(message)

                # Record to history
                record_alert(
                    account_id=report.account_id,
                    firm_name=report.firm_name,
                    rule_type=check.rule_type,
                    alert_level=check.alert_level.value,
                    message=check.message,
                    remaining=check.remaining,
                    remaining_pct=check.remaining_pct,
                )

                # Send to Telegram
                chat_id = telegram_chat_id or await get_user_telegram_chat_id(report.account_id)
                if chat_id:
                    await send_telegram_alert(chat_id, message)

    return triggered
