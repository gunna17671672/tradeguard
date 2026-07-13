"""Pydantic schemas at API boundaries. Money serializes as string, never float."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.models import AssetType, Direction, Severity, Side, TradeStatus

MoneyStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker: str
    account_label: str
    symbol: str
    asset_type: AssetType
    side: Side
    qty: MoneyStr
    price: MoneyStr
    fees: MoneyStr
    executed_at: datetime
    trade_id: int | None


class ViolationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trade_id: int
    rule_id: str
    severity: Severity
    message: str


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_label: str
    symbol: str
    direction: Direction
    status: TradeStatus
    opened_at: datetime
    closed_at: datetime | None
    max_qty: MoneyStr
    avg_entry_price: MoneyStr
    avg_exit_price: MoneyStr | None
    gross_pnl: MoneyStr
    net_pnl: MoneyStr
    total_fees: MoneyStr
    hold_time_seconds: int | None
    fill_count: int
    planned_stop: MoneyStr | None
    planned_target: MoneyStr | None
    setup_tag: str | None
    notes: str | None
    stop_set_at: datetime | None
    r_multiple: MoneyStr | None
    violations: list[ViolationRead]


class TradeDetail(TradeRead):
    executions: list[ExecutionRead]


class TradePage(BaseModel):
    items: list[TradeRead]
    total: int
    limit: int
    offset: int


class TradeUpdate(BaseModel):
    """PATCH /api/trades/{id} body. Only fields present in the request change;
    an explicit null clears the field."""

    model_config = ConfigDict(extra="forbid")

    planned_stop: Decimal | None = Field(default=None, gt=0)
    planned_target: Decimal | None = Field(default=None, gt=0)
    setup_tag: str | None = Field(default=None, max_length=50)
    notes: str | None = None


class ViolationFeedItem(ViolationRead):
    """A violation joined with enough of its trade to render a feed row."""

    symbol: str
    opened_at: datetime
    closed_at: datetime | None
    net_pnl: MoneyStr


class ViolationPage(BaseModel):
    items: list[ViolationFeedItem]
    total: int
    limit: int
    offset: int


class ImportResponse(BaseModel):
    """Batch summary returned by POST /api/imports."""

    batch_id: int
    broker: str
    filename: str
    inserted: int
    skipped_duplicates: int
    trades_rebuilt: int
    violations_recorded: int
    audited: bool  # False when no rules.yaml is configured


class ImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker: str
    filename: str
    imported_at: datetime
    inserted_count: int
    skipped_count: int
