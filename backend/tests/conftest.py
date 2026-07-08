"""Shared test helpers: compact builders for synthetic fills and trades."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.importers.base import NormalizedFill
from app.models import Direction, Severity, Side, Trade, TradeStatus, Violation

SESSION_START = datetime(2026, 6, 1, 13, 30, tzinfo=UTC)  # Mon 2026-06-01 09:30 ET


def make_fill(
    side: str,
    qty: str,
    price: str,
    minute: int = 0,
    symbol: str = "AAPL",
    fees: str = "0",
    account: str = "default",
    broker: str = "test",
) -> NormalizedFill:
    return NormalizedFill(
        broker=broker,
        symbol=symbol,
        side=Side(side),
        qty=Decimal(qty),
        price=Decimal(price),
        fees=Decimal(fees),
        executed_at=SESSION_START + timedelta(minutes=minute),
        account_label=account,
    )


def make_trade(
    *,
    opened_min: int = 0,
    closed_min: int | None = 30,
    day: int = 0,
    net_pnl: str = "0",
    qty: str = "100",
    entry: str = "100",
    stop: str | None = None,
    stop_set_min: int | None = None,
    symbol: str = "AAPL",
    account: str = "default",
    direction: Direction = Direction.LONG,
) -> Trade:
    """Synthetic closed (or open, if closed_min=None) trade relative to SESSION_START."""
    opened = SESSION_START + timedelta(days=day, minutes=opened_min)
    closed = None if closed_min is None else SESSION_START + timedelta(days=day, minutes=closed_min)
    pnl = Decimal(net_pnl)
    return Trade(
        account_label=account,
        symbol=symbol,
        direction=direction,
        status=TradeStatus.OPEN if closed is None else TradeStatus.CLOSED,
        opened_at=opened,
        closed_at=closed,
        max_qty=Decimal(qty),
        avg_entry_price=Decimal(entry),
        avg_exit_price=None,
        gross_pnl=pnl,
        net_pnl=pnl,
        total_fees=Decimal("0"),
        fill_count=2,
        planned_stop=None if stop is None else Decimal(stop),
        stop_set_at=None if stop_set_min is None else opened + timedelta(minutes=stop_set_min),
    )


def make_violation(
    rule_id: str = "test_rule", severity: Severity = Severity.VIOLATION
) -> Violation:
    return Violation(rule_id=rule_id, severity=severity, message=f"{rule_id} fired")


@pytest.fixture
def fixtures_dir(request: pytest.FixtureRequest):
    return request.path.parent / "fixtures"
