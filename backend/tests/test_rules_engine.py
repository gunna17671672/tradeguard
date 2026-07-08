"""Rules engine core: registry, params validation, context construction."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import Field

from app.models import Severity, Trade
from app.rules import engine
from app.rules.engine import (
    AccountSettings,
    Rule,
    RuleConfigError,
    RuleContext,
    RuleViolation,
    evaluate_trades,
)
from tests.conftest import make_trade

SETTINGS = AccountSettings(account_size="25000")


class RecordingRule(Rule):
    """Test rule that fires on every trade and records the context it saw."""

    rule_id = "recording"

    class Params(Rule.Params):
        threshold: int = Field(gt=0, default=1)

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.seen: list[tuple[Trade, RuleContext]] = []

    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        self.seen.append((trade, ctx))
        return [self.violation("fired")]


def make_rule() -> RecordingRule:
    return RecordingRule.from_config({})  # type: ignore[return-value]


class TestRegistry:
    def test_register_and_lookup(self):
        engine.register(RecordingRule)
        try:
            assert engine.get_rule_class("recording") is RecordingRule
            assert "recording" in engine.available_rules()
        finally:
            del engine._REGISTRY["recording"]

    def test_duplicate_registration_rejected(self):
        engine.register(RecordingRule)
        try:
            with pytest.raises(ValueError, match="duplicate rule id"):
                engine.register(RecordingRule)
        finally:
            del engine._REGISTRY["recording"]

    def test_unknown_rule_id(self):
        with pytest.raises(RuleConfigError, match="unknown rule 'nope'"):
            engine.get_rule_class("nope")


class TestParams:
    def test_invalid_params_raise_config_error(self):
        with pytest.raises(RuleConfigError, match="recording.*invalid params"):
            RecordingRule.from_config({"threshold": 0})

    def test_unknown_param_rejected(self):
        with pytest.raises(RuleConfigError, match="recording"):
            RecordingRule.from_config({"treshold": 3})

    def test_severity_override(self):
        rule = RecordingRule.from_config({}, severity=Severity.WARN)
        (violation,) = rule.evaluate(make_trade(), None)  # ctx unused by this rule
        assert violation.severity is Severity.WARN

    def test_default_severity_is_violation(self):
        (violation,) = make_rule().evaluate(make_trade(), None)
        assert violation.severity is Severity.VIOLATION


class TestAccountSettings:
    def test_money_is_exact_decimal_even_from_yaml_float(self):
        settings = AccountSettings(account_size=25000.5)
        assert settings.account_size == Decimal("25000.5")

    def test_account_size_must_be_positive(self):
        with pytest.raises(ValueError):
            AccountSettings(account_size="0")


class TestEvaluateTrades:
    def test_day_grouping_uses_market_timezone(self):
        # 19:55 ET and 20:30 ET on June 1 straddle the UTC midnight boundary
        # (23:55 UTC vs 00:30 UTC June 2) but share one ET session day.
        rule = make_rule()
        late = make_trade(opened_min=625, closed_min=630)  # 23:55 UTC
        later = make_trade(opened_min=660, closed_min=665)  # 00:30 UTC June 2
        evaluate_trades([late, later], [rule], SETTINGS)
        (_, ctx_late), (_, ctx_later) = rule.seen
        assert ctx_late.day_trades == [late, later]
        assert ctx_later.day_trades == [late, later]

    def test_previous_closed_crosses_symbols_within_account(self):
        rule = make_rule()
        first = make_trade(opened_min=0, closed_min=10, symbol="AAPL", net_pnl="-50")
        second = make_trade(opened_min=15, closed_min=25, symbol="TSLA")
        evaluate_trades([second, first], [rule], SETTINGS)
        contexts = {t: ctx for t, ctx in rule.seen}
        assert contexts[first].previous_closed is None
        assert contexts[second].previous_closed is first

    def test_previous_closed_never_crosses_accounts(self):
        rule = make_rule()
        other = make_trade(opened_min=0, closed_min=10, account="other")
        mine = make_trade(opened_min=15, closed_min=25)
        evaluate_trades([other, mine], [rule], SETTINGS)
        contexts = {t: ctx for t, ctx in rule.seen}
        assert contexts[mine].previous_closed is None

    def test_day_trades_never_cross_accounts(self):
        rule = make_rule()
        other = make_trade(opened_min=0, account="other")
        mine = make_trade(opened_min=5)
        evaluate_trades([other, mine], [rule], SETTINGS)
        contexts = {t: ctx for t, ctx in rule.seen}
        assert contexts[mine].day_trades == [mine]

    def test_open_trades_are_audited_and_appear_in_day_trades(self):
        rule = make_rule()
        open_trade = make_trade(opened_min=0, closed_min=None)
        audits = evaluate_trades([open_trade], [rule], SETTINGS)
        assert audits[0].trade is open_trade
        assert audits[0].violations[0].message == "fired"
        (_, ctx) = rule.seen[0]
        assert ctx.day_trades == [open_trade]
        assert ctx.day_closed_trades == []

    def test_audits_ordered_by_entry_time(self):
        rule = make_rule()
        t2 = make_trade(opened_min=20, closed_min=30)
        t1 = make_trade(opened_min=0, closed_min=10)
        audits = evaluate_trades([t2, t1], [rule], SETTINGS)
        assert [a.trade for a in audits] == [t1, t2]

    def test_no_rules_yields_clean_audits(self):
        audits = evaluate_trades([make_trade()], [], SETTINGS)
        assert audits[0].violations == []
