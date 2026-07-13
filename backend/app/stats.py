"""Performance stats: summary numbers, equity curve, PnL calendar.

Pure computations over closed trades, plus one thin DB fetch at the bottom.
Open trades are excluded everywhere (SPEC: positions not yet back to 0 are
excluded from most stats). Money stays Decimal end to end; percentages are
quantized to one decimal place, ratios to two.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Trade, TradeStatus
from app.rules.engine import session_date

ZERO = Decimal("0")
PCT_PLACES = Decimal("0.1")
RATIO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class StatsSummary:
    closed_trades: int
    wins: int
    losses: int
    scratches: int  # closed at exactly 0 net PnL
    win_rate_pct: Decimal | None  # None when there are no closed trades
    profit_factor: Decimal | None  # None when there are no losing trades
    avg_win: Decimal | None
    avg_loss: Decimal | None  # negative number (average losing PnL)
    expectancy: Decimal | None  # average net PnL per closed trade
    gross_pnl: Decimal
    net_pnl: Decimal
    total_fees: Decimal


def summarize(closed_trades: list[Trade]) -> StatsSummary:
    wins = [t for t in closed_trades if t.net_pnl > ZERO]
    losses = [t for t in closed_trades if t.net_pnl < ZERO]
    n = len(closed_trades)

    gross_wins = sum((t.net_pnl for t in wins), ZERO)
    gross_losses = sum((t.net_pnl for t in losses), ZERO)  # negative
    net_pnl = sum((t.net_pnl for t in closed_trades), ZERO)

    return StatsSummary(
        closed_trades=n,
        wins=len(wins),
        losses=len(losses),
        scratches=n - len(wins) - len(losses),
        win_rate_pct=None if n == 0 else (Decimal(len(wins)) * 100 / n).quantize(PCT_PLACES),
        profit_factor=None if not losses else (gross_wins / -gross_losses).quantize(RATIO_PLACES),
        avg_win=None if not wins else gross_wins / len(wins),
        avg_loss=None if not losses else gross_losses / len(losses),
        expectancy=None if n == 0 else net_pnl / n,
        gross_pnl=sum((t.gross_pnl for t in closed_trades), ZERO),
        net_pnl=net_pnl,
        total_fees=sum((t.total_fees for t in closed_trades), ZERO),
    )


@dataclass(frozen=True)
class EquityPoint:
    trade_id: int
    closed_at: datetime
    net_pnl: Decimal
    cumulative_pnl: Decimal


def equity_curve(closed_trades: list[Trade]) -> list[EquityPoint]:
    """Cumulative net PnL, one point per closed trade in close order."""
    points: list[EquityPoint] = []
    running = ZERO
    for t in sorted(closed_trades, key=lambda t: (t.closed_at, t.id or 0)):
        running += t.net_pnl
        points.append(
            EquityPoint(
                trade_id=t.id, closed_at=t.closed_at, net_pnl=t.net_pnl, cumulative_pnl=running
            )
        )
    return points


@dataclass(frozen=True)
class CalendarDay:
    day: date
    net_pnl: Decimal
    trade_count: int


def pnl_calendar(closed_trades: list[Trade], tz: ZoneInfo) -> list[CalendarDay]:
    """Net PnL per session day (close date in the account timezone), ascending."""
    by_day: dict[date, list[Trade]] = {}
    for t in closed_trades:
        by_day.setdefault(session_date(t.closed_at, tz), []).append(t)
    return [
        CalendarDay(
            day=day,
            net_pnl=sum((t.net_pnl for t in by_day[day]), ZERO),
            trade_count=len(by_day[day]),
        )
        for day in sorted(by_day)
    ]


def fetch_closed_trades(
    session: Session,
    account_label: str = "default",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[Trade]:
    """Thin DB layer: closed trades for one account, optionally bounded by close time."""
    stmt = (
        select(Trade)
        .where(Trade.account_label == account_label, Trade.status == TradeStatus.CLOSED)
        .order_by(Trade.closed_at, Trade.id)
    )
    if date_from is not None:
        stmt = stmt.where(Trade.closed_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Trade.closed_at < date_to)
    return list(session.scalars(stmt))
