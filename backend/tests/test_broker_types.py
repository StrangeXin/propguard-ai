"""Tests for broker value objects."""

import pytest
from datetime import datetime, timezone

from app.services.broker_types import (
    AccountInfo, PositionDTO, OrderDTO, OrderResult, ClosedTrade,
)


class TestBrokerTypes:
    def test_account_info_computed_fields(self):
        info = AccountInfo(
            balance=100000.0,
            equity=99500.0,
            margin=500.0,
            free_margin=99000.0,
            currency="USD",
        )
        assert info.balance == 100000.0
        assert info.equity == 99500.0

    def test_position_dto(self):
        pos = PositionDTO(
            id="p1", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.0850, current_price=1.0860,
            unrealized_pnl=10.0, stop_loss=None, take_profit=None,
            opened_at=datetime.now(timezone.utc),
        )
        assert pos.side == "long"
        assert pos.unrealized_pnl == 10.0

    def test_position_dto_side_validated(self):
        with pytest.raises(ValueError, match="side must be 'long' or 'short'"):
            PositionDTO(
                id="p1", symbol="EURUSD", side="buy", size=0.1,
                entry_price=1.0, current_price=1.0,
                unrealized_pnl=0, stop_loss=None, take_profit=None,
                opened_at=datetime.now(timezone.utc),
            )

    def test_order_result_success(self):
        r = OrderResult(success=True, order_id="o1", message=None)
        assert r.success
        assert r.order_id == "o1"

    def test_order_result_failure(self):
        r = OrderResult(success=False, order_id=None, message="insufficient margin")
        assert not r.success
        assert "insufficient" in r.message

    def test_closed_trade(self):
        now = datetime.now(timezone.utc)
        t = ClosedTrade(
            id="t1", symbol="EURUSD", side="long", size=0.1,
            entry_price=1.08, exit_price=1.09, pnl=100.0,
            opened_at=now, closed_at=now,
        )
        assert t.pnl == 100.0
