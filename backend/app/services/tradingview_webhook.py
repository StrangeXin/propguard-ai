"""
TradingView Webhook receiver — accepts alerts from TradingView
and converts them into signals for scoring.

TradingView sends POST requests with a JSON or plain text body
when an alert triggers. Users configure the webhook URL in their
TradingView alert settings.

Webhook URL: POST /api/webhook/tradingview?source_name=MyAlert
"""

import logging
import json
import re
from datetime import datetime

from app.services.signal_parser import parse_signal
from app.services.ai_scorer import score_signal
from app.services.telegram_bot import _signals
from app.models.signal import Signal, SignalDirection, ScoredSignal

logger = logging.getLogger(__name__)


def parse_tradingview_payload(body: str | dict) -> dict:
    """
    Parse TradingView webhook payload into a normalized dict.

    TradingView supports multiple formats:
    1. JSON: {"ticker": "BTCUSD", "action": "buy", "price": 65000, ...}
    2. Plain text: "BUY BTCUSD @ 65000 SL 63000 TP 70000"
    3. Pine Script alert: "{{ticker}} {{strategy.order.action}} @ {{close}}"
    """
    if isinstance(body, dict):
        return body

    # Try JSON parse first
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        pass

    # Return as raw text
    return {"raw_text": str(body)}


def tradingview_to_signal(payload: dict, source_name: str) -> Signal | None:
    """Convert a TradingView webhook payload to a Signal."""
    source_id = f"tradingview-{source_name}"

    # If it's a structured JSON payload (common TradingView format)
    if "ticker" in payload or "symbol" in payload:
        symbol = (payload.get("ticker") or payload.get("symbol", "")).upper()
        action = (payload.get("action") or payload.get("order", {}).get("action", "")).lower()
        price = payload.get("price") or payload.get("close")
        sl = payload.get("sl") or payload.get("stop_loss") or payload.get("stoploss")
        tp = payload.get("tp") or payload.get("take_profit") or payload.get("takeprofit")

        if not symbol:
            return None

        direction = None
        if action in ("buy", "long"):
            direction = SignalDirection.LONG
        elif action in ("sell", "short"):
            direction = SignalDirection.SHORT
        else:
            return None

        return Signal(
            id=f"tv-{datetime.now().strftime('%H%M%S')}",
            source_id=source_id,
            source_name=f"TradingView: {source_name}",
            symbol=symbol,
            direction=direction,
            entry_price=float(price) if price else None,
            stop_loss=float(sl) if sl else None,
            take_profit=float(tp) if tp else None,
            raw_text=json.dumps(payload),
            received_at=datetime.now(),
        )

    # Fall back to text parsing
    raw_text = payload.get("raw_text", payload.get("message", ""))
    if raw_text:
        return parse_signal(raw_text, source_id, f"TradingView: {source_name}")

    return None


async def handle_tradingview_webhook(
    body: str | dict,
    source_name: str = "Default",
) -> ScoredSignal | None:
    """Process a TradingView webhook and return scored signal."""
    payload = parse_tradingview_payload(body)
    signal = tradingview_to_signal(payload, source_name)

    if signal is None:
        logger.debug(f"Could not parse TradingView webhook: {str(body)[:200]}")
        return None

    score = await score_signal(signal)
    scored = ScoredSignal(signal=signal, score=score)

    _signals.append(scored)
    logger.info(
        f"TradingView signal: {signal.symbol} {signal.direction.value} "
        f"score={score.score}/100 source={source_name}"
    )

    return scored
