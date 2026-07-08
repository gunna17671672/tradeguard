"""Each built-in rule: proves it fires when breached AND stays quiet on clean trades."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import Trade
from app.rules.engine import AccountSettings, RuleConfigError, evaluate_trades, get_rule_class
from tests.conftest import make_trade

SETTINGS = AccountSettings(account_size="25000", r_value="150")


def audit(trades: list[Trade], rule_id: str, **params: object) -> dict[int, list[str]]:
    """Run one rule over trades; return {trade index -> fired rule ids}."""
    rule = get_rule_class(rule_id).from_config(params)
    audits = evaluate_trades(trades, [rule], SETTINGS)
    by_trade = {id(a.trade): [v.rule_id for v in a.violations] for a in audits}
    return {i: by_trade[id(t)] for i, t in enumerate(trades)}


class TestMaxTradesPerDay:
    def test_fires_on_each_trade_beyond_the_limit(self):
        trades = [make_trade(opened_min=i * 30, closed_min=i * 30 + 10) for i in range(4)]
        result = audit(trades, "max_trades_per_day", n=2)
        assert result == {0: [], 1: [], 2: ["max_trades_per_day"], 3: ["max_trades_per_day"]}

    def test_does_not_overfire_when_trades_spread_across_days(self):
        trades = [
            make_trade(day=0, opened_min=0, closed_min=10),
            make_trade(day=0, opened_min=30, closed_min=40),
            make_trade(day=1, opened_min=0, closed_min=10),
            make_trade(day=1, opened_min=30, closed_min=40),
        ]
        assert audit(trades, "max_trades_per_day", n=2) == {0: [], 1: [], 2: [], 3: []}

    def test_counts_per_account_not_globally(self):
        trades = [
            make_trade(opened_min=0, closed_min=10),
            make_trade(opened_min=20, closed_min=30, account="other"),
            make_trade(opened_min=40, closed_min=50),
        ]
        assert audit(trades, "max_trades_per_day", n=2) == {0: [], 1: [], 2: []}


class TestStopRequired:
    def test_fires_when_no_stop_recorded(self):
        assert audit([make_trade()], "stop_required", within_minutes=5) == {0: ["stop_required"]}

    def test_fires_when_stop_set_too_late(self):
        trade = make_trade(entry="100", stop="99", stop_set_min=12)
        assert audit([trade], "stop_required", within_minutes=5) == {0: ["stop_required"]}

    def test_quiet_when_stop_set_in_time(self):
        trade = make_trade(entry="100", stop="99", stop_set_min=3)
        assert audit([trade], "stop_required", within_minutes=5) == {0: []}

    def test_quiet_when_stop_recorded_but_annotation_time_unknown(self):
        trade = make_trade(entry="100", stop="99")
        assert audit([trade], "stop_required", within_minutes=5) == {0: []}


class TestMaxRiskPerTrade:
    # 1% of the 25k account = $250 max planned risk
    @pytest.mark.parametrize(
        ("qty", "stop", "fires"),
        [
            ("300", "99.00", True),  # $1 x 300 = $300 risk
            ("250", "99.00", False),  # exactly at the $250 limit
            ("100", "98.90", False),  # $110 risk
            ("100", "102.60", True),  # stop distance is absolute: $2.60 x 100 = $260
        ],
    )
    def test_risk_thresholds(self, qty: str, stop: str, fires: bool):
        trade = make_trade(entry="100.00", qty=qty, stop=stop)
        expected = ["max_risk_per_trade"] if fires else []
        assert audit([trade], "max_risk_per_trade", pct_of_account="1.0") == {0: expected}

    def test_skips_trades_without_a_stop(self):
        # stop_required owns the missing-stop case; this rule must stay quiet
        assert audit([make_trade(qty="10000")], "max_risk_per_trade", pct_of_account="1.0") == {
            0: []
        }


class TestBlockedEntryWindow:
    WINDOW = {"start": "09:30", "end": "09:35"}

    # SESSION_START is 09:30 ET; opened_min offsets from there.
    @pytest.mark.parametrize(
        ("opened_min", "fires"),
        [
            (0, True),  # 09:30:00 — window start is inclusive
            (2, True),  # 09:32
            (5, False),  # 09:35:00 — window end is exclusive
            (45, False),  # 10:15
        ],
    )
    def test_window_edges(self, opened_min: int, fires: bool):
        trade = make_trade(opened_min=opened_min, closed_min=opened_min + 10)
        expected = ["blocked_entry_window"] if fires else []
        assert audit([trade], "blocked_entry_window", **self.WINDOW) == {0: expected}

    def test_window_is_evaluated_in_market_time_not_utc(self):
        # 13:32 UTC is 09:32 ET: inside the window in ET, far from 13:30 UTC issues
        trade = make_trade(opened_min=2, closed_min=20)
        assert trade.opened_at.hour == 13  # sanity: stored as UTC
        assert audit([trade], "blocked_entry_window", **self.WINDOW) == {
            0: ["blocked_entry_window"]
        }

    def test_start_must_precede_end(self):
        with pytest.raises(RuleConfigError, match="start must be before end"):
            get_rule_class("blocked_entry_window").from_config({"start": "10:00", "end": "09:00"})


class TestRevengeTrade:
    PARAMS = {"cooldown_minutes": 15, "size_multiplier": "1.5"}

    def loser(self) -> Trade:
        return make_trade(opened_min=0, closed_min=30, qty="100", net_pnl="-80")

    def test_fires_on_fast_oversized_reentry_after_a_loss(self):
        trades = [self.loser(), make_trade(opened_min=35, closed_min=60, qty="150")]
        assert audit(trades, "revenge_trade", **self.PARAMS) == {0: [], 1: ["revenge_trade"]}

    def test_fires_across_symbols(self):
        trades = [self.loser(), make_trade(opened_min=35, closed_min=60, qty="200", symbol="TSLA")]
        assert audit(trades, "revenge_trade", **self.PARAMS)[1] == ["revenge_trade"]

    def test_quiet_when_size_below_multiplier(self):
        trades = [self.loser(), make_trade(opened_min=35, closed_min=60, qty="149")]
        assert audit(trades, "revenge_trade", **self.PARAMS) == {0: [], 1: []}

    def test_quiet_after_cooldown_expires(self):
        trades = [self.loser(), make_trade(opened_min=46, closed_min=70, qty="300")]
        assert audit(trades, "revenge_trade", **self.PARAMS) == {0: [], 1: []}

    def test_quiet_when_previous_trade_won(self):
        winner = make_trade(opened_min=0, closed_min=30, qty="100", net_pnl="120")
        trades = [winner, make_trade(opened_min=35, closed_min=60, qty="300")]
        assert audit(trades, "revenge_trade", **self.PARAMS) == {0: [], 1: []}

    def test_quiet_on_first_trade_of_history(self):
        assert audit([make_trade(qty="500")], "revenge_trade", **self.PARAMS) == {0: []}


class TestMaxDailyLoss:
    def test_flags_every_trade_entered_after_the_breach(self):
        trades = [
            make_trade(opened_min=0, closed_min=10, net_pnl="-300"),
            make_trade(opened_min=15, closed_min=25, net_pnl="-250"),  # entered pre-breach
            make_trade(opened_min=30, closed_min=40, net_pnl="50"),  # entered post-breach
            make_trade(opened_min=45, closed_min=55, net_pnl="-20"),  # still post-breach
        ]
        assert audit(trades, "max_daily_loss", amount="500") == {
            0: [],
            1: [],
            2: ["max_daily_loss"],
            3: ["max_daily_loss"],
        }

    def test_quiet_when_losses_stay_above_limit(self):
        trades = [
            make_trade(opened_min=0, closed_min=10, net_pnl="-499.99"),
            make_trade(opened_min=15, closed_min=25, net_pnl="100"),
        ]
        assert audit(trades, "max_daily_loss", amount="500") == {0: [], 1: []}

    def test_losses_reset_across_session_days(self):
        trades = [
            make_trade(day=0, opened_min=0, closed_min=10, net_pnl="-600"),
            make_trade(day=1, opened_min=0, closed_min=10, net_pnl="-100"),
        ]
        assert audit(trades, "max_daily_loss", amount="500") == {0: [], 1: []}

    def test_r_based_limit_uses_account_r_value(self):
        # 3R x $150 r_value = $450 limit
        trades = [
            make_trade(opened_min=0, closed_min=10, net_pnl="-460"),
            make_trade(opened_min=15, closed_min=25, net_pnl="0"),
        ]
        assert audit(trades, "max_daily_loss", r="3") == {0: [], 1: ["max_daily_loss"]}

    def test_requires_exactly_one_of_amount_or_r(self):
        cls = get_rule_class("max_daily_loss")
        with pytest.raises(RuleConfigError, match="exactly one"):
            cls.from_config({})
        with pytest.raises(RuleConfigError, match="exactly one"):
            cls.from_config({"amount": "500", "r": "3"})

    def test_r_param_requires_r_value_setting(self):
        rule = get_rule_class("max_daily_loss").from_config({"r": "3"})
        with pytest.raises(RuleConfigError, match="requires 'r_value'"):
            rule.validate_against_settings(AccountSettings(account_size="25000"))


class TestAllSixRegistered:
    def test_spec_rule_ids_present(self):
        from app.rules.engine import available_rules

        assert available_rules() == [
            "blocked_entry_window",
            "max_daily_loss",
            "max_risk_per_trade",
            "max_trades_per_day",
            "revenge_trade",
            "stop_required",
        ]

    def test_clean_disciplined_day_produces_zero_violations(self):
        """A realistic clean day passes all six rules simultaneously."""
        rules = [
            get_rule_class("max_trades_per_day").from_config({"n": 4}),
            get_rule_class("stop_required").from_config({"within_minutes": 5}),
            get_rule_class("max_risk_per_trade").from_config({"pct_of_account": "1.0"}),
            get_rule_class("blocked_entry_window").from_config({"start": "09:30", "end": "09:35"}),
            get_rule_class("revenge_trade").from_config(
                {"cooldown_minutes": 15, "size_multiplier": "1.5"}
            ),
            get_rule_class("max_daily_loss").from_config({"amount": "500"}),
        ]
        trades = [
            make_trade(
                opened_min=10,
                closed_min=40,
                qty="100",
                entry="100",
                stop="99",
                stop_set_min=1,
                net_pnl="-90",
            ),
            make_trade(
                opened_min=60,
                closed_min=90,
                qty="120",
                entry="50",
                stop="48.50",
                stop_set_min=0,
                net_pnl="200",
                symbol="AMD",
            ),
        ]
        audits = evaluate_trades(trades, rules, SETTINGS)
        assert all(a.violations == [] for a in audits)
        assert sum(t.net_pnl for t in trades) == Decimal("110")
