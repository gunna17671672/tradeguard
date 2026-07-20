"""The bundled sample dataset: loader + annotations for sample_data/.

The CSV (a synthetic two-week Webull order-history export, July 6–17 2026) is
engineered against the shipped rules.example.yaml defaults so a fresh install
sees every built-in rule fire at least once — one revenge trade, one
seventh-trade-of-the-day, one blocked-window entry, one oversized planned
risk, one entry after the daily-loss breach, and three stop_required hits
(two missing stops, one set late) — without drowning the dashboard.

Annotations (stops, targets, setup tags, notes) are applied straight to the
DB with *historical* stop_set_at timestamps: the API's PATCH stamps "now" as
the moment the stop was recorded, which would mark every stop on these past
trades as late. The audit runs once, after annotation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.importers.webull import WebullImporter
from app.ingest import ImportResult, audit_account, import_fills
from app.models import Trade
from app.rules.loader import RulesConfig

SAMPLE_RELPATH = Path("sample_data") / "webull_orders_two_weeks.csv"
_ET = ZoneInfo("America/New_York")
_YEAR = 2026


def find_sample_file(start: Path | None = None) -> Path | None:
    """Walk up from `start`/cwd for the bundled sample CSV (repo root holds it)."""
    origin = (start or Path.cwd()).resolve()
    for directory in (origin, *origin.parents):
        candidate = directory / SAMPLE_RELPATH
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class _Annotation:
    """One trade's user annotations, keyed by its entry time (ET wall clock)."""

    symbol: str
    opened_et: str  # "MM/DD HH:MM:SS" in America/New_York, year 2026
    stop: str | None
    target: str | None = None
    tag: str | None = None
    note: str | None = None
    stop_delay_min: int = 2  # minutes after entry the stop was recorded

    def opened_at_utc(self) -> datetime:
        local = datetime.strptime(f"{_YEAR}/{self.opened_et}", "%Y/%m/%d %H:%M:%S")
        return local.replace(tzinfo=_ET).astimezone(UTC)


_A = _Annotation

# One entry per round trip in the CSV. The two stop=None trades and the
# stop_delay_min=12 trade are stop_required's three hits; every other stop is
# recorded within the template's 5-minute limit.
ANNOTATIONS: tuple[_Annotation, ...] = (
    _A("AAPL", "07/06 09:41:12", "203.80", "206.30", "orb-pullback"),
    _A("SPY", "07/06 11:05:33", "621.80", "624.60", "vwap-reclaim"),
    _A("NVDA", "07/06 13:20:45", "153.60", "155.40", "breakout"),
    _A("TSLA", "07/07 09:52:21", None, None, "gap-fill"),
    _A("AMD", "07/07 12:10:02", "157.90", "159.60", "vwap-reclaim"),
    _A("AAPL", "07/08 09:46:05", "204.60", "206.10", "orb-pullback"),
    _A("NVDA", "07/08 10:02:19", "154.50", "156.00", "breakout"),
    _A(
        "NVDA",
        "07/08 10:29:52",
        "153.95",
        "155.90",
        "breakout",
        note="chased it right back after the stop-out at double size. worked, still dumb.",
    ),
    _A("SPY", "07/08 11:15:26", "625.20", "623.10", "range-fade"),
    _A("META", "07/08 12:30:15", "699.50", "707.00", "breakout"),
    _A("AMD", "07/08 13:45:33", "158.50", "160.00", "vwap-reclaim"),
    _A(
        "AAPL",
        "07/08 14:30:27",
        "205.60",
        "207.00",
        "range-fade",
        note="seventh trade of the day — way past my own limit, should have stopped after six.",
    ),
    _A("MSFT", "07/09 10:05:48", "497.40", "502.00", "breakout"),
    _A("PLTR", "07/09 13:30:11", "147.90", "150.60", "orb-pullback"),
    _A("SPY", "07/10 09:32:10", "625.30", "627.70", "orb-pullback"),
    _A("NVDA", "07/10 11:10:14", "152.70", "158.90", "breakout"),
    _A("AAPL", "07/13 09:47:18", "206.50", "208.60", "orb-pullback"),
    _A("TSLA", "07/13 12:20:31", "253.10", "249.80", "range-fade"),
    _A("NVDA", "07/14 10:15:24", "156.20", "158.00", "breakout"),
    _A("META", "07/14 13:05:17", "695.00", "704.00", "vwap-reclaim", stop_delay_min=12),
    _A(
        "TSLA",
        "07/15 09:50:36",
        "248.90",
        "251.30",
        "gap-fill",
        note="news gapped it through my stop; ate the whole move.",
    ),
    _A("AMD", "07/15 11:20:48", "159.60", "162.00", "breakout"),
    _A("NVDA", "07/15 13:10:53", "156.50", "158.30", "vwap-reclaim"),
    _A(
        "AAPL",
        "07/15 14:20:44",
        "206.00",
        "207.30",
        "range-fade",
        note="already down big for the day — had no business taking this one.",
    ),
    _A("MSFT", "07/16 10:10:31", None, None, "breakout"),
    _A("PLTR", "07/16 13:20:22", "152.30", "149.90", "range-fade"),
    _A("AAPL", "07/17 09:58:03", "207.60", "209.80", "orb-pullback"),
    _A("SPY", "07/17 12:45:51", "627.70", "629.90", "vwap-reclaim"),
)


@dataclass(frozen=True)
class SampleResult:
    imported: ImportResult
    trades: int
    annotated: int
    violations_recorded: int


def load_sample(session: Session, csv_path: Path, rules_config: RulesConfig | None) -> SampleResult:
    """Import the sample CSV, annotate its trades, and audit — idempotently.

    Re-running dedups every fill and simply re-applies the same annotations.
    """
    fills = WebullImporter().parse(csv_path)  # sample times carry EDT/EST suffixes
    imported = import_fills(
        session, fills, broker="webull", filename=csv_path.name, rules_config=None
    )

    trades = list(session.scalars(select(Trade)))
    by_key = {(t.symbol, t.opened_at): t for t in trades}
    annotated = 0
    for spec in ANNOTATIONS:
        trade = by_key.get((spec.symbol, spec.opened_at_utc()))
        if trade is None:
            raise RuntimeError(
                f"sample annotation matches no trade: {spec.symbol} @ {spec.opened_et} ET "
                "(the CSV and ANNOTATIONS table are out of sync)"
            )
        trade.planned_stop = None if spec.stop is None else Decimal(spec.stop)
        trade.planned_target = None if spec.target is None else Decimal(spec.target)
        trade.setup_tag = spec.tag
        trade.notes = spec.note
        trade.stop_set_at = (
            None if spec.stop is None else trade.opened_at + timedelta(minutes=spec.stop_delay_min)
        )
        annotated += 1
    session.flush()

    violations = 0
    if rules_config is not None:
        for account in sorted({t.account_label for t in trades}):
            violations += audit_account(session, account, rules_config)

    total = session.scalar(select(func.count()).select_from(Trade)) or 0
    return SampleResult(
        imported=imported, trades=total, annotated=annotated, violations_recorded=violations
    )
