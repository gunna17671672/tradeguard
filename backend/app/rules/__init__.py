"""Discipline rules engine: rule contract, built-ins, registry, evaluator."""

from __future__ import annotations

from app.rules import builtin as _builtin  # noqa: F401 — registers the built-in rules
from app.rules.engine import (
    AccountSettings,
    Rule,
    RuleConfigError,
    RuleContext,
    RuleViolation,
    TradeAudit,
    available_rules,
    evaluate_trades,
    get_rule_class,
    register,
    session_date,
)

__all__ = [
    "AccountSettings",
    "Rule",
    "RuleConfigError",
    "RuleContext",
    "RuleViolation",
    "TradeAudit",
    "available_rules",
    "evaluate_trades",
    "get_rule_class",
    "register",
    "session_date",
]
