"""Tests for signal parsing and scoring."""

import pytest
from app.services.signal_parser import parse_signal
from app.services.ai_scorer import _rule_based_score, register_source
from app.models.signal import SignalDirection, SignalSource


class TestSignalParser:
    def test_parse_basic_buy(self):
        text = "BUY EURUSD @ 1.0850 SL: 1.0800 TP: 1.0950"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None
        assert signal.symbol == "EURUSD"
        assert signal.direction == SignalDirection.LONG
        assert signal.entry_price == 1.085
        assert signal.stop_loss == 1.08
        assert signal.take_profit == 1.095

    def test_parse_sell_signal(self):
        text = "SHORT BTCUSD entry: 65000 sl: 66000 tp: 62000"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None
        assert signal.symbol == "BTCUSD"
        assert signal.direction == SignalDirection.SHORT
        assert signal.entry_price == 65000
        assert signal.stop_loss == 66000
        assert signal.take_profit == 62000

    def test_parse_chinese_signal(self):
        text = "做多 ETH 入场: 3500 止损: 3400 止盈: 3800"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None
        assert signal.symbol == "ETHUSD"
        assert signal.direction == SignalDirection.LONG

    def test_parse_no_prices(self):
        text = "BUY GOLD now!"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None
        assert signal.symbol == "XAUUSD"
        assert signal.entry_price is None

    def test_parse_no_direction(self):
        """Signal without clear direction should return None."""
        text = "EURUSD looking interesting at 1.0850"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is None

    def test_parse_no_symbol(self):
        """Message without a recognizable symbol should return None."""
        text = "Buy now! Great opportunity!"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is None

    def test_parse_single_currency(self):
        """Single currency code should normalize to USD pair."""
        text = "BUY GBP at 1.2700"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None
        assert signal.symbol == "GBPUSD"


class TestRuleBasedScoring:
    def test_complete_signal_good_rr(self):
        """Complete signal with good risk/reward should score high."""
        text = "BUY EURUSD @ 1.0850 SL: 1.0800 TP: 1.1000"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None
        score = _rule_based_score(signal, None)
        assert score.score >= 50  # completeness(25) + RR(20-25) + source(10) + fit(15)

    def test_incomplete_signal_scores_lower(self):
        """Signal without SL/TP should score lower."""
        text = "BUY EURUSD now"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None
        score = _rule_based_score(signal, None)
        assert score.score < 50

    def test_known_source_boost(self):
        """Signal from a source with good stats should score higher."""
        text = "BUY EURUSD @ 1.0850 SL: 1.0800 TP: 1.1000"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None

        # Score without source stats
        score_no_source = _rule_based_score(signal, None)

        # Score with good source stats
        source = SignalSource(
            source_id="src-1",
            source_name="TestGroup",
            source_type="telegram",
            win_rate=0.75,
            avg_rr=2.5,
            sample_size=200,
        )
        score_with_source = _rule_based_score(signal, source)

        assert score_with_source.score > score_no_source.score

    def test_risk_levels(self):
        """Verify risk level assignment based on score."""
        text = "BUY EURUSD @ 1.0850 SL: 1.0800 TP: 1.1000"
        signal = parse_signal(text, "src-1", "TestGroup")
        assert signal is not None

        # With a great source, should be low risk
        source = SignalSource(
            source_id="src-1",
            source_name="TestGroup",
            source_type="telegram",
            win_rate=0.8,
            avg_rr=3.0,
            sample_size=500,
        )
        score = _rule_based_score(signal, source)
        assert score.score >= 70
        assert score.risk_level.value == "low"
