"""Tests for TradingView webhook parsing."""

from app.services.tradingview_webhook import tradingview_to_signal, parse_tradingview_payload
from app.models.signal import SignalDirection


class TestTradingViewParser:
    def test_json_payload(self):
        payload = {
            "ticker": "BTCUSD",
            "action": "buy",
            "price": 65000,
            "sl": 63000,
            "tp": 70000,
        }
        signal = tradingview_to_signal(payload, "MyAlert")
        assert signal is not None
        assert signal.symbol == "BTCUSD"
        assert signal.direction == SignalDirection.LONG
        assert signal.entry_price == 65000

    def test_sell_action(self):
        payload = {"ticker": "EURUSD", "action": "sell", "price": 1.085}
        signal = tradingview_to_signal(payload, "FXAlert")
        assert signal is not None
        assert signal.direction == SignalDirection.SHORT

    def test_plain_text_fallback(self):
        payload = parse_tradingview_payload("BUY EURUSD @ 1.085 SL: 1.08 TP: 1.095")
        signal = tradingview_to_signal(payload, "TextAlert")
        assert signal is not None
        assert signal.symbol == "EURUSD"

    def test_pine_script_format(self):
        payload = {"symbol": "XAUUSD", "action": "long", "close": 2350.5}
        signal = tradingview_to_signal(payload, "GoldAlert")
        assert signal is not None
        assert signal.symbol == "XAUUSD"
        assert signal.entry_price == 2350.5

    def test_empty_payload(self):
        signal = tradingview_to_signal({}, "Empty")
        assert signal is None

    def test_no_action(self):
        payload = {"ticker": "BTCUSD", "price": 65000}
        signal = tradingview_to_signal(payload, "NoAction")
        assert signal is None
