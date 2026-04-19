"""
Pre-market AI Briefing — generates daily briefing for each account.

Design doc: 盘前 AI 简报
- Today's top 3 signals + market sentiment + account risk assessment
- Uses Claude API with fallback to template-based briefing
"""

import json
import logging
from datetime import datetime

from app.models.account import AccountState, ComplianceReport, AlertLevel
from app.models.signal import ScoredSignal
from app.config import get_settings

logger = logging.getLogger(__name__)

BRIEFING_PROMPT = """You are PropGuard AI, a trading risk management assistant. Generate a concise pre-market briefing.

Account Status:
- Firm: {firm_name} (${account_size} challenge)
- Current Equity: ${equity}
- Daily P&L: ${daily_pnl}
- Total P&L: ${total_pnl}
- Max Drawdown Used: ${dd_used} of ${dd_limit} ({dd_pct}%)
- Trading Days: {trading_days}
- Open Positions: {positions_count}

Compliance Status: {overall_status}
{compliance_details}

Top Signals Today:
{signals_summary}

Generate a briefing with these sections (keep each section to 2-3 sentences):
1. RISK STATUS — current account health and how close to limits
2. TODAY'S FOCUS — what to watch, based on signals and positions
3. RECOMMENDATION — one specific action for today

Be direct. Use numbers. No fluff. If the account is in danger, say so plainly.
Respond in the same language as the user's firm name context (English by default)."""


def _format_compliance_details(report: ComplianceReport) -> str:
    lines = []
    for check in report.checks:
        status = "OK" if check.alert_level == AlertLevel.SAFE else check.alert_level.value.upper()
        lines.append(f"  - {check.rule_type}: {status} (${check.remaining:.0f} remaining, {check.remaining_pct:.0f}%)")
    return "\n".join(lines) if lines else "  No checks available"


def _format_signals_summary(signals: list[ScoredSignal]) -> str:
    if not signals:
        return "  No signals available"
    lines = []
    for i, s in enumerate(signals[:5], 1):
        score_str = f"{s.score.score}/100" if s.score else "unscored"
        risk_str = s.score.risk_level.value if s.score else "unknown"
        lines.append(
            f"  {i}. {s.signal.symbol} {s.signal.direction.value.upper()} — "
            f"Score: {score_str}, Risk: {risk_str}"
        )
    return "\n".join(lines)


def generate_template_briefing(
    account: AccountState,
    report: ComplianceReport,
    top_signals: list[ScoredSignal],
) -> dict:
    """Template-based briefing when Claude API is unavailable."""
    # Risk status
    if report.overall_status == AlertLevel.BREACHED:
        risk = "CRITICAL: One or more limits have been breached. Do not trade until the situation is resolved."
    elif report.overall_status == AlertLevel.DANGER:
        risk = f"HIGH RISK: Account is very close to limits. Equity: ${account.current_equity:,.2f}. Reduce exposure immediately."
    elif report.overall_status == AlertLevel.CRITICAL:
        risk = f"ELEVATED RISK: Approaching limits. Equity: ${account.current_equity:,.2f}. Trade with reduced size."
    elif report.overall_status == AlertLevel.WARNING:
        risk = f"MODERATE: Some limits approaching. Equity: ${account.current_equity:,.2f}. Monitor closely."
    else:
        risk = f"HEALTHY: All limits well within bounds. Equity: ${account.current_equity:,.2f}. Normal trading conditions."

    # Today's focus
    if top_signals:
        best = top_signals[0]
        focus = (
            f"Top signal: {best.signal.symbol} {best.signal.direction.value.upper()} "
            f"(score: {best.score.score}/100). "
            f"{len(top_signals)} signals available for review."
        )
    else:
        focus = "No strong signals today. Consider staying flat or reducing positions."

    # Recommendation
    dd_check = next((c for c in report.checks if c.rule_type == "max_drawdown"), None)
    daily_check = next((c for c in report.checks if c.rule_type == "daily_loss"), None)

    if report.overall_status in (AlertLevel.DANGER, AlertLevel.BREACHED):
        rec = "DO NOT open new positions. Close any losing positions to protect remaining drawdown budget."
    elif daily_check and daily_check.remaining_pct < 30:
        rec = f"Daily loss budget is tight (${daily_check.remaining:.0f} remaining). Consider stopping for the day."
    elif dd_check and dd_check.remaining_pct < 40:
        rec = f"Overall drawdown at {100 - dd_check.remaining_pct:.0f}% used. Trade small — max 0.5% risk per trade."
    else:
        rec = "Normal conditions. Stick to your trading plan. Max 1% risk per trade."

    return {
        "generated_at": datetime.now().isoformat(),
        "firm_name": account.firm_name,
        "account_id": account.account_id,
        "sections": {
            "risk_status": risk,
            "todays_focus": focus,
            "recommendation": rec,
        },
        "signals_count": len(top_signals),
        "overall_status": report.overall_status.value,
        "source": "template",
    }


async def generate_ai_briefing(
    account: AccountState,
    report: ComplianceReport,
    top_signals: list[ScoredSignal],
    owner=None,
    consume_quota: bool = True,
) -> dict:
    """Generate briefing using Claude API via AIClient.

    Falls back to template-based briefing if `owner` is missing or Claude
    call fails. `consume_quota=False` skips quota enforcement inside AIClient
    when the route layer already consumed via @require_quota.
    """
    settings = get_settings()

    if not settings.anthropic_api_key or owner is None:
        return generate_template_briefing(account, report, top_signals)

    try:
        from app.services.ai_client import AIClient
        from app.services.quota import QuotaExceeded

        dd_check = next((c for c in report.checks if c.rule_type == "max_drawdown"), None)

        prompt = BRIEFING_PROMPT.format(
            firm_name=account.firm_name,
            account_size=f"{account.account_size:,}",
            equity=f"{account.current_equity:,.2f}",
            daily_pnl=f"{account.daily_pnl:+,.2f}",
            total_pnl=f"{account.total_pnl:+,.2f}",
            dd_used=f"{dd_check.current_value:,.0f}" if dd_check else "N/A",
            dd_limit=f"{dd_check.limit_value:,.0f}" if dd_check else "N/A",
            dd_pct=f"{100 - dd_check.remaining_pct:.0f}" if dd_check else "N/A",
            trading_days=account.trading_days_count,
            positions_count=len(account.open_positions),
            overall_status=report.overall_status.value.upper(),
            compliance_details=_format_compliance_details(report),
            signals_summary=_format_signals_summary(top_signals),
        )

        ai = AIClient(owner)
        try:
            resp = await ai.briefing(
                system_prompt="", user_prompt=prompt, max_tokens=500,
                consume_quota=consume_quota,
            )
        except QuotaExceeded:
            raise  # propagate to route layer for 402

        briefing_text = resp["text"].strip()

        return {
            "generated_at": datetime.now().isoformat(),
            "firm_name": account.firm_name,
            "account_id": account.account_id,
            "briefing": briefing_text,
            "signals_count": len(top_signals),
            "overall_status": report.overall_status.value,
            "source": "ai",
        }

    except Exception as e:
        logger.warning(f"AI briefing failed, falling back to template: {e}")
        return generate_template_briefing(account, report, top_signals)
