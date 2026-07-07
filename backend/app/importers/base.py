"""Importer contract: pure, DB-free parsing of broker files into normalized fills.

Importers are mapping-driven (logical field -> CSV column name) so a new broker
is mostly configuration. They never touch the database; persistence and dedup
live in the ingest layer.
"""

from __future__ import annotations

import csv
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.models import AssetType, Side


class ImporterError(Exception):
    """Raised when a file cannot be parsed; message must say why, loudly."""


@dataclass(frozen=True)
class NormalizedFill:
    broker: str
    symbol: str
    side: Side
    qty: Decimal
    price: Decimal
    fees: Decimal
    executed_at: datetime  # timezone-aware UTC
    account_label: str = "default"
    asset_type: AssetType = AssetType.STOCK
    raw_row: dict[str, str] = field(default_factory=dict)


def fill_dedup_hash(fill: NormalizedFill) -> str:
    """Stable hash for idempotent imports: same fill in a re-imported file dedups."""
    key = "|".join(
        [
            fill.broker,
            fill.symbol,
            fill.executed_at.astimezone(UTC).isoformat(),
            fill.side.value,
            str(fill.qty),
            str(fill.price),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass(frozen=True)
class ColumnMapping:
    """Logical field -> CSV column name. Optional fields may be None."""

    symbol: str
    side: str
    qty: str
    price: str
    executed_at: str
    fees: str | None = None
    account_label: str | None = None

    def required_columns(self) -> list[str]:
        return [self.symbol, self.side, self.qty, self.price, self.executed_at]

    def all_columns(self) -> list[str]:
        optional = [c for c in (self.fees, self.account_label) if c]
        return self.required_columns() + optional


def read_csv_rows(path: Path | str) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV into (header, rows). Fails loudly on empty or headerless files."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ImporterError(f"{path.name}: file is empty or has no header row")
        header = [h.strip() for h in reader.fieldnames]
        rows = [
            {
                (k.strip() if k else k): (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
            }
            for row in reader
        ]
    if not rows:
        raise ImporterError(f"{path.name}: header found but no data rows")
    return header, rows


def check_columns(header: list[str], mapping: ColumnMapping, filename: str) -> None:
    missing = [c for c in mapping.all_columns() if c not in header]
    if missing:
        raise ImporterError(
            f"{filename}: missing expected column(s) {missing}. "
            f"Expected {mapping.all_columns()}, found {header}. "
            "If your broker export uses different column names, use the generic "
            "importer with a custom mapping."
        )


def parse_decimal(raw: str, field_name: str, row_num: int) -> Decimal:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ImporterError(f"row {row_num}: cannot parse {field_name} value {raw!r}") from exc


def parse_side(raw: str, row_num: int) -> Side:
    normalized = raw.strip().lower()
    if normalized in ("buy", "b", "bot", "bought"):
        return Side.BUY
    if normalized in ("sell", "s", "sld", "sold", "sell short", "short"):
        return Side.SELL
    raise ImporterError(f"row {row_num}: unrecognized side value {raw!r}")


class BaseImporter(ABC):
    broker: str

    @abstractmethod
    def parse(self, path: Path | str) -> list[NormalizedFill]:
        """Parse a broker export file into normalized fills. Pure; no DB access."""
