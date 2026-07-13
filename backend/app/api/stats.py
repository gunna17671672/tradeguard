"""Stats API: summary numbers, equity curve, PnL calendar.

`from`/`to` are UTC calendar days bounding *close* time, `to` inclusive —
the same convention as the trades list, which bounds open time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app.api.deps import RulesConfigDep, SessionDep
from app.schemas import CalendarDayRead, EquityPointRead, StatsSummaryRead
from app.stats import equity_curve, fetch_closed_trades, pnl_calendar, summarize

router = APIRouter(prefix="/api/stats", tags=["stats"])

DateFrom = Annotated[date | None, Query(alias="from")]
DateTo = Annotated[date | None, Query(alias="to")]


def _bounds(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    start = None if date_from is None else datetime.combine(date_from, time.min, tzinfo=UTC)
    end = (
        None
        if date_to is None
        else datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
    )
    return start, end


@router.get("/summary")
def summary(
    session: SessionDep, date_from: DateFrom = None, date_to: DateTo = None
) -> StatsSummaryRead:
    start, end = _bounds(date_from, date_to)
    trades = fetch_closed_trades(session, date_from=start, date_to=end)
    return StatsSummaryRead.model_validate(summarize(trades))


@router.get("/equity")
def equity(session: SessionDep) -> list[EquityPointRead]:
    points = equity_curve(fetch_closed_trades(session))
    return [EquityPointRead.model_validate(p) for p in points]


@router.get("/calendar")
def calendar(session: SessionDep, rules_config: RulesConfigDep) -> list[CalendarDayRead]:
    tz = ZoneInfo(rules_config.settings.timezone if rules_config else "America/New_York")
    days = pnl_calendar(fetch_closed_trades(session), tz)
    return [CalendarDayRead.model_validate(d) for d in days]
