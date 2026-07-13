"""Reports API: weekly discipline report."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app.api.deps import RequiredRulesConfigDep, SessionDep
from app.reports import fetch_weekly_report
from app.schemas import WeeklyReportRead

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/weekly")
def weekly(
    session: SessionDep,
    rules_config: RequiredRulesConfigDep,
    week: Annotated[
        date | None, Query(description="Any date inside the wanted Mon-Sun week")
    ] = None,
) -> WeeklyReportRead:
    settings = rules_config.settings
    if week is None:
        week = datetime.now(ZoneInfo(settings.timezone)).date()
    return WeeklyReportRead.model_validate(fetch_weekly_report(session, week, settings))
