"""Generic CSV importer: user supplies the column mapping.

Fallback for brokers without a dedicated importer. The mapping names the CSV
columns for each logical field; timestamps default to ISO-8601 in UTC but both
the strptime format and source timezone are configurable.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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

DEFAULT_MAPPING = ColumnMapping(
    symbol="symbol",
    side="side",
    qty="qty",
    price="price",
    executed_at="executed_at",
    fees="fees",
)


class GenericCsvImporter(BaseImporter):
    broker = "generic"

    def __init__(
        self,
        mapping: ColumnMapping = DEFAULT_MAPPING,
        datetime_format: str | None = None,
        timezone: str = "UTC",
        broker_label: str = "generic",
    ) -> None:
        self.mapping = mapping
        self.datetime_format = datetime_format
        self.tz = ZoneInfo(timezone)
        self.broker = broker_label

    def _parse_time(self, raw: str, row_num: int) -> datetime:
        raw = raw.strip()
        try:
            if self.datetime_format:
                dt = datetime.strptime(raw, self.datetime_format)
            else:
                dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            expected = self.datetime_format or "ISO-8601"
            raise ImporterError(
                f"row {row_num}: cannot parse executed_at {raw!r} (expected {expected})"
            ) from exc
        return dt.replace(tzinfo=self.tz) if dt.tzinfo is None else dt

    def parse(self, path: Path | str) -> list[NormalizedFill]:
        path = Path(path)
        header, rows = read_csv_rows(path)
        check_columns(header, self.mapping, path.name)

        m = self.mapping
        fills: list[NormalizedFill] = []
        for i, row in enumerate(rows, start=2):
            fees = (
                parse_decimal(row[m.fees], "fees", i)
                if m.fees and row.get(m.fees, "") != ""
                else Decimal("0")
            )
            fills.append(
                NormalizedFill(
                    broker=self.broker,
                    symbol=row[m.symbol],
                    side=parse_side(row[m.side], i),
                    qty=parse_decimal(row[m.qty], "qty", i),
                    price=parse_decimal(row[m.price], "price", i),
                    fees=fees,
                    executed_at=self._parse_time(row[m.executed_at], i),
                    account_label=row[m.account_label] if m.account_label else "default",
                    raw_row=dict(row),
                )
            )
        return fills
