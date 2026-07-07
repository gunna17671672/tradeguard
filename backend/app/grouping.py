"""Fills -> trades grouping engine.

Pure functions: takes normalized fills, returns computed trades. Per
(account_label, symbol), net position is tracked through time; a trade opens
when position leaves 0 and closes when it returns to 0. PnL attribution uses
FIFO lot matching. A single fill that crosses through 0 (e.g. long 100, sell
150) is split: it closes the current trade and opens a new one in the opposite
direction, with fees prorated by quantity.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.importers.base import NormalizedFill
from app.models import Direction, Side, TradeStatus

ZERO = Decimal("0")


@dataclass
class FillPortion:
    """The part of a source fill attributed to one trade (fills can split)."""

    fill: NormalizedFill
    qty: Decimal
    fees: Decimal


@dataclass
class ComputedTrade:
    account_label: str
    symbol: str
    direction: Direction
    status: TradeStatus
    opened_at: datetime
    closed_at: datetime | None
    max_qty: Decimal
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None
    gross_pnl: Decimal
    net_pnl: Decimal
    total_fees: Decimal
    fill_count: int
    portions: list[FillPortion]

    @property
    def hold_time_seconds(self) -> int | None:
        if self.closed_at is None:
            return None
        return int((self.closed_at - self.opened_at).total_seconds())


@dataclass
class _OpenLot:
    qty: Decimal
    price: Decimal


@dataclass
class _TradeBuilder:
    account_label: str
    symbol: str
    direction: Direction
    opened_at: datetime
    position: Decimal = ZERO  # signed: positive long, negative short
    max_qty: Decimal = ZERO
    lots: deque[_OpenLot] = field(default_factory=deque)
    entry_qty: Decimal = ZERO
    entry_notional: Decimal = ZERO
    exit_qty: Decimal = ZERO
    exit_notional: Decimal = ZERO
    gross_pnl: Decimal = ZERO
    total_fees: Decimal = ZERO
    portions: list[FillPortion] = field(default_factory=list)
    last_time: datetime | None = None

    def add_entry(self, qty: Decimal, price: Decimal) -> None:
        self.lots.append(_OpenLot(qty=qty, price=price))
        self.entry_qty += qty
        self.entry_notional += qty * price
        signed = qty if self.direction is Direction.LONG else -qty
        self.position += signed
        self.max_qty = max(self.max_qty, abs(self.position))

    def add_exit(self, qty: Decimal, price: Decimal) -> None:
        """Match qty against open lots FIFO, realizing PnL."""
        remaining = qty
        while remaining > ZERO:
            lot = self.lots[0]
            matched = min(lot.qty, remaining)
            if self.direction is Direction.LONG:
                self.gross_pnl += (price - lot.price) * matched
            else:
                self.gross_pnl += (lot.price - price) * matched
            lot.qty -= matched
            if lot.qty == ZERO:
                self.lots.popleft()
            remaining -= matched
        self.exit_qty += qty
        self.exit_notional += qty * price
        signed = -qty if self.direction is Direction.LONG else qty
        self.position += signed

    def build(self) -> ComputedTrade:
        closed = self.position == ZERO
        return ComputedTrade(
            account_label=self.account_label,
            symbol=self.symbol,
            direction=self.direction,
            status=TradeStatus.CLOSED if closed else TradeStatus.OPEN,
            opened_at=self.opened_at,
            closed_at=self.last_time if closed else None,
            max_qty=self.max_qty,
            avg_entry_price=self.entry_notional / self.entry_qty,
            avg_exit_price=(self.exit_notional / self.exit_qty) if self.exit_qty else None,
            gross_pnl=self.gross_pnl,
            net_pnl=self.gross_pnl - self.total_fees,
            total_fees=self.total_fees,
            fill_count=len(self.portions),
            portions=self.portions,
        )


def group_fills(fills: list[NormalizedFill]) -> list[ComputedTrade]:
    """Group fills into trades across all (account, symbol) pairs.

    Result is ordered by trade open time (ties broken by input order).
    """
    by_key: dict[tuple[str, str], list[NormalizedFill]] = {}
    for f in sorted(fills, key=lambda f: f.executed_at):
        by_key.setdefault((f.account_label, f.symbol), []).append(f)

    trades: list[ComputedTrade] = []
    for (account, symbol), symbol_fills in by_key.items():
        trades.extend(_group_symbol(account, symbol, symbol_fills))
    trades.sort(key=lambda t: t.opened_at)
    return trades


def _group_symbol(
    account: str, symbol: str, fills: list[NormalizedFill]
) -> list[ComputedTrade]:
    trades: list[ComputedTrade] = []
    builder: _TradeBuilder | None = None

    for f in fills:
        qty = f.qty
        fees = f.fees

        if builder is None:
            builder = _open_trade(account, symbol, f, qty, fees)
            continue

        is_entry = (f.side is Side.BUY) == (builder.direction is Direction.LONG)
        if is_entry:
            builder.add_entry(qty, f.price)
            builder.portions.append(FillPortion(fill=f, qty=qty, fees=fees))
            builder.total_fees += fees
            builder.last_time = f.executed_at
        else:
            open_qty = abs(builder.position)
            closing_qty = min(qty, open_qty)
            crossing_qty = qty - closing_qty
            # Prorate fees if this fill both closes the trade and flips direction
            closing_fees = fees if crossing_qty == ZERO else fees * closing_qty / qty
            builder.add_exit(closing_qty, f.price)
            builder.portions.append(FillPortion(fill=f, qty=closing_qty, fees=closing_fees))
            builder.total_fees += closing_fees
            builder.last_time = f.executed_at
            if builder.position == ZERO:
                trades.append(builder.build())
                builder = None
            if crossing_qty > ZERO:
                builder = _open_trade(account, symbol, f, crossing_qty, fees - closing_fees)

    if builder is not None:
        trades.append(builder.build())
    return trades


def _open_trade(
    account: str, symbol: str, f: NormalizedFill, qty: Decimal, fees: Decimal
) -> _TradeBuilder:
    direction = Direction.LONG if f.side is Side.BUY else Direction.SHORT
    builder = _TradeBuilder(
        account_label=account, symbol=symbol, direction=direction, opened_at=f.executed_at
    )
    builder.add_entry(qty, f.price)
    builder.portions.append(FillPortion(fill=f, qty=qty, fees=fees))
    builder.total_fees += fees
    builder.last_time = f.executed_at
    return builder
