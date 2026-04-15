"""
Telegram Bot service — receives forwarded trading signals from users.

Design doc: V1 uses "user forward" mode only. Users forward messages from
signal groups to our bot. No userbot scraping (Telegram ToS violation).

Flow:
1. User adds @PropGuardBot to their Telegram
2. User forwards signal messages from their signal groups to the bot
3. Bot parses the signal and scores it
4. Bot replies with the score and risk assessment
"""

import logging
from datetime import datetime

from app.services.signal_parser import parse_signal
from app.services.ai_scorer import score_signal, get_source_stats, register_source
from app.models.signal import SignalSource, ScoredSignal

logger = logging.getLogger(__name__)

# In-memory signal store (in production: Supabase)
_signals: list[ScoredSignal] = []
MAX_SIGNALS = 500  # keep last 500 signals in memory


async def handle_telegram_message(
    text: str,
    chat_id: str,
    forward_from: str | None = None,
) -> ScoredSignal | None:
    """
    Process an incoming Telegram message.
    Returns a ScoredSignal if we could parse and score it, None otherwise.
    """
    # Determine source
    source_id = forward_from or f"direct-{chat_id}"
    source_name = forward_from or "Direct Message"

    # Parse signal from text
    signal = parse_signal(text, source_id, source_name)
    if signal is None:
        logger.debug(f"Could not parse signal from: {text[:100]}")
        return None

    # Score the signal
    score = await score_signal(signal)

    scored = ScoredSignal(signal=signal, score=score)

    # Store in memory
    _signals.append(scored)
    if len(_signals) > MAX_SIGNALS:
        _signals.pop(0)

    # Persist to Supabase
    from app.services.database import db_save_signal
    db_save_signal(
        user_id=None,
        signal=signal.model_dump(),
        score=score.model_dump() if score else None,
    )

    logger.info(
        f"Signal scored: {signal.symbol} {signal.direction.value} "
        f"score={score.score}/100 risk={score.risk_level.value}"
    )

    return scored


def get_recent_signals(limit: int = 20) -> list[ScoredSignal]:
    """Get the most recent scored signals."""
    return list(reversed(_signals[-limit:]))


def get_top_signals(limit: int = 5) -> list[ScoredSignal]:
    """Get the highest-scored signals from recent ones."""
    recent = _signals[-100:]  # look at last 100
    scored = [s for s in recent if s.score is not None]
    scored.sort(key=lambda s: s.score.score if s.score else 0, reverse=True)
    return scored[:limit]


def format_signal_response(scored: ScoredSignal) -> str:
    """Format a scored signal for Telegram reply."""
    s = scored.signal
    sc = scored.score

    emoji = "🟢" if sc and sc.score >= 70 else "🟡" if sc and sc.score >= 40 else "🔴"
    risk_emoji = {"low": "✅", "med": "⚠️", "high": "🚨"}.get(
        sc.risk_level.value if sc else "high", "❓"
    )

    lines = [
        f"{emoji} *Signal Score: {sc.score}/100*" if sc else "❓ Could not score",
        f"",
        f"📊 {s.symbol} — {s.direction.value.upper()}",
    ]

    if s.entry_price:
        lines.append(f"Entry: ${s.entry_price:,.2f}")
    if s.stop_loss:
        lines.append(f"SL: ${s.stop_loss:,.2f}")
    if s.take_profit:
        lines.append(f"TP: ${s.take_profit:,.2f}")

    if s.entry_price and s.stop_loss and s.take_profit:
        risk = abs(s.entry_price - s.stop_loss)
        reward = abs(s.take_profit - s.entry_price)
        rr = reward / risk if risk > 0 else 0
        lines.append(f"R:R = 1:{rr:.1f}")

    if sc:
        lines.extend([
            f"",
            f"{risk_emoji} Risk: {sc.risk_level.value.upper()}",
            f"💡 {sc.rationale}",
        ])

    lines.append(f"\n_Source: {s.source_name}_")
    return "\n".join(lines)
