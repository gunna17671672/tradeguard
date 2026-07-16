"""Webull CSV importer (US stocks).

Supports the two known Webull app export layouts, detected from the header:

- "fills" variant: Symbol, Side, Filled, Avg Price, Filled Time
- "orders" variant (order history): Symbol, Side, Qty, Filled Qty,
  Avg Fill Price, Status, Update Time, commission, fee, ... (plus junk
  columns like a literal 'undefined' header, which are ignored)

Rows are orders, not pure fills: only rows whose Status indicates a fill are
imported, using the filled quantity (a partially filled order has
Qty > Filled Qty). Skipped unfilled rows are counted on `skipped_unfilled`.
Any other header fails loudly, listing both expected layouts; the generic
importer with a custom mapping is the fallback.

Webull renders timestamps in two styles, tried in order:

- "07/01/2026 09:31:05 EDT" — zone-abbreviation suffix (stripped; EDT vs EST
  is resolved from the date)
- "2026-07-14 14:36:05" — no zone suffix at all

Either way the wall-clock time is in the timezone of the device that made the
export — Webull writes device-local times, not Eastern. `WebullImporter(
timezone=...)` names that zone and defaults to America/New_York (market time);
times are converted to UTC for storage. The fills variant carries no fee
columns, so fees are 0; the orders variant sums its commission and fee columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from app.importers.base import (
    BaseImporter,
    ColumnMapping,
    ImporterError,
    NormalizedFill,
    parse_decimal,
    parse_side,
    read_csv_rows,
)

# Assumed when no timezone override is given. Webull actually writes the
# exporting device's local time, so non-Eastern traders must override this.
WEBULL_DISPLAY_TIMEZONE = "America/New_York"

STATUS_COLUMN = "Status"
FILLED_STATUSES = {"filled", "partial filled", "partially filled"}


@dataclass(frozen=True)
class _Variant:
    name: str
    mapping: ColumnMapping
    fee_columns: tuple[str, ...] = ()
    requires_status: bool = False

    def required_columns(self) -> list[str]:
        required = self.mapping.required_columns()
        return required + [STATUS_COLUMN] if self.requires_status else required


_VARIANTS: tuple[_Variant, ...] = (
    _Variant(
        name="fills export",
        mapping=ColumnMapping(
            symbol="Symbol",
            side="Side",
            qty="Filled",
            price="Avg Price",
            executed_at="Filled Time",
        ),
    ),
    _Variant(
        name="order-history export",
        mapping=ColumnMapping(
            symbol="Symbol",
            side="Side",
            qty="Filled Qty",
            price="Avg Fill Price",
            executed_at="Update Time",
        ),
        fee_columns=("commission", "fee"),
        requires_status=True,
    ),
)

# Known Webull timestamp layouts, tried in order (any trailing zone
# abbreviation like "EDT" is stripped before matching).
_TIME_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def _detect_variant(header: list[str], filename: str) -> _Variant:
    for variant in _VARIANTS:
        if all(column in header for column in variant.required_columns()):
            return variant
    expected = " or ".join(
        f"{variant.required_columns()} ({variant.name})" for variant in _VARIANTS
    )
    raise ImporterError(
        f"{filename}: columns do not match a known Webull export. "
        f"Expected {expected}; found {header}. "
        "If your broker export uses different column names, use the generic "
        "importer with a custom mapping."
    )


def _parse_webull_time(raw: str, column: str, row_num: int, tz: ZoneInfo) -> datetime:
    # Strip a trailing zone token like "EDT"/"EST"; the wall-clock time is
    # localized in `tz` either way (EDT vs EST falls out of the date).
    parts = raw.strip().rsplit(" ", 1)
    candidate = parts[0] if len(parts) == 2 and parts[1].isalpha() else raw.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ImporterError(
        f"row {row_num}: cannot parse {column} {raw!r} "
        "(expected e.g. '07/01/2026 09:31:05 EDT' or '2026-07-14 14:36:05')"
    )


def _parse_fees(row: dict[str, str], columns: tuple[str, ...], row_num: int) -> Decimal:
    total = Decimal("0")
    for column in columns:
        raw = row.get(column)
        if raw:  # missing or empty fee cells mean no fee
            total += parse_decimal(raw, column, row_num)
    return total


class WebullImporter(BaseImporter):
    broker = "webull"

    def __init__(self, timezone: str = WEBULL_DISPLAY_TIMEZONE) -> None:
        """`timezone`: the IANA zone the export's timestamps are written in.

        Webull writes the exporting device's local time, so this defaults to
        America/New_York (market time) but must be overridden for exports
        made elsewhere. It applies to zone-less timestamps
        ('2026-07-14 14:36:05') and to the abbreviated-suffix style
        ('07/01/2026 09:31:05 EDT'), where DST is resolved from the date
        rather than the suffix.
        """
        self.timezone = ZoneInfo(timezone)

    def parse(self, path: Path | str) -> list[NormalizedFill]:
        path = Path(path)
        header, rows = read_csv_rows(path)
        variant = _detect_variant(header, path.name)
        mapping = variant.mapping
        has_status = STATUS_COLUMN in header

        self.skipped_unfilled = 0
        fills: list[NormalizedFill] = []
        for i, row in enumerate(rows, start=2):  # 1-based + header row
            status = (row.get(STATUS_COLUMN) or "").strip().lower()
            if has_status and status not in FILLED_STATUSES:
                self.skipped_unfilled += 1
                continue
            qty = parse_decimal(row[mapping.qty], mapping.qty, i)
            if qty == 0:
                self.skipped_unfilled += 1
                continue
            fills.append(
                NormalizedFill(
                    broker=self.broker,
                    symbol=row[mapping.symbol],
                    side=parse_side(row[mapping.side], i),
                    qty=qty,
                    price=parse_decimal(row[mapping.price], mapping.price, i),
                    fees=_parse_fees(row, variant.fee_columns, i),
                    executed_at=_parse_webull_time(
                        row[mapping.executed_at], mapping.executed_at, i, self.timezone
                    ),
                    # Junk headers (e.g. a literal 'undefined' column) are kept
                    # as-is; only nameless overflow cells are dropped.
                    raw_row={k: v if isinstance(v, str) else "" for k, v in row.items() if k},
                )
            )
        if not fills:
            raise ImporterError(
                f"{path.name}: no filled executions found "
                f"(rows present but none with status in {sorted(FILLED_STATUSES)})"
            )
        return fills
