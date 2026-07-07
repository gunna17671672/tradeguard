"""Ingest layer: the thin DB boundary between pure importers/grouping and SQLite.

Imports are idempotent: fills dedup on a content hash, and trades for any
touched (account, symbol) pair are rebuilt from all stored fills so re-running
an import never duplicates or corrupts trades.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.grouping import group_fills
from app.importers.base import NormalizedFill, fill_dedup_hash
from app.models import Execution, ImportBatch, Trade


@dataclass(frozen=True)
class ImportResult:
    batch_id: int
    inserted: int
    skipped_duplicates: int
    trades_rebuilt: int


def import_fills(
    session: Session, fills: list[NormalizedFill], broker: str, filename: str
) -> ImportResult:
    """Persist new fills (skipping duplicates) and rebuild affected trades."""
    batch = ImportBatch(broker=broker, filename=filename, imported_at=datetime.now(UTC))
    session.add(batch)
    session.flush()

    existing_hashes = set(
        session.scalars(
            select(Execution.dedup_hash).where(
                Execution.dedup_hash.in_([fill_dedup_hash(f) for f in fills])
            )
        )
    )

    inserted = 0
    skipped = 0
    seen: set[str] = set()
    touched_keys: set[tuple[str, str]] = set()
    for f in fills:
        h = fill_dedup_hash(f)
        if h in existing_hashes or h in seen:
            skipped += 1
            continue
        seen.add(h)
        session.add(
            Execution(
                broker=f.broker,
                account_label=f.account_label,
                symbol=f.symbol,
                asset_type=f.asset_type,
                side=f.side,
                qty=f.qty,
                price=f.price,
                fees=f.fees,
                executed_at=f.executed_at,
                raw_row_json=json.dumps(f.raw_row, sort_keys=True),
                dedup_hash=h,
                import_batch_id=batch.id,
            )
        )
        inserted += 1
        touched_keys.add((f.account_label, f.symbol))

    batch.inserted_count = inserted
    batch.skipped_count = skipped
    session.flush()

    trades_rebuilt = 0
    for account, symbol in sorted(touched_keys):
        trades_rebuilt += rebuild_trades(session, account, symbol)

    return ImportResult(
        batch_id=batch.id,
        inserted=inserted,
        skipped_duplicates=skipped,
        trades_rebuilt=trades_rebuilt,
    )


def rebuild_trades(session: Session, account_label: str, symbol: str) -> int:
    """Delete and regroup all trades for one (account, symbol) from stored fills."""
    executions = list(
        session.scalars(
            select(Execution)
            .where(Execution.account_label == account_label, Execution.symbol == symbol)
            .order_by(Execution.executed_at, Execution.id)
        )
    )
    for execution in executions:
        execution.trade_id = None
    session.flush()
    for trade in session.scalars(
        select(Trade).where(Trade.account_label == account_label, Trade.symbol == symbol)
    ):
        session.delete(trade)
    session.flush()

    by_hash = {e.dedup_hash: e for e in executions}
    fills = [
        NormalizedFill(
            broker=e.broker,
            symbol=e.symbol,
            side=e.side,
            qty=e.qty,
            price=e.price,
            fees=e.fees,
            executed_at=e.executed_at,
            account_label=e.account_label,
            asset_type=e.asset_type,
            raw_row={"dedup_hash": e.dedup_hash},
        )
        for e in executions
    ]

    computed = group_fills(fills)
    for ct in computed:
        trade = Trade(
            account_label=ct.account_label,
            symbol=ct.symbol,
            direction=ct.direction,
            status=ct.status,
            opened_at=ct.opened_at,
            closed_at=ct.closed_at,
            max_qty=ct.max_qty,
            avg_entry_price=ct.avg_entry_price,
            avg_exit_price=ct.avg_exit_price,
            gross_pnl=ct.gross_pnl,
            net_pnl=ct.net_pnl,
            total_fees=ct.total_fees,
            hold_time_seconds=ct.hold_time_seconds,
            fill_count=ct.fill_count,
        )
        session.add(trade)
        session.flush()
        # A fill that flips direction belongs to two trades; the single FK
        # ends up on the later (opened) trade. fill_count on each trade still
        # counts its portion of the split fill.
        for portion in ct.portions:
            by_hash[portion.fill.raw_row["dedup_hash"]].trade_id = trade.id
    session.flush()
    return len(computed)
