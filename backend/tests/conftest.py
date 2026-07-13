"""Shared test helpers: compact builders for synthetic fills and trades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.importers.base import NormalizedFill
from app.ingest import ImportResult, import_fills
from app.main import create_app
from app.models import Direction, Severity, Side, Trade, TradeStatus, Violation
from app.rules.loader import load_rules_config

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


# Rules used by the API test app: max_trades_per_day(2) so a third same-day
# entry is dirty, and max_risk_per_trade (fires only when a stop exists, and
# 1% of 25k = $250) so PATCHing a stop can add or remove violations.
API_TEST_RULES = """\
account:
  account_size: "25000"
  timezone: America/New_York

rules:
  max_trades_per_day:
    n: 2
  max_risk_per_trade:
    pct_of_account: "1.0"
"""


@dataclass
class ApiHarness:
    """A TestClient plus direct DB/rules access for seeding and assertions."""

    client: TestClient
    session_factory: sessionmaker[Session]
    rules_path: Path
    db_path: Path

    def seed(
        self, fills: list[NormalizedFill], broker: str = "test", filename: str = "seed.csv"
    ) -> ImportResult:
        """Ingest synthetic fills the same way the CLI/API would, audit included."""
        config = load_rules_config(self.rules_path)
        with session_scope(self.session_factory) as session:
            return import_fills(
                session, fills, broker=broker, filename=filename, rules_config=config
            )


@pytest.fixture
def api(tmp_path: Path) -> ApiHarness:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(API_TEST_RULES, encoding="utf-8")
    db_path = tmp_path / "test.db"
    app = create_app(db_path=db_path, rules_path=rules_path)
    return ApiHarness(
        client=TestClient(app),
        session_factory=app.state.session_factory,
        rules_path=rules_path,
        db_path=db_path,
    )


def round_trip(
    symbol: str = "AAPL",
    entry_min: int = 0,
    exit_min: int = 30,
    qty: str = "100",
    entry: str = "100",
    exit_price: str = "101",
    day_offset_min: int = 0,
) -> list[NormalizedFill]:
    """A buy+sell pair that groups into one closed long trade."""
    return [
        make_fill("buy", qty, entry, minute=day_offset_min + entry_min, symbol=symbol),
        make_fill("sell", qty, exit_price, minute=day_offset_min + exit_min, symbol=symbol),
    ]
