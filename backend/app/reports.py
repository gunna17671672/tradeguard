"""Adherence score and weekly discipline report data.

Pure computations over trades (with their violations loaded), plus one thin
DB fetch at the bottom. Definitions:

- A closed trade is *clean* when it has no violations at severity
  `violation`; warn/info findings are advisory and do not hurt adherence.
- Adherence score: % of closed trades that are clean (per week in the report).
- Streak: consecutive most-recent session days that had closed trades, all of
  them clean. A day with any violation resets the streak to 0; days without
  closed trades neither count nor break it.
- Weeks run Monday–Sunday; a trade belongs to the week of its close, evaluated
  as a session date in the account timezone.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Severity, Trade, TradeStatus
from app.rules.engine import AccountSettings, session_date

ZERO = Decimal("0")
PCT_PLACES = Decimal("0.1")


def is_clean(trade: Trade) -> bool:
    return all(v.severity is not Severity.VIOLATION for v in trade.violations)


def adherence_score(closed_trades: Sequence[Trade]) -> Decimal | None:
    """% of closed trades with zero violations; None when there are no trades."""
    if not closed_trades:
        return None
    clean = sum(1 for t in closed_trades if is_clean(t))
    return (Decimal(clean) * 100 / Decimal(len(closed_trades))).quantize(PCT_PLACES)


def violation_free_streak_days(closed_trades: Iterable[Trade], tz: ZoneInfo) -> int:
    """Current streak: consecutive latest trading days whose trades are all clean."""
    clean_by_day: dict[date, bool] = {}
    for t in closed_trades:
        day = session_date(t.closed_at, tz)
        clean_by_day[day] = clean_by_day.get(day, True) and is_clean(t)
    streak = 0
    for day in sorted(clean_by_day, reverse=True):
        if not clean_by_day[day]:
            break
        streak += 1
    return streak


def week_bounds(day: date) -> tuple[date, date]:
    """Monday..Sunday of the week containing `day`."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


@dataclass(frozen=True)
class WeeklyReport:
    week_start: date
    week_end: date
    closed_trades: int
    wins: int
    losses: int
    gross_pnl: Decimal
    net_pnl: Decimal
    total_fees: Decimal
    adherence_pct: Decimal | None  # None when the week had no closed trades
    violation_count: int
    violations_by_rule: dict[str, int]
    streak_days: int  # current streak over all history, not just this week


def build_weekly_report(
    trades: Sequence[Trade], week_of: date, settings: AccountSettings
) -> WeeklyReport:
    """Weekly discipline summary from one account's trades (violations loaded)."""
    tz = ZoneInfo(settings.timezone)
    week_start, week_end = week_bounds(week_of)
    all_closed = [t for t in trades if t.status is TradeStatus.CLOSED]
    in_week = [t for t in all_closed if week_start <= session_date(t.closed_at, tz) <= week_end]

    by_rule = Counter(v.rule_id for t in in_week for v in t.violations)
    return WeeklyReport(
        week_start=week_start,
        week_end=week_end,
        closed_trades=len(in_week),
        wins=sum(1 for t in in_week if t.net_pnl > ZERO),
        losses=sum(1 for t in in_week if t.net_pnl < ZERO),
        gross_pnl=sum((t.gross_pnl for t in in_week), ZERO),
        net_pnl=sum((t.net_pnl for t in in_week), ZERO),
        total_fees=sum((t.total_fees for t in in_week), ZERO),
        adherence_pct=adherence_score(in_week),
        violation_count=sum(by_rule.values()),
        violations_by_rule=dict(by_rule),
        streak_days=violation_free_streak_days(all_closed, tz),
    )


def fetch_weekly_report(
    session: Session, week_of: date, settings: AccountSettings, account_label: str = "default"
) -> WeeklyReport:
    """Thin DB layer: load one account's trades and build the weekly report."""
    trades = session.scalars(
        select(Trade)
        .where(Trade.account_label == account_label)
        .options(selectinload(Trade.violations))
        .order_by(Trade.opened_at, Trade.id)
    ).all()
    return build_weekly_report(trades, week_of, settings)
