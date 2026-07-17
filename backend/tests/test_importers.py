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
        assert "Fill price" in msg  # paper order-history variant listed

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


class TestWebullPaperOrdersVariant:
    """PAPER-account order-history export: Quantity is the order quantity (no
    filled-qty column), Fill price / Commission carry the money columns, and
    Closing time — the order's terminal time — is the execution time."""

    HEADER = (
        "Symbol,Side,Type,Quantity,Limit price,Stop price,Fill price,Status,"
        "Commission,Placing time,Closing time,Order ID,Level ID,Leverage,Margin\n"
    )

    def test_imports_filled_rows_skipping_cancelled(self, fixtures_dir: Path):
        importer = WebullImporter()
        fills = importer.parse(fixtures_dir / "webull_paper_orders_sample.csv")
        assert len(fills) == 3
        assert importer.skipped_unfilled == 1  # cancelled GME order
        assert all(f.broker == "webull" for f in fills)

    def test_exchange_prefix_stripped_from_symbols(self, fixtures_dir: Path):
        fills = WebullImporter().parse(fixtures_dir / "webull_paper_orders_sample.csv")
        assert [f.symbol for f in fills] == ["AAPL", "AAPL", "TSLA"]
        # raw_row keeps the export verbatim, prefix and junk columns included
        assert fills[0].raw_row["Symbol"] == "NASDAQ:AAPL"
        assert fills[0].raw_row["Leverage"] == "1:1"
        assert fills[0].raw_row["Margin"] == "19000.00 USD"

    def test_quantity_and_fill_price_are_the_fill(self, fixtures_dir: Path):
        first = WebullImporter().parse(fixtures_dir / "webull_paper_orders_sample.csv")[0]
        assert first.side is Side.BUY
        assert isinstance(first.qty, Decimal) and first.qty == D("100")
        assert isinstance(first.price, Decimal) and first.price == D("190.00")

    def test_closing_time_not_placing_time_is_executed_at(self, fixtures_dir: Path):
        fills = WebullImporter().parse(fixtures_dir / "webull_paper_orders_sample.csv")
        # AAPL sell: placed 09:40:00, closed (filled) 09:45:10 EDT == 13:45:10 UTC
        assert fills[1].executed_at.astimezone(UTC) == datetime(2026, 6, 1, 13, 45, 10, tzinfo=UTC)

    def test_timezone_override_applies(self, fixtures_dir: Path):
        first = WebullImporter(timezone="America/Phoenix").parse(
            fixtures_dir / "webull_paper_orders_sample.csv"
        )[0]
        # 09:31:05 Phoenix (UTC-7, no DST) == 16:31:05 UTC
        assert first.executed_at.astimezone(UTC) == datetime(2026, 6, 1, 16, 31, 5, tzinfo=UTC)

    def test_empty_commission_is_zero_and_present_commission_counts(self, fixtures_dir: Path):
        fills = WebullImporter().parse(fixtures_dir / "webull_paper_orders_sample.csv")
        assert fills[0].fees == D("0")  # empty Commission cell
        assert fills[1].fees == D("0.55")

    def test_partially_filled_row_fails_loudly(self, tmp_path: Path):
        partial = tmp_path / "partial.csv"
        partial.write_text(
            self.HEADER + "NASDAQ:AAPL,Buy,Limit,100,190.00,,190.00,Partially Filled,"
            ",2026-06-01 09:31:05,2026-06-01 09:45:00,9900000001,,1:1,19000.00 USD\n",
            encoding="utf-8",
        )
        with pytest.raises(ImporterError, match="no.*filled-quantity column"):
            WebullImporter().parse(partial)


class TestWebullTimestampFormats:
    """Webull renders either 'MM/DD/YYYY HH:MM:SS EDT' or a zone-less
    'YYYY-MM-DD HH:MM:SS'; both are wall-clock times in the importer's
    `timezone` parameter (default America/New_York), converted to UTC."""

    def _one_row(self, tmp_path: Path, update_time: str) -> Path:
        path = tmp_path / "one.csv"
        path.write_text(
            "Symbol,Side,Qty,Filled Qty,Avg Fill Price,Status,Update Time\n"
            f"AAPL,Buy,100,100,190.00,Filled,{update_time}\n",
            encoding="utf-8",
        )
        return path

    @pytest.mark.parametrize(
        ("raw", "expected_utc"),
        [
            # suffixed style: summer is EDT (UTC-4), winter is EST (UTC-5)
            ("07/14/2026 09:31:05 EDT", datetime(2026, 7, 14, 13, 31, 5, tzinfo=UTC)),
            ("01/15/2026 09:31:05 EST", datetime(2026, 1, 15, 14, 31, 5, tzinfo=UTC)),
            # zone-less style: assumed Eastern, DST resolved from the date
            ("2026-07-14 14:36:05", datetime(2026, 7, 14, 18, 36, 5, tzinfo=UTC)),
            ("2026-01-15 14:36:05", datetime(2026, 1, 15, 19, 36, 5, tzinfo=UTC)),
        ],
    )
    def test_both_formats_across_dst(self, tmp_path: Path, raw: str, expected_utc: datetime):
        (fill,) = WebullImporter().parse(self._one_row(tmp_path, raw))
        assert fill.executed_at.astimezone(UTC) == expected_utc

    def test_timezone_parameter_overrides_the_eastern_assumption(self, tmp_path: Path):
        (fill,) = WebullImporter(timezone="UTC").parse(
            self._one_row(tmp_path, "2026-07-14 14:36:05")
        )
        assert fill.executed_at.astimezone(UTC) == datetime(2026, 7, 14, 14, 36, 5, tzinfo=UTC)

    def test_iso_times_fixture_imports_both_seasons(self, fixtures_dir: Path):
        importer = WebullImporter()
        fills = importer.parse(fixtures_dir / "webull_orders_iso_times.csv")
        assert len(fills) == 4
        assert importer.skipped_unfilled == 1  # cancelled TSLA order
        # AAPL buy on a July day (EDT), MSFT buy on a January day (EST)
        assert fills[0].executed_at.astimezone(UTC) == datetime(2026, 7, 14, 13, 31, 5, tzinfo=UTC)
        assert fills[2].executed_at.astimezone(UTC) == datetime(2026, 1, 15, 15, 0, 0, tzinfo=UTC)

    def test_unparseable_time_error_names_value_and_both_styles(self, tmp_path: Path):
        with pytest.raises(ImporterError) as exc_info:
            WebullImporter().parse(self._one_row(tmp_path, "14-07-2026 14:36"))
        msg = str(exc_info.value)
        assert "'14-07-2026 14:36'" in msg  # offending value
        assert "Update Time" in msg  # offending column
        assert "07/01/2026 09:31:05 EDT" in msg and "2026-07-14 14:36:05" in msg


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
