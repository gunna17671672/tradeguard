"""Adherence score, violation-free streak, and weekly report data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models import Severity, Trade
from app.reports import (
    adherence_score,
    build_weekly_report,
    fetch_weekly_report,
    violation_free_streak_days,
    week_bounds,
)
from app.rules.engine import AccountSettings
from tests.conftest import make_trade, make_violation

ET = ZoneInfo("America/New_York")
SETTINGS = AccountSettings(account_size="25000")
# SESSION_START in conftest is Monday 2026-06-01 09:30 ET
MONDAY = date(2026, 6, 1)

D = Decimal


def dirty(trade: Trade, rule_id: str = "stop_required") -> Trade:
    trade.violations.append(make_violation(rule_id))
    return trade


class TestAdherenceScore:
    def test_percentage_of_clean_closed_trades(self):
        trades = [make_trade(), dirty(make_trade()), make_trade(), make_trade()]
        assert adherence_score(trades) == D("75.0")

    def test_all_clean_is_100(self):
        assert adherence_score([make_trade(), make_trade()]) == D("100.0")

    def test_no_trades_is_none_not_zero(self):
        assert adherence_score([]) is None

    def test_thirds_are_quantized(self):
        trades = [dirty(make_trade()), make_trade(), make_trade()]
        assert adherence_score(trades) == D("66.7")

    def test_warn_and_info_findings_do_not_hurt_adherence(self):
        trade = make_trade()
        trade.violations.append(make_violation("stop_required", Severity.WARN))
        trade.violations.append(make_violation("max_trades_per_day", Severity.INFO))
        assert adherence_score([trade]) == D("100.0")


class TestViolationFreeStreak:
    def test_counts_consecutive_clean_trading_days(self):
        trades = [
            dirty(make_trade(day=0, opened_min=0, closed_min=10)),
            make_trade(day=1, opened_min=0, closed_min=10),
            make_trade(day=3, opened_min=0, closed_min=10),  # gap day 2 doesn't break it
            make_trade(day=4, opened_min=0, closed_min=10),
        ]
        assert violation_free_streak_days(trades, ET) == 3

    def test_zero_when_latest_day_has_a_violation(self):
        trades = [
            make_trade(day=0, opened_min=0, closed_min=10),
            dirty(make_trade(day=1, opened_min=0, closed_min=10)),
        ]
        assert violation_free_streak_days(trades, ET) == 0

    def test_one_dirty_trade_spoils_its_whole_day(self):
        trades = [
            make_trade(day=0, opened_min=0, closed_min=10),
            dirty(make_trade(day=0, opened_min=30, closed_min=40)),
        ]
        assert violation_free_streak_days(trades, ET) == 0

    def test_no_trades_means_no_streak(self):
        assert violation_free_streak_days([], ET) == 0


class TestWeekBounds:
    def test_monday_through_sunday(self):
        assert week_bounds(date(2026, 6, 3)) == (date(2026, 6, 1), date(2026, 6, 7))
        assert week_bounds(date(2026, 6, 1)) == (date(2026, 6, 1), date(2026, 6, 7))
        assert week_bounds(date(2026, 6, 7)) == (date(2026, 6, 1), date(2026, 6, 7))


class TestWeeklyReport:
    def trades(self) -> list[Trade]:
        return [
            make_trade(day=0, opened_min=0, closed_min=10, net_pnl="150"),
            dirty(make_trade(day=1, opened_min=0, closed_min=10, net_pnl="-80")),
            dirty(make_trade(day=1, opened_min=30, closed_min=40, net_pnl="40"), "revenge_trade"),
            make_trade(day=2, opened_min=0, closed_min=10, net_pnl="0"),  # scratch
            make_trade(day=2, opened_min=30, closed_min=None),  # still open: excluded
            make_trade(day=7, opened_min=0, closed_min=10, net_pnl="999"),  # next week
        ]

    def test_summarizes_only_the_requested_week(self):
        report = build_weekly_report(self.trades(), MONDAY, SETTINGS)
        assert (report.week_start, report.week_end) == (MONDAY, date(2026, 6, 7))
        assert report.closed_trades == 4
        assert report.wins == 2
        assert report.losses == 1
        assert report.net_pnl == D("110")
        assert report.adherence_pct == D("50.0")
        assert report.violation_count == 2
        assert report.violations_by_rule == {"stop_required": 1, "revenge_trade": 1}

    def test_any_day_of_the_week_selects_the_same_week(self):
        wednesday = build_weekly_report(self.trades(), date(2026, 6, 3), SETTINGS)
        assert wednesday.closed_trades == 4

    def test_streak_spans_history_beyond_the_week(self):
        # Day 1 was dirty; days 2 and 7 (the following Monday) are clean.
        report = build_weekly_report(self.trades(), date(2026, 6, 8), SETTINGS)
        assert report.closed_trades == 1
        assert report.streak_days == 2

    def test_empty_week(self):
        report = build_weekly_report(self.trades(), date(2026, 7, 6), SETTINGS)
        assert report.closed_trades == 0
        assert report.adherence_pct is None
        assert report.net_pnl == D("0")
        assert report.violations_by_rule == {}


class TestFetchWeeklyReport:
    def test_fetch_scopes_to_account_and_loads_violations(self, tmp_path):
        from app.db import init_db, make_engine, make_session_factory

        engine = make_engine(tmp_path / "t.db")
        init_db(engine)
        with make_session_factory(engine)() as session:
            mine = dirty(make_trade(day=0, opened_min=0, closed_min=10, net_pnl="-50"))
            other = make_trade(day=0, opened_min=0, closed_min=10, account="other", net_pnl="700")
            session.add_all([mine, other])
            session.commit()

        with make_session_factory(engine)() as session:
            report = fetch_weekly_report(session, MONDAY, SETTINGS)
            assert report.closed_trades == 1
            assert report.net_pnl == D("-50")
            assert report.adherence_pct == D("0.0")
            assert report.violations_by_rule == {"stop_required": 1}
