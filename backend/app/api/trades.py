"""Trades API: list with filters, detail, and annotation editing.

Date-range filters are half-open UTC calendar days: `from=2026-06-01` matches
trades opened at or after that day's midnight UTC, `to=2026-06-05` matches
trades opened strictly before the *next* midnight (i.e. `to` is inclusive).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.api.deps import RulesConfigDep, SessionDep
from app.ingest import audit_account
from app.models import Trade, TradeStatus
from app.schemas import TradeDetail, TradePage, TradeRead, TradeUpdate

router = APIRouter(prefix="/api/trades", tags=["trades"])


def _day_start_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _apply_filters(
    stmt: Select[tuple[Trade]],
    symbol: str | None,
    tag: str | None,
    status: TradeStatus | None,
    has_violations: bool | None,
    date_from: date | None,
    date_to: date | None,
) -> Select[tuple[Trade]]:
    if symbol is not None:
        stmt = stmt.where(Trade.symbol == symbol.upper())
    if tag is not None:
        stmt = stmt.where(Trade.setup_tag == tag)
    if status is not None:
        stmt = stmt.where(Trade.status == status)
    if has_violations is True:
        stmt = stmt.where(Trade.violations.any())
    elif has_violations is False:
        stmt = stmt.where(~Trade.violations.any())
    if date_from is not None:
        stmt = stmt.where(Trade.opened_at >= _day_start_utc(date_from))
    if date_to is not None:
        stmt = stmt.where(Trade.opened_at < _day_start_utc(date_to) + timedelta(days=1))
    return stmt


@router.get("")
def list_trades(
    session: SessionDep,
    symbol: str | None = None,
    tag: str | None = None,
    status: TradeStatus | None = None,
    has_violations: bool | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TradePage:
    stmt = _apply_filters(select(Trade), symbol, tag, status, has_violations, date_from, date_to)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    trades = session.scalars(
        stmt.options(selectinload(Trade.violations))
        .order_by(Trade.opened_at.desc(), Trade.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return TradePage(
        items=[TradeRead.model_validate(t) for t in trades],
        total=total,
        limit=limit,
        offset=offset,
    )


def _get_trade_or_404(session: SessionDep, trade_id: int) -> Trade:
    trade = session.get(
        Trade,
        trade_id,
        options=[selectinload(Trade.violations), selectinload(Trade.executions)],
    )
    if trade is None:
        raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")
    return trade


def _detail(trade: Trade) -> TradeDetail:
    detail = TradeDetail.model_validate(trade)
    detail.executions.sort(key=lambda e: (e.executed_at, e.id))
    return detail


@router.get("/{trade_id}")
def get_trade(session: SessionDep, trade_id: int) -> TradeDetail:
    return _detail(_get_trade_or_404(session, trade_id))


@router.patch("/{trade_id}")
def update_trade(
    session: SessionDep,
    rules_config: RulesConfigDep,
    trade_id: int,
    body: TradeUpdate,
) -> TradeDetail:
    trade = _get_trade_or_404(session, trade_id)

    changes = body.model_dump(include=body.model_fields_set)
    if "planned_stop" in changes:
        if changes["planned_stop"] is None:
            trade.stop_set_at = None
        elif trade.planned_stop is None:
            # First time a stop is recorded; later price edits keep the
            # original timestamp so stop_required(within_minutes) stays honest.
            trade.stop_set_at = datetime.now(UTC)
    for field, value in changes.items():
        setattr(trade, field, value)
    session.flush()

    # Annotations feed the rules (stop_required, max_risk_per_trade), so the
    # account is re-audited to keep stored violations consistent.
    if rules_config is not None:
        audit_account(session, trade.account_label, rules_config)
    session.flush()
    return _detail(trade)
