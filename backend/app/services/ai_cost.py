"""
AI cost ledger — per-owner Claude token + USD usage accounting.

Written to after every AIClient call. Enables per-user cost tracking for
pricing decisions and detecting abusive usage of shared API keys.
"""

import logging
from datetime import datetime, timezone

from app.models.owner import Owner
from app.services.database import get_db

logger = logging.getLogger(__name__)

# Per-1M-tokens USD pricing (Anthropic public prices, 2026-04).
# Tuple is (input_per_1m, output_per_1m).
COST_PER_1M: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "claude-haiku-4-5": (0.80, 4.0),
}
_DEFAULT_RATE = (3.0, 15.0)  # Sonnet-class fallback for unknown models.


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = COST_PER_1M.get(model, _DEFAULT_RATE)
    cost = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
    return round(cost, 6)


def record_tokens(owner: Owner, *, model: str,
                  input_tokens: int, output_tokens: int) -> float:
    """Write a ledger row and return the computed cost in USD."""
    cost = _cost_usd(model, input_tokens, output_tokens)
    db = get_db()
    if not db:
        return cost
    try:
        db.table("ai_cost_ledger").insert({
            "owner_id": owner.id,
            "owner_kind": owner.kind,
            "date": datetime.now(timezone.utc).date().isoformat(),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "cost_usd": cost,
        }).execute()
    except Exception as e:
        logger.error(f"record_tokens: {e}")
    return cost


def get_cost_today(owner_id: str) -> float:
    """Sum of cost_usd for owner today. Used by admin dashboards and tests."""
    db = get_db()
    if not db:
        return 0.0
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        result = db.table("ai_cost_ledger").select("cost_usd").eq("owner_id", owner_id).eq("date", today).execute()
        return round(sum(float(r["cost_usd"]) for r in (result.data or [])), 6)
    except Exception as e:
        logger.error(f"get_cost_today: {e}")
        return 0.0
