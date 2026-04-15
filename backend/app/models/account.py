from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class AlertLevel(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    CRITICAL = "critical"
    DANGER = "danger"
    BREACHED = "breached"


class Position(BaseModel):
    symbol: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    opened_at: datetime


class AccountState(BaseModel):
    account_id: str
    firm_name: str
    account_size: int
    initial_balance: float
    current_balance: float
    current_equity: float
    daily_pnl: float  # today's realized + unrealized
    total_pnl: float  # since challenge start
    equity_high_watermark: float
    open_positions: list[Position] = []
    trading_days_count: int = 0
    challenge_start_date: datetime | None = None
    last_updated: datetime = datetime.now()


class RuleCheckResult(BaseModel):
    rule_type: str
    rule_description: str
    current_value: float
    limit_value: float
    remaining: float
    remaining_pct: float
    alert_level: AlertLevel
    message: str


class ComplianceReport(BaseModel):
    account_id: str
    firm_name: str
    timestamp: datetime
    overall_status: AlertLevel
    checks: list[RuleCheckResult]
    next_reset: datetime | None = None  # for daily loss reset
