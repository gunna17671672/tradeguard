"""Pydantic schemas at API boundaries. Money serializes as string, never float."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.models import AssetType, Direction, Severity, Side, TradeStatus

MoneyStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class HealthRead(BaseModel):
    """GET /api/health: liveness plus the resolved runtime configuration."""

    status: str
    db_path: str  # fully resolved — independent of the launch directory
    rules_path: str | None


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
    skipped_unfilled: int  # source rows for orders that never (fully) executed
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


class ImportDeleteResponse(BaseModel):
    """Summary returned by DELETE /api/imports/{batch_id}: what was reverted."""

    batch_id: int
    broker: str
    filename: str
    fills_deleted: int
    trades_rebuilt: int
    violations_recorded: int
    audited: bool  # False when no rules.yaml is configured


class StatsSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    closed_trades: int
    wins: int
    losses: int
    scratches: int
    win_rate_pct: MoneyStr | None
    profit_factor: MoneyStr | None
    avg_win: MoneyStr | None
    avg_loss: MoneyStr | None
    expectancy: MoneyStr | None
    gross_pnl: MoneyStr
    net_pnl: MoneyStr
    total_fees: MoneyStr


class EquityPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_id: int
    closed_at: datetime
    net_pnl: MoneyStr
    cumulative_pnl: MoneyStr


class CalendarDayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    net_pnl: MoneyStr
    trade_count: int


class WeeklyReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    week_start: date
    week_end: date
    closed_trades: int
    wins: int
    losses: int
    gross_pnl: MoneyStr
    net_pnl: MoneyStr
    total_fees: MoneyStr
    adherence_pct: MoneyStr | None
    violation_count: int
    violations_by_rule: dict[str, int]
    streak_days: int


class RulesFileRead(BaseModel):
    """rules.yaml as the Settings editor sees it: raw sections plus metadata."""

    account: dict[str, Any]
    rules: dict[str, Any]
    enabled_rule_ids: list[str]
    available_rules: list[str]


class RulesFileWrite(BaseModel):
    """PUT /api/rules body: the two rules.yaml sections, validated before write."""

    model_config = ConfigDict(extra="forbid")

    account: dict[str, Any]
    rules: dict[str, Any] = {}


class RulesUpdateResponse(RulesFileRead):
    violations_recorded: int  # from the re-audit that follows a rules change
