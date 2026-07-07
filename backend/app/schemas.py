"""Pydantic schemas at API boundaries. Money serializes as string, never float."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.models import AssetType, Direction, Side, TradeStatus

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


class ImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker: str
    filename: str
    imported_at: datetime
    inserted_count: int
    skipped_count: int
