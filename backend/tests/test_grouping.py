"""Table-driven tests for the fills -> trades grouping engine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.grouping import group_fills
from app.models import Direction, TradeStatus
from tests.conftest import make_fill

D = Decimal


class TestSimpleRoundTrips:
    def test_long_round_trip(self):
        fills = [
            make_fill("buy", "100", "10.00", minute=0),
            make_fill("sell", "100", "11.00", minute=5),
        ]
        (t,) = group_fills(fills)
        assert t.direction is Direction.LONG
        assert t.status is TradeStatus.CLOSED
        assert t.gross_pnl == D("100.00")
        assert t.max_qty == D("100")
        assert t.avg_entry_price == D("10.00")
        assert t.avg_exit_price == D("11.00")
        assert t.fill_count == 2
        assert t.hold_time_seconds == 300

    def test_short_round_trip(self):
        fills = [
            make_fill("sell", "50", "20.00", minute=0),
            make_fill("buy", "50", "18.50", minute=10),
        ]
        (t,) = group_fills(fills)
        assert t.direction is Direction.SHORT
        assert t.status is TradeStatus.CLOSED
        assert t.gross_pnl == D("75.00")

    def test_losing_short(self):
        fills = [
            make_fill("sell", "10", "5.00", minute=0),
            make_fill("buy", "10", "6.00", minute=1),
        ]
        (t,) = group_fills(fills)
        assert t.gross_pnl == D("-10.00")


class TestPartialFills:
    def test_scale_in_scale_out_fifo(self):
        # Buy 100@10, buy 100@12; sell 150@13 (FIFO: 100@10 + 50@12), sell 50@11
        fills = [
            make_fill("buy", "100", "10.00", minute=0),
            make_fill("buy", "100", "12.00", minute=1),
            make_fill("sell", "150", "13.00", minute=2),
            make_fill("sell", "50", "11.00", minute=3),
        ]
        (t,) = group_fills(fills)
        assert t.status is TradeStatus.CLOSED
        # FIFO: (13-10)*100 + (13-12)*50 + (11-12)*50 = 300 + 50 - 50 = 300
        assert t.gross_pnl == D("300.00")
        assert t.max_qty == D("200")
        assert t.avg_entry_price == D("11.00")
        assert t.avg_exit_price == D("12.50")
        assert t.fill_count == 4

    def test_fifo_differs_from_lifo(self):
        # FIFO must match the first lot, not the most recent one.
        fills = [
            make_fill("buy", "10", "100.00", minute=0),
            make_fill("buy", "10", "200.00", minute=1),
            make_fill("sell", "10", "150.00", minute=2),
            make_fill("sell", "10", "150.00", minute=3),
        ]
        (t,) = group_fills(fills)
        # FIFO: (150-100)*10 + (150-200)*10 = 0; LIFO would give the same total
        # but per-exit attribution differs — total must be 0 either way,
        # so also check an asymmetric case below.
        assert t.gross_pnl == D("0.00")

    def test_fifo_partial_lot_split(self):
        # Sell 15 against lots [10@10, 10@20]: matches 10@10 fully + 5@20.
        fills = [
            make_fill("buy", "10", "10.00", minute=0),
            make_fill("buy", "10", "20.00", minute=1),
            make_fill("sell", "15", "30.00", minute=2),
        ]
        (t,) = group_fills(fills)
        assert t.status is TradeStatus.OPEN
        # Realized: (30-10)*10 + (30-20)*5 = 250
        assert t.gross_pnl == D("250.00")

    def test_short_scale_fifo(self):
        # Short 100@50, short 100@48; cover 150@45: FIFO (50-45)*100 + (48-45)*50
        fills = [
            make_fill("sell", "100", "50.00", minute=0),
            make_fill("sell", "100", "48.00", minute=1),
            make_fill("buy", "150", "45.00", minute=2),
            make_fill("buy", "50", "49.00", minute=3),
        ]
        (t,) = group_fills(fills)
        assert t.direction is Direction.SHORT
        assert t.status is TradeStatus.CLOSED
        # (50-45)*100 + (48-45)*50 + (48-49)*50 = 500 + 150 - 50 = 600
        assert t.gross_pnl == D("600.00")


class TestTradeBoundaries:
    def test_two_sequential_trades_same_symbol(self):
        fills = [
            make_fill("buy", "100", "10.00", minute=0),
            make_fill("sell", "100", "11.00", minute=5),
            make_fill("buy", "200", "12.00", minute=30),
            make_fill("sell", "200", "11.50", minute=45),
        ]
        t1, t2 = group_fills(fills)
        assert t1.gross_pnl == D("100.00")
        assert t2.gross_pnl == D("-100.00")
        assert t1.closed_at < t2.opened_at

    def test_open_position_is_open_trade(self):
        fills = [make_fill("buy", "100", "10.00", minute=0)]
        (t,) = group_fills(fills)
        assert t.status is TradeStatus.OPEN
        assert t.closed_at is None
        assert t.avg_exit_price is None
        assert t.gross_pnl == D("0")
        assert t.hold_time_seconds is None

    def test_flip_long_to_short_splits_fill(self):
        # Long 100, sell 150 -> closes long (100) and opens short (50).
        fills = [
            make_fill("buy", "100", "10.00", minute=0),
            make_fill("sell", "150", "11.00", minute=5),
            make_fill("buy", "50", "10.50", minute=10),
        ]
        t1, t2 = group_fills(fills)
        assert t1.direction is Direction.LONG
        assert t1.status is TradeStatus.CLOSED
        assert t1.gross_pnl == D("100.00")
        assert t1.max_qty == D("100")
        assert t2.direction is Direction.SHORT
        assert t2.status is TradeStatus.CLOSED
        assert t2.max_qty == D("50")
        assert t2.gross_pnl == D("25.00")  # (11 - 10.50) * 50
        assert t2.opened_at == t1.closed_at  # same fill closes one, opens the other

    def test_symbols_and_accounts_grouped_independently(self):
        fills = [
            make_fill("buy", "10", "10.00", minute=0, symbol="AAPL"),
            make_fill("buy", "5", "200.00", minute=1, symbol="TSLA"),
            make_fill("sell", "10", "11.00", minute=2, symbol="AAPL"),
            make_fill("sell", "5", "210.00", minute=3, symbol="TSLA"),
            make_fill("buy", "10", "10.00", minute=0, symbol="AAPL", account="ira"),
        ]
        trades = group_fills(fills)
        assert len(trades) == 3
        closed = [t for t in trades if t.status is TradeStatus.CLOSED]
        assert {t.symbol for t in closed} == {"AAPL", "TSLA"}
        (open_trade,) = [t for t in trades if t.status is TradeStatus.OPEN]
        assert open_trade.account_label == "ira"

    def test_out_of_order_input_is_sorted_by_time(self):
        fills = [
            make_fill("sell", "100", "11.00", minute=5),
            make_fill("buy", "100", "10.00", minute=0),
        ]
        (t,) = group_fills(fills)
        assert t.direction is Direction.LONG
        assert t.gross_pnl == D("100.00")


class TestFees:
    def test_net_pnl_subtracts_fees(self):
        fills = [
            make_fill("buy", "100", "10.00", minute=0, fees="1.00"),
            make_fill("sell", "100", "11.00", minute=5, fees="1.05"),
        ]
        (t,) = group_fills(fills)
        assert t.gross_pnl == D("100.00")
        assert t.total_fees == D("2.05")
        assert t.net_pnl == D("97.95")

    def test_flip_fill_fees_prorated(self):
        # Sell 150 with $3 fees closing a 100-share long: $2 to the closing
        # trade, $1 to the new short.
        fills = [
            make_fill("buy", "100", "10.00", minute=0),
            make_fill("sell", "150", "11.00", minute=5, fees="3.00"),
        ]
        t1, t2 = group_fills(fills)
        assert t1.total_fees == D("2.00")
        assert t2.total_fees == D("1.00")


class TestDecimalDiscipline:
    @pytest.mark.parametrize(
        "qty,entry,exit_,expected",
        [
            ("3", "10.10", "10.20", "0.30"),
            ("7", "0.0001", "0.0003", "0.0014"),
            ("1000000", "10.01", "10.02", "10000.00"),
        ],
    )
    def test_pnl_is_exact(self, qty: str, entry: str, exit_: str, expected: str):
        fills = [
            make_fill("buy", qty, entry, minute=0),
            make_fill("sell", qty, exit_, minute=1),
        ]
        (t,) = group_fills(fills)
        assert t.gross_pnl == D(expected)
        assert isinstance(t.gross_pnl, Decimal)
