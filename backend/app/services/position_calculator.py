"""
Position Size Calculator — calculates recommended position size
based on account state and risk parameters.

Design doc reference:
- 1% risk per trade, hard cap 3% of account equity
- Kelly fraction as secondary reference (only shown with 30+ days of data)
- Priority: hard cap (3%) > 1% base rule
"""

from dataclasses import dataclass
import math


@dataclass
class PositionCalcResult:
    recommended_size: float  # in lots or contracts
    stop_loss_price: float
    risk_amount: float  # $ risked on this trade
    risk_pct: float  # % of equity risked
    max_allowed_size: float  # hard cap size
    kelly_size: float | None  # kelly-optimal size (None if insufficient data)
    kelly_note: str | None  # explanation if kelly is shown
    warnings: list[str]


def calculate_position(
    equity: float,
    entry_price: float,
    stop_loss: float,
    contract_size: float = 100000.0,  # forex standard lot = 100K units
    source_win_rate: float | None = None,
    source_avg_rr: float | None = None,
    source_sample_size: int = 0,
    daily_loss_remaining: float | None = None,
    max_dd_remaining: float | None = None,
) -> PositionCalcResult:
    """
    Calculate recommended position size.

    Args:
        equity: Current account equity
        entry_price: Planned entry price
        stop_loss: Planned stop loss price
        contract_size: Value of 1 lot in base units (forex=100000, crypto=1)
        source_win_rate: Historical win rate of the signal source (0-1)
        source_avg_rr: Average risk/reward ratio of the signal source
        source_sample_size: Number of historical trades for this source
        daily_loss_remaining: Remaining daily loss budget in $
        max_dd_remaining: Remaining max drawdown budget in $
    """
    warnings: list[str] = []

    # Calculate risk per lot
    price_diff = abs(entry_price - stop_loss)
    if price_diff == 0:
        return PositionCalcResult(
            recommended_size=0, stop_loss_price=stop_loss,
            risk_amount=0, risk_pct=0, max_allowed_size=0,
            kelly_size=None, kelly_note=None,
            warnings=["Stop loss cannot equal entry price"],
        )

    risk_per_lot = price_diff * contract_size

    # 1% base risk rule
    risk_budget_1pct = equity * 0.01
    size_1pct = risk_budget_1pct / risk_per_lot if risk_per_lot > 0 else 0

    # 3% hard cap
    risk_budget_3pct = equity * 0.03
    max_size = risk_budget_3pct / risk_per_lot if risk_per_lot > 0 else 0

    # Constrain by remaining budgets
    if daily_loss_remaining is not None and daily_loss_remaining > 0:
        daily_max_size = (daily_loss_remaining * 0.5) / risk_per_lot  # use at most 50% of remaining daily budget
        if daily_max_size < size_1pct:
            size_1pct = daily_max_size
            warnings.append(f"Size reduced: daily loss budget tight (${daily_loss_remaining:.0f} remaining)")

    if max_dd_remaining is not None and max_dd_remaining > 0:
        dd_max_size = (max_dd_remaining * 0.2) / risk_per_lot  # use at most 20% of remaining DD budget
        if dd_max_size < size_1pct:
            size_1pct = dd_max_size
            warnings.append(f"Size reduced: drawdown budget tight (${max_dd_remaining:.0f} remaining)")

    # Apply hard cap
    recommended = min(size_1pct, max_size)
    recommended = max(recommended, 0)  # floor at 0

    # Kelly criterion (reference only, requires 30+ trades)
    kelly_size = None
    kelly_note = None
    if source_win_rate is not None and source_avg_rr is not None and source_sample_size >= 30:
        # Kelly formula: f = W - (1-W)/R
        # W = win rate, R = average win/loss ratio
        kelly_f = source_win_rate - (1 - source_win_rate) / source_avg_rr if source_avg_rr > 0 else 0
        if kelly_f > 0:
            kelly_risk = equity * kelly_f
            kelly_size = kelly_risk / risk_per_lot if risk_per_lot > 0 else 0
            # Cap kelly at hard max
            kelly_size = min(kelly_size, max_size)
            kelly_note = (
                f"Kelly fraction: {kelly_f:.1%} "
                f"(based on {source_sample_size} trades, "
                f"{source_win_rate:.0%} win rate, {source_avg_rr:.1f} avg R:R). "
                f"Shown as reference only."
            )
        else:
            kelly_note = f"Kelly fraction is negative ({kelly_f:.1%}) — source has negative edge. Avoid this signal."
            warnings.append("Kelly suggests negative edge on this signal source")
    elif source_sample_size > 0 and source_sample_size < 30:
        kelly_note = f"Kelly requires 30+ trades (source has {source_sample_size}). Using 1% rule only."

    risk_amount = recommended * risk_per_lot
    risk_pct = (risk_amount / equity * 100) if equity > 0 else 0

    # Round to reasonable precision
    recommended = round(recommended, 2)
    if max_size > 0:
        max_size = round(max_size, 2)

    return PositionCalcResult(
        recommended_size=recommended,
        stop_loss_price=stop_loss,
        risk_amount=round(risk_amount, 2),
        risk_pct=round(risk_pct, 2),
        max_allowed_size=round(max_size, 2),
        kelly_size=round(kelly_size, 2) if kelly_size is not None else None,
        kelly_note=kelly_note,
        warnings=warnings,
    )
