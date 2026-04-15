from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "med"
    HIGH = "high"


class Signal(BaseModel):
    """A trading signal received from an external source."""
    id: str
    source_id: str
    source_name: str
    symbol: str
    direction: SignalDirection
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    raw_text: str  # original message text
    received_at: datetime = datetime.now()


class SignalScore(BaseModel):
    """AI-generated score for a trading signal."""
    signal_id: str
    score: int  # 0-100
    rationale: str
    risk_level: RiskLevel
    scored_at: datetime = datetime.now()


class ScoredSignal(BaseModel):
    """Signal combined with its AI score."""
    signal: Signal
    score: SignalScore | None = None


class SignalSource(BaseModel):
    """Metadata about a signal source (Telegram bot, TradingView webhook, etc.)."""
    source_id: str
    source_name: str
    source_type: str  # "telegram" | "tradingview" | "manual"
    win_rate: float | None = None  # historical, 0-1
    avg_rr: float | None = None  # average risk/reward ratio
    sample_size: int = 0
    last_updated: datetime | None = None
