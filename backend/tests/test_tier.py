"""Tests for tier enforcement."""

from app.services.tier import (
    get_user_tier, set_user_tier, check_feature_access,
    check_account_limit, check_signal_source_limit, Tier,
)


class TestTierSystem:
    def test_default_tier_is_free(self):
        assert get_user_tier("new-user") == Tier.FREE

    def test_set_and_get_tier(self):
        set_user_tier("test-user", Tier.PRO)
        assert get_user_tier("test-user") == Tier.PRO

    def test_free_no_ai_scoring(self):
        result = check_feature_access("free-user", "ai_scoring")
        assert result["allowed"] is False
        assert result["upgrade_to"] == "pro"

    def test_pro_has_ai_scoring(self):
        set_user_tier("pro-user", Tier.PRO)
        result = check_feature_access("pro-user", "ai_scoring")
        assert result["allowed"] is True

    def test_pro_no_position_calc(self):
        set_user_tier("pro-user-2", Tier.PRO)
        result = check_feature_access("pro-user-2", "position_calculator")
        assert result["allowed"] is False
        assert result["upgrade_to"] == "premium"

    def test_premium_has_everything(self):
        set_user_tier("premium-user", Tier.PREMIUM)
        for feature in ["ai_scoring", "ai_briefing", "position_calculator", "history"]:
            result = check_feature_access("premium-user", feature)
            assert result["allowed"] is True, f"{feature} should be allowed for premium"

    def test_free_account_limit(self):
        result = check_account_limit("free-user-2", current_count=1)
        assert result["allowed"] is False

    def test_free_account_under_limit(self):
        result = check_account_limit("free-user-3", current_count=0)
        assert result["allowed"] is True

    def test_free_signal_source_limit(self):
        result = check_signal_source_limit("free-user-4", current_count=3)
        assert result["allowed"] is False

    def test_pro_signal_source_unlimited(self):
        set_user_tier("pro-signals", Tier.PRO)
        result = check_signal_source_limit("pro-signals", current_count=50)
        assert result["allowed"] is True
