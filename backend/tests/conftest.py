"""Shared test helpers: compact builders for synthetic fills."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.importers.base import NormalizedFill
from app.models import Side

SESSION_START = datetime(2026, 6, 1, 13, 30, tzinfo=UTC)  # 09:30 ET


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


@pytest.fixture
def fixtures_dir(request: pytest.FixtureRequest):
    return request.path.parent / "fixtures"
