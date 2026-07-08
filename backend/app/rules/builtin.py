"""The six built-in discipline rules (SPEC.md v1 set).

Each rule is registered under the id used in rules.yaml. Interpretation notes:

- Entry times are evaluated in the account timezone; the blocked entry window
  is half-open [start, end), so an entry at exactly `end` is allowed.
- stop_required: a missing planned_stop always violates. When the trade also
  records *when* the stop was annotated (stop_set_at), setting it more than
  within_minutes after entry violates too; without that timestamp a recorded
  stop gets the benefit of the doubt.
- max_daily_loss takes `amount` (dollars) or `r` (multiples of the account's
  r_value setting); it flags every trade entered after realized PnL for the
  session day has already breached the limit.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

from pydantic import Field, model_validator

from app.models import Trade
from app.rules.engine import (
    AccountSettings,
    PositiveDecimal,
    Rule,
    RuleConfigError,
    RuleContext,
    RuleViolation,
    register,
)

ZERO = Decimal("0")


def _minutes(delta: timedelta) -> str:
    return f"{delta.total_seconds() / 60:g}"


def _money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    return f"-${-quantized}" if quantized < ZERO else f"${quantized}"


@register
class MaxTradesPerDay(Rule):
    rule_id = "max_trades_per_day"

    class Params(Rule.Params):
        n: int = Field(gt=0)

    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        position = ctx.day_trades.index(trade) + 1
        if position <= self.params.n:
            return []
        return [
            self.violation(
                f"Entry #{position} of the day exceeds the limit of {self.params.n} trades"
            )
        ]


@register
class StopRequired(Rule):
    rule_id = "stop_required"

    class Params(Rule.Params):
        within_minutes: int = Field(ge=0)

    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        if trade.planned_stop is None:
            return [self.violation("No planned stop recorded for this trade")]
        if trade.stop_set_at is not None:
            lag = trade.stop_set_at - trade.opened_at
            if lag > timedelta(minutes=self.params.within_minutes):
                return [
                    self.violation(
                        f"Planned stop was set {_minutes(lag)} min after entry "
                        f"(limit {self.params.within_minutes} min)"
                    )
                ]
        return []


@register
class MaxRiskPerTrade(Rule):
    rule_id = "max_risk_per_trade"

    class Params(Rule.Params):
        pct_of_account: PositiveDecimal

    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        if trade.planned_stop is None:  # stop_required is the rule that flags this
            return []
        risk = abs(trade.avg_entry_price - trade.planned_stop) * trade.max_qty
        limit = ctx.settings.account_size * self.params.pct_of_account / 100
        if risk <= limit:
            return []
        return [
            self.violation(
                f"Planned risk {_money(risk)} exceeds {self.params.pct_of_account}% "
                f"of account ({_money(limit)})"
            )
        ]


@register
class BlockedEntryWindow(Rule):
    rule_id = "blocked_entry_window"

    class Params(Rule.Params):
        start: time
        end: time

        @model_validator(mode="after")
        def _start_before_end(self) -> BlockedEntryWindow.Params:
            if self.start >= self.end:
                raise ValueError("start must be before end")
            return self

    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        local = trade.opened_at.astimezone(ctx.tz)
        if not (self.params.start <= local.time() < self.params.end):
            return []
        return [
            self.violation(
                f"Entered at {local:%H:%M:%S} {ctx.tz.key}, inside the blocked window "
                f"{self.params.start:%H:%M}–{self.params.end:%H:%M}"
            )
        ]


@register
class RevengeTrade(Rule):
    rule_id = "revenge_trade"

    class Params(Rule.Params):
        cooldown_minutes: int = Field(gt=0)
        size_multiplier: PositiveDecimal

    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        prev = ctx.previous_closed
        if prev is None or prev.net_pnl >= ZERO:
            return []
        gap = trade.opened_at - prev.closed_at
        if gap > timedelta(minutes=self.params.cooldown_minutes):
            return []
        if trade.max_qty < prev.max_qty * self.params.size_multiplier:
            return []
        return [
            self.violation(
                f"Entered {_minutes(gap)} min after a {_money(prev.net_pnl)} loss on "
                f"{prev.symbol} at {self.params.size_multiplier}x+ its size "
                f"({trade.max_qty} vs {prev.max_qty} shares)"
            )
        ]


@register
class MaxDailyLoss(Rule):
    rule_id = "max_daily_loss"

    class Params(Rule.Params):
        amount: PositiveDecimal | None = None
        r: PositiveDecimal | None = None

        @model_validator(mode="after")
        def _exactly_one(self) -> MaxDailyLoss.Params:
            if (self.amount is None) == (self.r is None):
                raise ValueError("set exactly one of 'amount' (dollars) or 'r' (R multiples)")
            return self

    def validate_against_settings(self, settings: AccountSettings) -> None:
        if self.params.r is not None and settings.r_value is None:
            raise RuleConfigError(
                "rule 'max_daily_loss': param 'r' requires 'r_value' (dollars per 1R) "
                "in the account settings"
            )

    def _limit(self, settings: AccountSettings) -> Decimal:
        if self.params.amount is not None:
            return self.params.amount
        assert settings.r_value is not None  # enforced by validate_against_settings
        return self.params.r * settings.r_value

    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        realized = sum(
            (
                t.net_pnl
                for t in ctx.day_closed_trades
                if t is not trade and t.closed_at <= trade.opened_at
            ),
            ZERO,
        )
        limit = self._limit(ctx.settings)
        if realized > -limit:
            return []
        return [
            self.violation(
                f"Entered after the daily loss limit was breached "
                f"(realized {_money(realized)} vs limit {_money(-limit)})"
            )
        ]
