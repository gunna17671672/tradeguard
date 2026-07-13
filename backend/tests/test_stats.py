"""Performance stats: summary, equity curve, PnL calendar."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.stats import equity_curve, pnl_calendar, summarize
from tests.conftest import make_trade

ET = ZoneInfo("America/New_York")
# SESSION_START in conftest is Monday 2026-06-01 09:30 ET
D = Decimal


class TestSummarize:
    def test_empty_gives_zero_counts_and_none_ratios(self):
        s = summarize([])
        assert s.closed_trades == 0
        assert s.win_rate_pct is None
        assert s.profit_factor is None
        assert s.avg_win is None
        assert s.avg_loss is None
        assert s.expectancy is None
        assert s.net_pnl == D("0")

    def test_counts_and_win_rate(self):
        trades = [
            make_trade(net_pnl="100"),
            make_trade(net_pnl="-50"),
            make_trade(net_pnl="300"),
            make_trade(net_pnl="0"),  # scratch: neither win nor loss
        ]
        s = summarize(trades)
        assert (s.closed_trades, s.wins, s.losses, s.scratches) == (4, 2, 1, 1)
        assert s.win_rate_pct == D("50.0")

    def test_profit_factor_and_averages(self):
        trades = [
            make_trade(net_pnl="100"),
            make_trade(net_pnl="200"),
            make_trade(net_pnl="-100"),
            make_trade(net_pnl="-50"),
        ]
        s = summarize(trades)
        assert s.profit_factor == D("2.00")  # 300 / 150
        assert s.avg_win == D("150")
        assert s.avg_loss == D("-75")
        assert s.expectancy == D("37.5")
        assert s.net_pnl == D("150")

    def test_profit_factor_none_when_no_losses(self):
        s = summarize([make_trade(net_pnl="100")])
        assert s.profit_factor is None
        assert s.avg_loss is None
        assert s.win_rate_pct == D("100.0")

    def test_thirds_quantized_to_one_place(self):
        trades = [make_trade(net_pnl="1"), make_trade(net_pnl="-1"), make_trade(net_pnl="-2")]
        assert summarize(trades).win_rate_pct == D("33.3")


class TestEquityCurve:
    def test_cumulative_in_close_order(self):
        trades = [
            make_trade(opened_min=40, closed_min=60, net_pnl="-50"),
            make_trade(opened_min=0, closed_min=30, net_pnl="100"),
        ]
        for i, t in enumerate(trades):
            t.id = i + 1
        points = equity_curve(trades)
        assert [p.cumulative_pnl for p in points] == [D("100"), D("50")]
        assert [p.trade_id for p in points] == [2, 1]

    def test_empty(self):
        assert equity_curve([]) == []


class TestPnlCalendar:
    def test_buckets_by_session_day_in_account_tz(self):
        trades = [
            make_trade(day=0, net_pnl="100"),
            make_trade(day=0, opened_min=60, closed_min=90, net_pnl="-30"),
            # closes 23:30 ET Tue = 03:30 UTC Wed; must count as the ET Tuesday
            make_trade(day=1, opened_min=800, closed_min=840, net_pnl="10"),
        ]
        days = pnl_calendar(trades, ET)
        assert [(d.day, d.net_pnl, d.trade_count) for d in days] == [
            (date(2026, 6, 1), D("70"), 2),
            (date(2026, 6, 2), D("10"), 1),
        ]

    def test_empty(self):
        assert pnl_calendar([], ET) == []
