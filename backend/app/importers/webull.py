"""Webull CSV importer (US stocks).

Targets the standard Webull app "Orders" export. Column names vary by app
version, so the expected names live in one mapping and any mismatch fails
loudly, listing found vs. expected columns; the generic importer with a custom
mapping is the fallback for other variants.

Webull timestamps are US Eastern (e.g. "07/01/2026 09:31:05 EDT"); they are
converted to UTC. The export carries no fee column, so fees are 0.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.importers.base import (
    BaseImporter,
    ColumnMapping,
    ImporterError,
    NormalizedFill,
    check_columns,
    parse_decimal,
    parse_side,
    read_csv_rows,
)

NY = ZoneInfo("America/New_York")

WEBULL_MAPPING = ColumnMapping(
    symbol="Symbol",
    side="Side",
    qty="Filled",
    price="Avg Price",
    executed_at="Filled Time",
)

STATUS_COLUMN = "Status"
FILLED_STATUSES = {"filled", "partial filled", "partially filled"}

_TIME_FORMATS = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M")


def _parse_webull_time(raw: str, row_num: int) -> datetime:
    # Strip a trailing zone token like "EDT"/"EST"; Webull times are Eastern.
    parts = raw.strip().rsplit(" ", 1)
    candidate = parts[0] if len(parts) == 2 and parts[1].isalpha() else raw.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).replace(tzinfo=NY)
        except ValueError:
            continue
    raise ImporterError(
        f"row {row_num}: cannot parse Filled Time {raw!r} (expected e.g. '07/01/2026 09:31:05 EDT')"
    )


class WebullImporter(BaseImporter):
    broker = "webull"

    def parse(self, path: Path | str) -> list[NormalizedFill]:
        path = Path(path)
        header, rows = read_csv_rows(path)
        check_columns(header, WEBULL_MAPPING, path.name)

        fills: list[NormalizedFill] = []
        for i, row in enumerate(rows, start=2):  # 1-based + header row
            status = row.get(STATUS_COLUMN, "").strip().lower()
            if STATUS_COLUMN in header and status not in FILLED_STATUSES:
                continue
            qty = parse_decimal(row[WEBULL_MAPPING.qty], "Filled", i)
            if qty == 0:
                continue
            fills.append(
                NormalizedFill(
                    broker=self.broker,
                    symbol=row[WEBULL_MAPPING.symbol],
                    side=parse_side(row[WEBULL_MAPPING.side], i),
                    qty=qty,
                    price=parse_decimal(row[WEBULL_MAPPING.price], "Avg Price", i),
                    fees=parse_decimal("0", "fees", i),
                    executed_at=_parse_webull_time(row[WEBULL_MAPPING.executed_at], i),
                    raw_row=dict(row),
                )
            )
        if not fills:
            raise ImporterError(
                f"{path.name}: no filled executions found "
                f"(rows present but none with status in {sorted(FILLED_STATUSES)})"
            )
        return fills
