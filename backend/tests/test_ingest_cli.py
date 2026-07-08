"""End-to-end import tests: CLI + ingest layer against a temp SQLite DB.

The 40-fill fixture's expected values are hand-computed:
15 trades (AAPL 3, TSLA 2, NVDA 2 via a flip, AMD 2 with one open, MSFT 1,
META 2, AMZN 1, INTC 1, GOOG 1); 14 closed with gross PnL 1027.50 total;
the open AMD trade has 50 shares on and +50 realized from a partial exit.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.cli import main
from app.db import init_db, make_engine, make_session_factory
from app.models import Direction, Execution, ImportBatch, Trade, TradeStatus

D = Decimal


def _session_factory(db_path: Path):
    engine = make_engine(db_path)
    init_db(engine)
    return make_session_factory(engine)


class TestFortyFillFixture:
    def _import(self, fixtures_dir: Path, db: Path) -> int:
        return main(
            [
                "import",
                str(fixtures_dir / "webull_day_40_fills.csv"),
                "--broker",
                "webull",
                "--db",
                str(db),
            ]
        )

    def test_import_counts_and_pnl(self, fixtures_dir: Path, tmp_path: Path, capsys):
        db = tmp_path / "t.db"
        assert self._import(fixtures_dir, db) == 0
        out = capsys.readouterr().out
        assert "Imported 40 fill(s)" in out

        with _session_factory(db)() as session:
            fills = session.scalars(select(Execution)).all()
            trades = session.scalars(select(Trade)).all()
            assert len(fills) == 40
            assert len(trades) == 15

            closed = [t for t in trades if t.status is TradeStatus.CLOSED]
            assert len(closed) == 14
            assert sum(t.gross_pnl for t in closed) == D("1027.50")
            assert sum(t.net_pnl for t in closed) == D("1027.50")  # Webull: no fees

    def test_partial_fill_and_scale_out_cases(self, fixtures_dir: Path, tmp_path: Path):
        db = tmp_path / "t.db"
        assert self._import(fixtures_dir, db) == 0
        with _session_factory(db)() as session:
            trades = session.scalars(select(Trade)).all()
            by_symbol: dict[str, list[Trade]] = {}
            for t in sorted(trades, key=lambda t: t.opened_at):
                by_symbol.setdefault(t.symbol, []).append(t)

            # MSFT: scale in 3 lots, scale out 3 exits, FIFO-matched
            (msft,) = by_symbol["MSFT"]
            assert msft.gross_pnl == D("142.50")
            assert msft.max_qty == D("90")
            assert msft.fill_count == 6

            # AAPL trade 2: partial exits 150 + 50 against 100 + 100 entries
            aapl2 = by_symbol["AAPL"][1]
            assert aapl2.gross_pnl == D("225.00")
            assert aapl2.max_qty == D("200")

            # NVDA: one sell crosses zero -> long trade + short trade
            nvda_long, nvda_short = by_symbol["NVDA"]
            assert nvda_long.direction is Direction.LONG
            assert nvda_long.gross_pnl == D("200.00")
            assert nvda_short.direction is Direction.SHORT
            assert nvda_short.gross_pnl == D("50.00")

            # AMD: second trade still open with realized partial-exit PnL
            amd_open = by_symbol["AMD"][1]
            assert amd_open.status is TradeStatus.OPEN
            assert amd_open.closed_at is None
            assert amd_open.gross_pnl == D("50.00")

            # TSLA short with scaled entry
            tsla_short = by_symbol["TSLA"][0]
            assert tsla_short.direction is Direction.SHORT
            assert tsla_short.gross_pnl == D("250.00")

    def test_reimport_is_idempotent(self, fixtures_dir: Path, tmp_path: Path, capsys):
        db = tmp_path / "t.db"
        assert self._import(fixtures_dir, db) == 0
        assert self._import(fixtures_dir, db) == 0
        out = capsys.readouterr().out
        assert "Imported 0 fill(s)" in out.splitlines()[-1]
        assert "40 duplicate(s) skipped" in out

        with _session_factory(db)() as session:
            assert len(session.scalars(select(Execution)).all()) == 40
            assert len(session.scalars(select(Trade)).all()) == 15
            assert len(session.scalars(select(ImportBatch)).all()) == 2

    def test_fills_linked_to_trades(self, fixtures_dir: Path, tmp_path: Path):
        db = tmp_path / "t.db"
        assert self._import(fixtures_dir, db) == 0
        with _session_factory(db)() as session:
            unlinked = session.scalars(select(Execution).where(Execution.trade_id.is_(None))).all()
            assert unlinked == []


class TestAnnotationsSurviveRebuild:
    def test_reimport_preserves_user_annotations(self, fixtures_dir: Path, tmp_path: Path):
        db = tmp_path / "t.db"
        csv = str(fixtures_dir / "webull_day_40_fills.csv")
        assert main(["import", csv, "--broker", "webull", "--db", str(db)]) == 0

        factory = _session_factory(db)
        with factory() as session:
            trade = session.scalars(select(Trade).where(Trade.symbol == "MSFT")).one()
            trade.planned_stop = D("414.50")
            trade.setup_tag = "orb"
            trade.notes = "clean breakout"
            session.commit()

        # Re-importing rebuilds every touched trade; annotations must carry over.
        assert main(["import", csv, "--broker", "webull", "--db", str(db)]) == 0
        with factory() as session:
            trade = session.scalars(select(Trade).where(Trade.symbol == "MSFT")).one()
            assert trade.planned_stop == D("414.50")
            assert trade.setup_tag == "orb"
            assert trade.notes == "clean breakout"


class TestCliGeneric:
    def test_generic_import_with_mapping_file(self, tmp_path: Path, capsys):
        csv_file = tmp_path / "custom.csv"
        csv_file.write_text(
            "Ticker,Action,Shares,FillPrice,Commission,When\n"
            "AAPL,buy,100,190.00,0.50,06/01/2026 09:31:05\n"
            "AAPL,sell,100,191.00,0.50,06/01/2026 09:45:00\n",
            encoding="utf-8",
        )
        mapping_file = tmp_path / "mapping.json"
        mapping_file.write_text(
            json.dumps(
                {
                    "symbol": "Ticker",
                    "side": "Action",
                    "qty": "Shares",
                    "price": "FillPrice",
                    "fees": "Commission",
                    "executed_at": "When",
                    "datetime_format": "%m/%d/%Y %H:%M:%S",
                    "timezone": "America/New_York",
                }
            ),
            encoding="utf-8",
        )
        db = tmp_path / "t.db"
        rc = main(
            [
                "import",
                str(csv_file),
                "--broker",
                "generic",
                "--mapping",
                str(mapping_file),
                "--db",
                str(db),
            ]
        )
        assert rc == 0
        with _session_factory(db)() as session:
            (trade,) = session.scalars(select(Trade)).all()
            assert trade.gross_pnl == D("100.00")
            assert trade.total_fees == D("1.00")
            assert trade.net_pnl == D("99.00")

    def test_mapping_flag_rejected_for_webull(self, tmp_path: Path, capsys):
        f = tmp_path / "x.csv"
        f.write_text("a\n1\n", encoding="utf-8")
        m = tmp_path / "m.json"
        m.write_text("{}", encoding="utf-8")
        rc = main(["import", str(f), "--broker", "webull", "--mapping", str(m)])
        assert rc == 1
        assert "only supported with --broker generic" in capsys.readouterr().err


class TestCliErrors:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = main(["import", str(tmp_path / "nope.csv"), "--broker", "webull"])
        assert rc == 2
        assert "file not found" in capsys.readouterr().err

    def test_bad_columns_exit_code(self, tmp_path: Path, capsys):
        f = tmp_path / "bad.csv"
        f.write_text("Ticker,Action\nAAPL,Buy\n", encoding="utf-8")
        rc = main(["import", str(f), "--broker", "webull", "--db", str(tmp_path / "t.db")])
        assert rc == 1
        err = capsys.readouterr().err
        assert "missing expected column" in err
