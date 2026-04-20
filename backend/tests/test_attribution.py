"""Tests for attribution service — label freezing and DB write helpers."""

from unittest.mock import patch, MagicMock

import pytest

from app.services.attribution import (
    freeze_user_label,
    record_attribution,
    fetch_labels_by_orders,
    fetch_labels_by_positions,
)


class TestFreezeUserLabel:
    def test_uses_name_when_present(self):
        assert freeze_user_label({"name": "Mason", "email": "m@x.com"}) == "Mason"

    def test_trims_name_whitespace(self):
        assert freeze_user_label({"name": "  Alice  ", "email": "a@x.com"}) == "Alice"

    def test_truncates_name_at_32_chars(self):
        long = "x" * 64
        assert freeze_user_label({"name": long, "email": "a@x.com"}) == "x" * 32

    def test_falls_back_to_masked_email_when_name_empty(self):
        assert freeze_user_label({"name": "", "email": "mason@example.com"}) == "m***n@example.com"

    def test_masks_short_local_part(self):
        # local part "ab" (len 2) → keep first char + "*"
        assert freeze_user_label({"name": "", "email": "ab@x.com"}) == "a*@x.com"

    def test_masks_single_char_local(self):
        assert freeze_user_label({"name": "", "email": "a@x.com"}) == "a*@x.com"

    def test_masks_name_none(self):
        assert freeze_user_label({"name": None, "email": "xy@host.com"}) == "x*@host.com"

    def test_returns_anonymous_when_both_name_and_email_missing(self):
        assert freeze_user_label({"name": "", "email": ""}) == "anonymous"

    def test_returns_anonymous_when_keys_absent(self):
        assert freeze_user_label({}) == "anonymous"

    def test_handles_email_without_at_sign(self):
        # Defensive: malformed email shouldn't crash
        result = freeze_user_label({"name": "", "email": "noatsignhere"})
        assert result  # just check it doesn't raise
        assert "*" in result


class TestRecordAttribution:
    def test_happy_path_inserts_row(self):
        mock_db = MagicMock()
        mock_table = mock_db.table.return_value
        mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"broker_order_id": "o1"}])
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = record_attribution(
                broker_order_id="o1",
                broker_position_id="p1",
                account_id="acc1",
                user_id="u1",
                user_label="Mason",
                symbol="EURUSD",
                side="buy",
                volume=0.1,
            )
        assert result is True
        mock_db.table.assert_called_with("order_attributions")
        insert_arg = mock_table.insert.call_args[0][0]
        assert insert_arg["broker_order_id"] == "o1"
        assert insert_arg["user_label"] == "Mason"

    def test_swallows_db_exception(self):
        mock_db = MagicMock()
        mock_db.table.side_effect = RuntimeError("db down")
        with patch("app.services.attribution.get_db", return_value=mock_db):
            # MUST NOT raise — the order has already been placed at the broker.
            result = record_attribution(
                broker_order_id="o1", broker_position_id=None, account_id="acc1",
                user_id="u1", user_label="Mason", symbol="EURUSD", side="buy", volume=0.1,
            )
        assert result is False

    def test_returns_false_when_db_unavailable(self):
        with patch("app.services.attribution.get_db", return_value=None):
            result = record_attribution(
                broker_order_id="o1", broker_position_id=None, account_id="acc1",
                user_id="u1", user_label="Mason", symbol="EURUSD", side="buy", volume=0.1,
            )
        assert result is False


class TestFetchLabels:
    def test_fetch_by_orders_returns_map(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"broker_order_id": "o1", "user_label": "Mason"},
                {"broker_order_id": "o2", "user_label": "Alice"},
            ]
        )
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = fetch_labels_by_orders(["o1", "o2", "o3"])
        assert result == {"o1": "Mason", "o2": "Alice"}

    def test_fetch_by_orders_empty_input(self):
        with patch("app.services.attribution.get_db") as mock_get:
            result = fetch_labels_by_orders([])
        assert result == {}
        mock_get.assert_not_called()  # no DB round-trip for empty input

    def test_fetch_by_positions_returns_map(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"broker_position_id": "p1", "user_label": "Mason"}]
        )
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = fetch_labels_by_positions(["p1"])
        assert result == {"p1": "Mason"}

    def test_fetch_by_orders_swallows_db_error(self):
        mock_db = MagicMock()
        mock_db.table.side_effect = RuntimeError("db down")
        with patch("app.services.attribution.get_db", return_value=mock_db):
            result = fetch_labels_by_orders(["o1"])
        assert result == {}  # fail open: labels missing beats 500 on history read
