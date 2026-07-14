"""Importer tests: Webull mapping, generic mapping, loud failures."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.importers import available_brokers, get_importer
from app.importers.base import ColumnMapping, ImporterError, fill_dedup_hash
from app.importers.generic import GenericCsvImporter
from app.importers.webull import WebullImporter
from app.models import Side

D = Decimal


class TestWebullImporter:
    def test_parses_filled_rows_only(self, fixtures_dir: Path):
        importer = WebullImporter()
        fills = importer.parse(fixtures_dir / "webull_sample.csv")
        assert len(fills) == 4  # cancelled row skipped
        assert importer.skipped_unfilled == 1
        assert all(f.broker == "webull" for f in fills)

    def test_values_are_decimal_and_utc(self, fixtures_dir: Path):
        first = WebullImporter().parse(fixtures_dir / "webull_sample.csv")[0]
        assert first.symbol == "AAPL"
        assert first.side is Side.BUY
        assert isinstance(first.qty, Decimal) and first.qty == D("100")
        assert isinstance(first.price, Decimal) and first.price == D("190.00")
        # 09:31:05 EDT == 13:31:05 UTC
        assert first.executed_at.astimezone(UTC) == datetime(2026, 6, 1, 13, 31, 5, tzinfo=UTC)

    def test_missing_columns_fail_loudly(self, tmp_path: Path):
        bad = tmp_path / "bad.csv"
        bad.write_text("Ticker,Action,Shares\nAAPL,Buy,100\n", encoding="utf-8")
        with pytest.raises(ImporterError) as exc_info:
            WebullImporter().parse(bad)
        msg = str(exc_info.value)
        assert "Symbol" in msg  # expected columns listed
        assert "Ticker" in msg  # found columns listed
        assert "Avg Price" in msg  # fills variant listed
        assert "Avg Fill Price" in msg  # order-history variant listed

    def test_empty_file_fails_loudly(self, tmp_path: Path):
        empty = tmp_path / "empty.csv"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(ImporterError, match="empty"):
            WebullImporter().parse(empty)

    def test_bad_timestamp_fails_loudly(self, tmp_path: Path):
        bad = tmp_path / "bad_time.csv"
        bad.write_text(
            "Symbol,Side,Status,Filled,Avg Price,Filled Time\n"
            "AAPL,Buy,Filled,100,190.00,not-a-time\n",
            encoding="utf-8",
        )
        with pytest.raises(ImporterError, match="Filled Time"):
            WebullImporter().parse(bad)


class TestWebullOrdersVariant:
    """Order-history export: rows are orders, not fills; only filled ones import."""

    def test_imports_filled_and_partial_rows_counting_skips(self, fixtures_dir: Path):
        importer = WebullImporter()
        fills = importer.parse(fixtures_dir / "webull_orders_sample.csv")
        assert len(fills) == 4
        assert importer.skipped_unfilled == 3  # cancelled + pending + rejected
        assert [f.symbol for f in fills] == ["AAPL", "AAPL", "TSLA", "TSLA"]

    def test_partial_fill_uses_filled_qty_not_order_qty(self, fixtures_dir: Path):
        fills = WebullImporter().parse(fixtures_dir / "webull_orders_sample.csv")
        partial = fills[2]  # TSLA buy: Qty 80, Filled Qty 50, Partial Filled
        assert partial.qty == D("50")
        assert partial.price == D("240.10")
        assert partial.side is Side.BUY

    def test_fees_sum_commission_and_fee_columns(self, fixtures_dir: Path):
        fills = WebullImporter().parse(fixtures_dir / "webull_orders_sample.csv")
        assert fills[0].fees == D("0.02")  # commission 0.00 + fee 0.02
        assert fills[1].fees == D("0.03")  # empty commission cell counts as 0

    def test_update_time_parsed_as_eastern(self, fixtures_dir: Path):
        first = WebullImporter().parse(fixtures_dir / "webull_orders_sample.csv")[0]
        # 09:31:05 EDT == 13:31:05 UTC
        assert first.executed_at.astimezone(UTC) == datetime(2026, 6, 1, 13, 31, 5, tzinfo=UTC)

    def test_undefined_column_is_kept_harmlessly(self, fixtures_dir: Path):
        first = WebullImporter().parse(fixtures_dir / "webull_orders_sample.csv")[0]
        assert first.raw_row["undefined"] == ""
        assert first.raw_row["Order ID"] == "SYN0001"

    def test_bad_update_time_names_the_column(self, tmp_path: Path):
        bad = tmp_path / "bad_time.csv"
        bad.write_text(
            "Symbol,Side,Qty,Filled Qty,Avg Fill Price,Status,Update Time\n"
            "AAPL,Buy,100,100,190.00,Filled,not-a-time\n",
            encoding="utf-8",
        )
        with pytest.raises(ImporterError, match="Update Time"):
            WebullImporter().parse(bad)

    def test_all_rows_unfilled_fails_loudly(self, tmp_path: Path):
        unfilled = tmp_path / "unfilled.csv"
        unfilled.write_text(
            "Symbol,Side,Qty,Filled Qty,Avg Fill Price,Status,Update Time\n"
            "AAPL,Buy,100,0,,Cancelled,06/01/2026 09:31:05 EDT\n",
            encoding="utf-8",
        )
        with pytest.raises(ImporterError, match="no filled executions"):
            WebullImporter().parse(unfilled)


class TestGenericImporter:
    def test_default_mapping(self, fixtures_dir: Path):
        fills = GenericCsvImporter().parse(fixtures_dir / "generic_sample.csv")
        assert len(fills) == 4
        assert fills[0].fees == D("0.35")
        assert fills[0].executed_at == datetime(2026, 6, 2, 14, 30, 5, tzinfo=UTC)

    def test_custom_mapping_and_timezone(self, tmp_path: Path):
        csv_file = tmp_path / "broker.csv"
        csv_file.write_text(
            "Ticker,Action,Shares,FillPrice,When\nAAPL,BOT,100,190.00,06/01/2026 09:31:05\n",
            encoding="utf-8",
        )
        importer = GenericCsvImporter(
            mapping=ColumnMapping(
                symbol="Ticker",
                side="Action",
                qty="Shares",
                price="FillPrice",
                executed_at="When",
            ),
            datetime_format="%m/%d/%Y %H:%M:%S",
            timezone="America/New_York",
        )
        (fill,) = importer.parse(csv_file)
        assert fill.side is Side.BUY
        assert fill.executed_at.astimezone(UTC) == datetime(2026, 6, 1, 13, 31, 5, tzinfo=UTC)

    def test_missing_mapped_column_fails_loudly(self, tmp_path: Path):
        csv_file = tmp_path / "broker.csv"
        csv_file.write_text("symbol,side,qty\nAAPL,buy,1\n", encoding="utf-8")
        with pytest.raises(ImporterError, match="missing expected column"):
            GenericCsvImporter().parse(csv_file)


class TestRegistry:
    def test_available_brokers(self):
        assert available_brokers() == ["generic", "webull"]

    def test_unknown_broker(self):
        with pytest.raises(ImporterError, match="unknown broker"):
            get_importer("etrade")


class TestDedupHash:
    def test_same_fill_same_hash(self, fixtures_dir: Path):
        a = WebullImporter().parse(fixtures_dir / "webull_sample.csv")
        b = WebullImporter().parse(fixtures_dir / "webull_sample.csv")
        assert [fill_dedup_hash(f) for f in a] == [fill_dedup_hash(f) for f in b]

    def test_distinct_fills_distinct_hashes(self, fixtures_dir: Path):
        fills = WebullImporter().parse(fixtures_dir / "webull_sample.csv")
        hashes = {fill_dedup_hash(f) for f in fills}
        assert len(hashes) == len(fills)
