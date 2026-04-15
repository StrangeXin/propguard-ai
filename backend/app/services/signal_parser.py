"""
Signal parser — extracts structured trading signal data from raw text messages.
Handles common formats from Telegram signal groups.
"""

import re
import uuid
from datetime import datetime
from app.models.signal import Signal, SignalDirection


# Common patterns in trading signal messages
SYMBOL_PATTERN = re.compile(
    r'\b(BTC|ETH|SOL|XRP|DOGE|ADA|DOT|AVAX|LINK|MATIC|'
    r'EUR|GBP|USD|JPY|CHF|AUD|NZD|CAD|'
    r'EURUSD|GBPUSD|USDJPY|AUDUSD|USDCAD|NZDUSD|USDCHF|GBPJPY|EURJPY|'
    r'BTCUSD|ETHUSD|SOLUSD|XRPUSD|'
    r'XAUUSD|GOLD|NAS100|US30|SPX500|US500)\b',
    re.IGNORECASE,
)

DIRECTION_PATTERNS = {
    SignalDirection.LONG: re.compile(
        r'\b(buy|long|bullish|calls?|上涨|做多|买入)\b', re.IGNORECASE
    ),
    SignalDirection.SHORT: re.compile(
        r'\b(sell|short|bearish|puts?|下跌|做空|卖出)\b', re.IGNORECASE
    ),
}

PRICE_PATTERN = re.compile(
    r'(?:entry|price|at|@|入场)\s*[:：]?\s*\$?(\d+[.,]?\d*)', re.IGNORECASE
)

SL_PATTERN = re.compile(
    r'(?:sl|stop\s*loss|止损)\s*[:：]?\s*\$?(\d+[.,]?\d*)', re.IGNORECASE
)

TP_PATTERN = re.compile(
    r'(?:tp|take\s*profit|目标|止盈)\s*[:：]?\s*\$?(\d+[.,]?\d*)', re.IGNORECASE
)


def _extract_price(pattern: re.Pattern, text: str) -> float | None:
    match = pattern.search(text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def parse_signal(raw_text: str, source_id: str, source_name: str) -> Signal | None:
    """
    Parse a raw text message into a structured Signal.
    Returns None if we can't extract enough information.
    """
    # Extract symbol
    symbol_match = SYMBOL_PATTERN.search(raw_text)
    if not symbol_match:
        return None
    symbol = symbol_match.group(0).upper()

    # Normalize symbols
    alias_map = {"GOLD": "XAUUSD", "NAS100": "NAS100", "US30": "US30", "SPX500": "SPX500", "US500": "SPX500"}
    if symbol in alias_map:
        symbol = alias_map[symbol]
    elif len(symbol) == 3:
        usd_pairs = {"EUR": "EURUSD", "GBP": "GBPUSD", "AUD": "AUDUSD",
                     "NZD": "NZDUSD", "JPY": "USDJPY", "CHF": "USDCHF",
                     "CAD": "USDCAD"}
        symbol = usd_pairs.get(symbol, f"{symbol}USD")

    # Extract direction
    direction = None
    for d, pattern in DIRECTION_PATTERNS.items():
        if pattern.search(raw_text):
            direction = d
            break

    if direction is None:
        return None

    # Extract prices
    entry = _extract_price(PRICE_PATTERN, raw_text)
    sl = _extract_price(SL_PATTERN, raw_text)
    tp = _extract_price(TP_PATTERN, raw_text)

    return Signal(
        id=str(uuid.uuid4())[:8],
        source_id=source_id,
        source_name=source_name,
        symbol=symbol,
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        raw_text=raw_text,
        received_at=datetime.now(),
    )
