"""Tests for the PropGuard rule engine."""

import pytest
from datetime import datetime
from app.models.account import AccountState, AlertLevel, Position
from app.rules.engine import evaluate_compliance, load_firm_rules, list_available_firms


def make_account(
    firm_name: str = "ftmo",
    account_size: int = 100000,
    daily_pnl: float = 0,
    total_pnl: float = 0,
    equity_offset: float = 0,
    trading_days: int = 0,
    positions: list | None = None,
) -> AccountState:
    initial = float(account_size)
    balance = initial + total_pnl
    equity = balance + equity_offset
    return AccountState(
        account_id="test-001",
        firm_name=firm_name,
        account_size=account_size,
        initial_balance=initial,
        current_balance=round(balance, 2),
        current_equity=round(equity, 2),
        daily_pnl=round(daily_pnl, 2),
        total_pnl=round(total_pnl, 2),
        equity_high_watermark=round(max(initial, equity), 2),
        open_positions=positions or [],
        trading_days_count=trading_days,
        challenge_start_date=datetime(2026, 4, 1),
    )


class TestListFirms:
    def test_lists_three_firms(self):
        firms = list_available_firms()
        names = {f["firm_name"] for f in firms}
        assert "FTMO" in names
        assert "TopStep" in names
        assert "Breakout" in names

    def test_firm_metadata(self):
        firms = list_available_firms()
        ftmo = next(f for f in firms if f["firm_name"] == "FTMO")
        assert "forex" in ftmo["markets"]
        assert ftmo["evaluation_type"] == "2-step"
        assert 100000 in ftmo["account_sizes"]


class TestLoadRules:
    def test_load_ftmo(self):
        rules = load_firm_rules("ftmo")
        assert rules["firm_name"] == "FTMO"
        assert len(rules["rules"]) > 0

    def test_load_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            load_firm_rules("nonexistent_firm")


class TestFTMOCompliance:
    def test_safe_account(self):
        """Account with no losses should be SAFE."""
        account = make_account(daily_pnl=0, total_pnl=1000)
        report = evaluate_compliance(account)
        assert report.overall_status == AlertLevel.SAFE

    def test_daily_loss_warning(self):
        """FTMO: daily loss = max(balance, initial) - equity. 5% of $100K = $5000."""
        # Balance $100K, equity $96.5K → loss = $3500, 70% used, 30% remaining = WARNING
        account = make_account(total_pnl=0, equity_offset=-3500)
        report = evaluate_compliance(account)
        daily_check = next(c for c in report.checks if c.rule_type == "daily_loss")
        assert daily_check.alert_level == AlertLevel.WARNING

    def test_daily_loss_critical(self):
        """Equity dropped $4300 below balance."""
        account = make_account(total_pnl=0, equity_offset=-4300)
        report = evaluate_compliance(account)
        daily_check = next(c for c in report.checks if c.rule_type == "daily_loss")
        assert daily_check.alert_level == AlertLevel.CRITICAL

    def test_daily_loss_danger(self):
        """Equity dropped $4800 below balance."""
        account = make_account(total_pnl=0, equity_offset=-4800)
        report = evaluate_compliance(account)
        daily_check = next(c for c in report.checks if c.rule_type == "daily_loss")
        assert daily_check.alert_level == AlertLevel.DANGER

    def test_daily_loss_breached(self):
        """Equity dropped $5100 below balance — breached."""
        account = make_account(total_pnl=0, equity_offset=-5100)
        report = evaluate_compliance(account)
        daily_check = next(c for c in report.checks if c.rule_type == "daily_loss")
        assert daily_check.alert_level == AlertLevel.BREACHED
        assert report.overall_status == AlertLevel.BREACHED

    def test_max_drawdown_safe(self):
        """Account with small drawdown should be safe."""
        # FTMO: 10% static DD on $100K = $10K limit
        account = make_account(total_pnl=-2000, equity_offset=0)
        report = evaluate_compliance(account)
        dd_check = next(c for c in report.checks if c.rule_type == "max_drawdown")
        assert dd_check.alert_level == AlertLevel.SAFE

    def test_max_drawdown_danger(self):
        """Account approaching max drawdown."""
        # Lost $9600 = 96% of $10K limit = 4% remaining = DANGER
        account = make_account(total_pnl=-9600, equity_offset=0)
        report = evaluate_compliance(account)
        dd_check = next(c for c in report.checks if c.rule_type == "max_drawdown")
        assert dd_check.alert_level == AlertLevel.DANGER

    def test_max_drawdown_breached(self):
        """Account has breached max drawdown."""
        account = make_account(total_pnl=-10500, equity_offset=0)
        report = evaluate_compliance(account)
        dd_check = next(c for c in report.checks if c.rule_type == "max_drawdown")
        assert dd_check.alert_level == AlertLevel.BREACHED

    def test_min_trading_days(self):
        """Check minimum trading days tracking."""
        account = make_account(trading_days=2)
        report = evaluate_compliance(account)
        days_check = next(c for c in report.checks if c.rule_type == "min_trading_days")
        assert days_check.remaining == 2.0  # need 4, have 2

    def test_overall_status_worst_case(self):
        """Overall status should be the worst across all checks."""
        # Equity dropped $5500 below balance — daily loss breached
        account = make_account(total_pnl=0, equity_offset=-5500)
        report = evaluate_compliance(account)
        assert report.overall_status == AlertLevel.BREACHED


class TestTopStepCompliance:
    def test_trailing_drawdown(self):
        """TopStep uses trailing drawdown — equity high watermark matters."""
        # $100K account, $3K MLL (trailing)
        # If equity peaked at $103K, floor is $100K
        account = make_account(
            firm_name="topstep",
            account_size=100000,
            total_pnl=3000,  # balance = $103K
            equity_offset=-2800,  # equity = $100,200 (near floor of $100K)
        )
        # High watermark is $103K, so drawdown = $103K - $100.2K = $2800
        # Limit = $3000, remaining = $200 = 6.67% → CRITICAL (between 5% and 15%)
        account.equity_high_watermark = 103000
        report = evaluate_compliance(account)
        dd_check = next(c for c in report.checks if c.rule_type == "max_drawdown")
        assert dd_check.alert_level == AlertLevel.CRITICAL

    def test_daily_loss_50k(self):
        """TopStep 50K account has $1000 daily loss limit."""
        account = make_account(firm_name="topstep", account_size=50000, daily_pnl=-850)
        report = evaluate_compliance(account)
        daily_check = next(c for c in report.checks if c.rule_type == "daily_loss")
        # 85% used, 15% remaining → CRITICAL
        assert daily_check.alert_level == AlertLevel.CRITICAL


class TestBreakoutCompliance:
    def test_no_daily_loss_limit(self):
        """Breakout has no daily loss limit."""
        account = make_account(firm_name="breakout", account_size=50000, daily_pnl=-2000)
        report = evaluate_compliance(account)
        daily_check = next(c for c in report.checks if c.rule_type == "daily_loss")
        assert daily_check.alert_level == AlertLevel.SAFE

    def test_static_drawdown_6pct(self):
        """Breakout 1-step: 6% static drawdown."""
        # $50K account, 6% = $3K limit
        # Lost $2700 = 90% used = 10% remaining = WARNING
        account = make_account(firm_name="breakout", account_size=50000, total_pnl=-2700, equity_offset=0)
        report = evaluate_compliance(account)
        dd_check = next(c for c in report.checks if c.rule_type == "max_drawdown")
        assert dd_check.alert_level in (AlertLevel.WARNING, AlertLevel.CRITICAL)
