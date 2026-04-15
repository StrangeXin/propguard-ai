"""Tests for position size calculator."""

from app.services.position_calculator import calculate_position


class TestPositionCalculator:
    def test_basic_1pct_risk(self):
        """1% of $100K equity = $1000 risk budget."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.0950,
            contract_size=100000,
        )
        # Risk = 50 pips * $10/pip/lot = $500/lot
        # $1000 / $500 = 2.0 lots
        assert result.recommended_size == 2.0
        assert result.risk_pct <= 1.0

    def test_hard_cap_3pct(self):
        """Position should never exceed 3% risk."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.0990,  # very tight stop = 10 pips
            contract_size=100000,
        )
        # 1% rule: $1000 / ($10 * 10) = 10 lots
        # 3% cap: $3000 / ($10 * 10) = 30 lots
        # 10 < 30, so 1% rule wins
        assert result.recommended_size == 10.0
        assert result.risk_pct <= 1.0

    def test_daily_loss_constraint(self):
        """Position reduced when daily loss budget is tight."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.0950,
            contract_size=100000,
            daily_loss_remaining=500,  # only $500 left
        )
        # Normal: 2.0 lots ($1000 risk)
        # But daily budget: $500 * 50% = $250 / $500 = 0.5 lots
        assert result.recommended_size < 2.0
        assert len(result.warnings) > 0

    def test_drawdown_constraint(self):
        """Position reduced when drawdown budget is tight."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.0950,
            contract_size=100000,
            max_dd_remaining=1000,  # only $1000 of DD left
        )
        # DD budget: $1000 * 20% = $200 / $500 = 0.4 lots
        assert result.recommended_size < 2.0
        assert len(result.warnings) > 0

    def test_kelly_with_enough_data(self):
        """Kelly shown when source has 30+ trades."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.0950,
            contract_size=100000,
            source_win_rate=0.6,
            source_avg_rr=2.0,
            source_sample_size=100,
        )
        assert result.kelly_size is not None
        assert result.kelly_note is not None
        assert "reference" in result.kelly_note.lower()

    def test_kelly_hidden_insufficient_data(self):
        """Kelly not shown when source has < 30 trades."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.0950,
            contract_size=100000,
            source_win_rate=0.6,
            source_avg_rr=2.0,
            source_sample_size=15,
        )
        assert result.kelly_size is None
        assert "30" in (result.kelly_note or "")

    def test_negative_kelly(self):
        """Bad source should warn about negative edge."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.0950,
            contract_size=100000,
            source_win_rate=0.3,  # 30% win rate
            source_avg_rr=1.0,  # 1:1 RR = negative edge
            source_sample_size=50,
        )
        assert result.kelly_size is None
        assert any("negative" in w.lower() for w in result.warnings)

    def test_zero_risk(self):
        """SL equals entry should return 0 with warning."""
        result = calculate_position(
            equity=100000,
            entry_price=1.1000,
            stop_loss=1.1000,
        )
        assert result.recommended_size == 0
        assert len(result.warnings) > 0
