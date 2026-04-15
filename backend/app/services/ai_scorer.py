"""
AI Signal Scorer — uses Claude API to evaluate trading signals.
Falls back to rule-based scoring when API is unavailable.

Design doc reference: AI 评分方法论
- Input: signal source win rate, RR ratio, market volatility, account remaining drawdown
- Output: JSON {score: 0-100, rationale: "one sentence", risk_level: "low|med|high"}
- Fallback: pure rule scoring (win_rate * RR * volatility_coefficient)
"""

import json
import logging
from datetime import datetime

from app.models.signal import Signal, SignalScore, RiskLevel, SignalSource
from app.config import get_settings

logger = logging.getLogger(__name__)

# In-memory signal source stats (in production, this comes from Supabase)
_source_stats: dict[str, SignalSource] = {}

SCORING_PROMPT = """You are a trading signal quality evaluator. Score this signal 0-100 based on the data provided.

Signal:
- Symbol: {symbol}
- Direction: {direction}
- Entry: {entry}
- Stop Loss: {sl}
- Take Profit: {tp}
- Raw message: {raw_text}

Source stats:
- Source: {source_name}
- Historical win rate: {win_rate}
- Average risk/reward: {avg_rr}
- Sample size: {sample_size}

Account context:
- Remaining daily loss budget: ${daily_remaining}
- Remaining drawdown budget: ${dd_remaining}

Scoring criteria:
1. Signal quality (clear entry, SL, TP defined? 0-25 points)
2. Risk/reward ratio (>2:1 = good, >3:1 = excellent. 0-25 points)
3. Source reliability (win rate * sample size confidence. 0-25 points)
4. Account fit (does this signal's risk fit within remaining budgets? 0-25 points)

Respond ONLY with valid JSON, no other text:
{{"score": <0-100>, "rationale": "<one sentence>", "risk_level": "<low|med|high>"}}"""


def register_source(source: SignalSource):
    """Register or update a signal source's stats."""
    _source_stats[source.source_id] = source


def get_source_stats(source_id: str) -> SignalSource | None:
    return _source_stats.get(source_id)


def _rule_based_score(
    signal: Signal,
    source: SignalSource | None,
    daily_remaining: float = 5000,
    dd_remaining: float = 10000,
) -> SignalScore:
    """Fallback scoring when Claude API is unavailable."""
    score = 0

    # Signal completeness (0-25)
    completeness = 0
    if signal.entry_price is not None:
        completeness += 8
    if signal.stop_loss is not None:
        completeness += 8
    if signal.take_profit is not None:
        completeness += 9
    score += completeness

    # Risk/reward ratio (0-25)
    rr_score = 0
    if signal.entry_price and signal.stop_loss and signal.take_profit:
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        if risk > 0:
            rr = reward / risk
            if rr >= 3:
                rr_score = 25
            elif rr >= 2:
                rr_score = 20
            elif rr >= 1.5:
                rr_score = 15
            elif rr >= 1:
                rr_score = 10
            else:
                rr_score = 5
    score += rr_score

    # Source reliability (0-25)
    source_score = 0
    if source and source.win_rate is not None and source.sample_size > 0:
        # Confidence-weighted win rate
        confidence = min(source.sample_size / 100, 1.0)  # full confidence at 100 signals
        source_score = int(source.win_rate * confidence * 25)
    else:
        source_score = 10  # neutral for unknown sources
    score += source_score

    # Account fit (0-25)
    fit_score = 15  # default moderate
    if signal.stop_loss and signal.entry_price:
        risk_amount = abs(signal.entry_price - signal.stop_loss)
        if risk_amount < daily_remaining * 0.02:  # risk < 2% of daily budget
            fit_score = 25
        elif risk_amount < daily_remaining * 0.05:
            fit_score = 20
        elif risk_amount < daily_remaining * 0.1:
            fit_score = 10
        else:
            fit_score = 5
    score += fit_score

    # Determine risk level
    if score >= 70:
        risk_level = RiskLevel.LOW
    elif score >= 40:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.HIGH

    rationale = f"Rule-based score: completeness={completeness}/25, RR={rr_score}/25, source={source_score}/25, fit={fit_score}/25"

    return SignalScore(
        signal_id=signal.id,
        score=min(score, 100),
        rationale=rationale,
        risk_level=risk_level,
        scored_at=datetime.now(),
    )


async def score_signal(
    signal: Signal,
    daily_remaining: float = 5000,
    dd_remaining: float = 10000,
) -> SignalScore:
    """
    Score a trading signal using Claude API, with rule-based fallback.
    """
    settings = get_settings()
    source = get_source_stats(signal.source_id)

    # Try Claude API first
    if settings.anthropic_api_key:
        try:
            return await _ai_score(signal, source, daily_remaining, dd_remaining)
        except Exception as e:
            logger.warning(f"AI scoring failed, falling back to rules: {e}")

    # Fallback to rule-based scoring
    return _rule_based_score(signal, source, daily_remaining, dd_remaining)


async def _ai_score(
    signal: Signal,
    source: SignalSource | None,
    daily_remaining: float,
    dd_remaining: float,
) -> SignalScore:
    """Score using Claude API with structured output."""
    import anthropic

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = SCORING_PROMPT.format(
        symbol=signal.symbol,
        direction=signal.direction.value,
        entry=signal.entry_price or "not specified",
        sl=signal.stop_loss or "not specified",
        tp=signal.take_profit or "not specified",
        raw_text=signal.raw_text[:500],  # truncate long messages
        source_name=signal.source_name,
        win_rate=f"{source.win_rate:.1%}" if source and source.win_rate else "unknown",
        avg_rr=f"{source.avg_rr:.1f}" if source and source.avg_rr else "unknown",
        sample_size=source.sample_size if source else 0,
        daily_remaining=f"{daily_remaining:.2f}",
        dd_remaining=f"{dd_remaining:.2f}",
    )

    response = await client.messages.create(
        model=settings.ai_model,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = response.content[0].text.strip()
    # Handle markdown-wrapped JSON (```json ... ```)
    if result_text.startswith("```"):
        result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    result = json.loads(result_text)

    return SignalScore(
        signal_id=signal.id,
        score=max(0, min(100, int(result["score"]))),
        rationale=result["rationale"],
        risk_level=RiskLevel(result["risk_level"]),
        scored_at=datetime.now(),
    )
