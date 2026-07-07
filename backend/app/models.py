"""SQLAlchemy models for the M1 data core: import batches, executions, trades."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db import Money, UTCDateTime


class Base(DeclarativeBase):
    pass


class Side(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class AssetType(enum.StrEnum):
    STOCK = "stock"


class Direction(enum.StrEnum):
    LONG = "long"
    SHORT = "short"


class TradeStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column(String(50))
    filename: Mapped[str] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)

    executions: Mapped[list[Execution]] = relationship(back_populates="import_batch")


class Execution(Base):
    """One raw broker fill."""

    __tablename__ = "executions"
    __table_args__ = (Index("ix_executions_account_symbol", "account_label", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column(String(50))
    account_label: Mapped[str] = mapped_column(String(100), default="default")
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType), default=AssetType.STOCK)
    side: Mapped[Side] = mapped_column(Enum(Side))
    qty: Mapped[Decimal] = mapped_column(Money)
    price: Mapped[Decimal] = mapped_column(Money)
    fees: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    raw_row_json: Mapped[str] = mapped_column(Text)
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True)

    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"))
    import_batch: Mapped[ImportBatch] = relationship(back_populates="executions")

    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), default=None)
    trade: Mapped[Trade | None] = relationship(back_populates="executions")


class Trade(Base):
    """A round trip reconstructed from fills by the grouping engine."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_label: Mapped[str] = mapped_column(String(100), default="default")
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[Direction] = mapped_column(Enum(Direction))
    status: Mapped[TradeStatus] = mapped_column(Enum(TradeStatus))

    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    max_qty: Mapped[Decimal] = mapped_column(Money)
    avg_entry_price: Mapped[Decimal] = mapped_column(Money)
    avg_exit_price: Mapped[Decimal | None] = mapped_column(Money, default=None)
    gross_pnl: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    net_pnl: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total_fees: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    hold_time_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    fill_count: Mapped[int] = mapped_column(Integer, default=0)

    # User-annotated fields (editable via API/UI in later milestones)
    planned_stop: Mapped[Decimal | None] = mapped_column(Money, default=None)
    planned_target: Mapped[Decimal | None] = mapped_column(Money, default=None)
    setup_tag: Mapped[str | None] = mapped_column(String(50), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    executions: Mapped[list[Execution]] = relationship(back_populates="trade")

    @property
    def r_multiple(self) -> Decimal | None:
        if self.planned_stop is None:
            return None
        risk_per_share = abs(self.avg_entry_price - self.planned_stop)
        if risk_per_share == 0 or self.max_qty == 0:
            return None
        return self.net_pnl / (risk_per_share * self.max_qty)
