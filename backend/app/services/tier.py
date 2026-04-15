"""
Free/Pro tier enforcement — controls feature access based on subscription level.

Design doc pricing:
  Free: 1 prop firm account + 3 signal sources (unscored)
  Pro ($29/mo): 3 accounts + unlimited signals + AI scoring + briefing
  Premium ($49/mo): unlimited accounts + position calculator + history
"""

from enum import Enum
from dataclasses import dataclass


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"


@dataclass
class TierLimits:
    max_accounts: int         # prop firm accounts monitored
    max_signal_sources: int   # signal sources connected
    ai_scoring: bool          # AI signal scoring enabled
    ai_briefing: bool         # pre-market AI briefing
    position_calculator: bool # position calculator
    history_access: bool      # historical analysis
    alert_channels: list[str] # available alert channels


TIER_CONFIG: dict[Tier, TierLimits] = {
    Tier.FREE: TierLimits(
        max_accounts=1,
        max_signal_sources=3,
        ai_scoring=False,
        ai_briefing=False,
        position_calculator=False,
        history_access=False,
        alert_channels=["web"],
    ),
    Tier.PRO: TierLimits(
        max_accounts=3,
        max_signal_sources=999,  # "unlimited"
        ai_scoring=True,
        ai_briefing=True,
        position_calculator=False,
        history_access=False,
        alert_channels=["web", "telegram", "email"],
    ),
    Tier.PREMIUM: TierLimits(
        max_accounts=999,  # "unlimited"
        max_signal_sources=999,
        ai_scoring=True,
        ai_briefing=True,
        position_calculator=True,
        history_access=True,
        alert_channels=["web", "telegram", "email", "discord"],
    ),
}


# In-memory user tier store (in production: Supabase)
_user_tiers: dict[str, Tier] = {}


def get_user_tier(user_id: str) -> Tier:
    return _user_tiers.get(user_id, Tier.FREE)


def set_user_tier(user_id: str, tier: Tier):
    _user_tiers[user_id] = tier


def get_tier_limits(tier: Tier) -> TierLimits:
    return TIER_CONFIG[tier]


def check_feature_access(user_id: str, feature: str) -> dict:
    """
    Check if a user can access a feature.
    Returns {allowed: bool, reason: str, upgrade_to: str | None}
    """
    tier = get_user_tier(user_id)
    limits = get_tier_limits(tier)

    checks = {
        "ai_scoring": (limits.ai_scoring, "AI signal scoring", Tier.PRO),
        "ai_briefing": (limits.ai_briefing, "Pre-market AI briefing", Tier.PRO),
        "position_calculator": (limits.position_calculator, "Position calculator", Tier.PREMIUM),
        "history": (limits.history_access, "Historical analysis", Tier.PREMIUM),
    }

    if feature in checks:
        allowed, name, required_tier = checks[feature]
        if not allowed:
            return {
                "allowed": False,
                "reason": f"{name} requires {required_tier.value.title()} plan",
                "upgrade_to": required_tier.value,
                "current_tier": tier.value,
            }

    return {"allowed": True, "current_tier": tier.value}


def check_account_limit(user_id: str, current_count: int) -> dict:
    """Check if user can add another monitored account."""
    tier = get_user_tier(user_id)
    limits = get_tier_limits(tier)

    if current_count >= limits.max_accounts:
        upgrade = Tier.PRO if tier == Tier.FREE else Tier.PREMIUM
        return {
            "allowed": False,
            "reason": f"Free plan allows {limits.max_accounts} account(s). Upgrade to add more.",
            "upgrade_to": upgrade.value,
            "current_count": current_count,
            "max_allowed": limits.max_accounts,
        }

    return {"allowed": True, "current_count": current_count, "max_allowed": limits.max_accounts}


def check_signal_source_limit(user_id: str, current_count: int) -> dict:
    """Check if user can add another signal source."""
    tier = get_user_tier(user_id)
    limits = get_tier_limits(tier)

    if current_count >= limits.max_signal_sources:
        return {
            "allowed": False,
            "reason": f"Free plan allows {limits.max_signal_sources} signal sources. Upgrade to Pro for unlimited.",
            "upgrade_to": Tier.PRO.value,
            "current_count": current_count,
            "max_allowed": limits.max_signal_sources,
        }

    return {"allowed": True, "current_count": current_count, "max_allowed": limits.max_signal_sources}
