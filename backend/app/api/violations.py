"""Violations feed: rule findings joined with their trades, newest first."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.deps import SessionDep
from app.models import Severity, Trade, Violation
from app.schemas import ViolationFeedItem, ViolationPage

router = APIRouter(prefix="/api/violations", tags=["violations"])


@router.get("")
def list_violations(
    session: SessionDep,
    rule_id: str | None = None,
    severity: Severity | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ViolationPage:
    stmt = select(Violation).join(Violation.trade)
    if rule_id is not None:
        stmt = stmt.where(Violation.rule_id == rule_id)
    if severity is not None:
        stmt = stmt.where(Violation.severity == severity)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    violations = session.scalars(
        stmt.options(joinedload(Violation.trade))
        .order_by(Trade.opened_at.desc(), Violation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        ViolationFeedItem(
            id=v.id,
            trade_id=v.trade_id,
            rule_id=v.rule_id,
            severity=v.severity,
            message=v.message,
            symbol=v.trade.symbol,
            opened_at=v.trade.opened_at,
            closed_at=v.trade.closed_at,
            net_pnl=v.trade.net_pnl,
        )
        for v in violations
    ]
    return ViolationPage(items=items, total=total, limit=limit, offset=offset)
