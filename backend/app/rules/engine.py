"""Rules engine core: rule contract, evaluation context, registry, evaluator.

A rule is a small pure class: `evaluate(trade, ctx)` returns the violations it
found for that one trade. The context exposes that session day's trades, the
previous closed trade, and account settings. Rules register themselves by id
(the key used in rules.yaml), so adding a rule is one file in builtin.py.

Session days are evaluated in the account's timezone (default
America/New_York): a trade entered at 23:55 UTC belongs to the ET calendar day.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, ClassVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from app.models import Severity, Trade


class RuleConfigError(Exception):
    """Raised when a rule id is unknown or its configured params are invalid."""


def _decimal_via_str(value: object) -> object:
    """Route floats through str() so YAML numbers become exact Decimals."""
    return str(value) if isinstance(value, float) else value


ParamDecimal = Annotated[Decimal, BeforeValidator(_decimal_via_str)]
PositiveDecimal = Annotated[ParamDecimal, Field(gt=0)]


class AccountSettings(BaseModel):
    """The `account:` section of rules.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_size: PositiveDecimal
    timezone: str = "America/New_York"
    r_value: PositiveDecimal | None = None  # dollars per 1R, for R-based rule params


@dataclass(frozen=True)
class RuleViolation:
    """A violation as produced by a rule; persistence maps it to a DB row."""

    rule_id: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class RuleContext:
    """What a rule may look at besides the trade itself."""

    day_trades: list[Trade]  # trades entered this session day, ordered by entry time
    day_closed_trades: list[Trade]  # trades closed this session day, ordered by close time
    previous_closed: Trade | None  # most recent trade closed at or before this entry
    settings: AccountSettings
    tz: ZoneInfo


class Rule(ABC):
    """One discipline rule. Subclasses set rule_id and a Params model."""

    rule_id: ClassVar[str]
    default_severity: ClassVar[Severity] = Severity.VIOLATION

    class Params(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

    def __init__(self, params: BaseModel, severity: Severity | None = None) -> None:
        self.params = params
        self.severity = severity if severity is not None else self.default_severity

    @classmethod
    def from_config(cls, raw_params: dict[str, object], severity: Severity | None = None) -> Rule:
        try:
            params = cls.Params(**raw_params)
        except ValidationError as exc:
            raise RuleConfigError(f"rule {cls.rule_id!r}: invalid params: {exc}") from exc
        return cls(params, severity)

    def validate_against_settings(self, settings: AccountSettings) -> None:  # noqa: B027
        """Optional hook for params that depend on account settings; raise RuleConfigError."""

    def violation(self, message: str) -> RuleViolation:
        return RuleViolation(rule_id=self.rule_id, severity=self.severity, message=message)

    @abstractmethod
    def evaluate(self, trade: Trade, ctx: RuleContext) -> list[RuleViolation]:
        """Return violations for this trade (empty list when compliant)."""


_REGISTRY: dict[str, type[Rule]] = {}


def register(cls: type[Rule]) -> type[Rule]:
    if cls.rule_id in _REGISTRY:
        raise ValueError(f"duplicate rule id {cls.rule_id!r}")
    _REGISTRY[cls.rule_id] = cls
    return cls


def get_rule_class(rule_id: str) -> type[Rule]:
    try:
        return _REGISTRY[rule_id]
    except KeyError:
        raise RuleConfigError(
            f"unknown rule {rule_id!r}; available: {', '.join(available_rules())}"
        ) from None


def available_rules() -> list[str]:
    return sorted(_REGISTRY)


def session_date(moment: datetime, tz: ZoneInfo) -> date:
    """Calendar day of a UTC moment in the account's market timezone."""
    return moment.astimezone(tz).date()


@dataclass(frozen=True)
class TradeAudit:
    trade: Trade
    violations: list[RuleViolation] = field(default_factory=list)


def evaluate_trades(
    trades: Sequence[Trade], rules: Sequence[Rule], settings: AccountSettings
) -> list[TradeAudit]:
    """Audit every trade against every rule. Pure: no DB access.

    Context is built per account: day groupings and the previous closed trade
    never cross account labels. Result is ordered by trade entry time.
    """
    tz = ZoneInfo(settings.timezone)
    by_account: dict[str, list[Trade]] = {}
    for t in trades:
        by_account.setdefault(t.account_label, []).append(t)

    audits: list[TradeAudit] = []
    for account_trades in by_account.values():
        audits.extend(_evaluate_account(account_trades, rules, settings, tz))
    audits.sort(key=lambda a: a.trade.opened_at)
    return audits


def _evaluate_account(
    trades: list[Trade], rules: Sequence[Rule], settings: AccountSettings, tz: ZoneInfo
) -> list[TradeAudit]:
    opened_order = sorted(trades, key=lambda t: t.opened_at)
    closed_order = sorted((t for t in trades if t.closed_at is not None), key=lambda t: t.closed_at)

    entered_by_day: dict[date, list[Trade]] = {}
    for t in opened_order:
        entered_by_day.setdefault(session_date(t.opened_at, tz), []).append(t)
    closed_by_day: dict[date, list[Trade]] = {}
    for t in closed_order:
        closed_by_day.setdefault(session_date(t.closed_at, tz), []).append(t)

    audits: list[TradeAudit] = []
    for t in opened_order:
        previous_closed = None
        for c in closed_order:
            if c is t:
                continue
            if c.closed_at > t.opened_at:
                break
            previous_closed = c
        day = session_date(t.opened_at, tz)
        ctx = RuleContext(
            day_trades=entered_by_day[day],
            day_closed_trades=closed_by_day.get(day, []),
            previous_closed=previous_closed,
            settings=settings,
            tz=tz,
        )
        found = [v for rule in rules for v in rule.evaluate(t, ctx)]
        audits.append(TradeAudit(trade=t, violations=found))
    return audits
