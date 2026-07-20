"""The bundled sample dataset: loads clean, every trade gets its annotation,
and every one of the six built-in rules fires at least once against the
shipped rules.example.yaml — hand-verified counts, see app/sample.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import init_db, make_engine, make_session_factory
from app.models import Trade, Violation
from app.rules.loader import load_rules_config
from app.sample import SAMPLE_RELPATH, find_sample_file, load_sample

EXAMPLE_RULES = Path(__file__).resolve().parents[2] / "rules.example.yaml"


def _session_factory(db_path: Path):
    engine = make_engine(db_path)
    init_db(engine)
    return make_session_factory(engine)


@pytest.fixture
def sample_csv() -> Path:
    path = find_sample_file()
    assert path is not None, f"{SAMPLE_RELPATH} not found above the repo (bundled dataset missing)"
    return path


class TestLoadSample:
    def test_loads_and_annotates_every_trade(self, sample_csv: Path, tmp_path: Path):
        config = load_rules_config(EXAMPLE_RULES)
        factory = _session_factory(tmp_path / "t.db")
        with factory() as session:
            result = load_sample(session, sample_csv, config)
            session.commit()

        assert result.imported.inserted == 58  # 61 rows - 2 cancelled - 1 pending
        assert result.trades == 28
        assert result.annotated == 28  # every trade in the fixture is annotated

        with factory() as session:
            trades = session.scalars(select(Trade)).all()
            assert len(trades) == 28
            assert all(t.setup_tag is not None for t in trades)
            # No open trades: every position in the fixture returns to flat.
            assert all(t.closed_at is not None for t in trades)

    def test_every_builtin_rule_fires_against_the_shipped_template(
        self, sample_csv: Path, tmp_path: Path
    ):
        """Not just stop_required — the whole rule set gets real coverage."""
        config = load_rules_config(EXAMPLE_RULES)
        factory = _session_factory(tmp_path / "t.db")
        with factory() as session:
            result = load_sample(session, sample_csv, config)
            session.commit()

        assert result.violations_recorded == 8
        with factory() as session:
            fired = {v.rule_id for v in session.scalars(select(Violation)).all()}
        assert fired == {
            "max_trades_per_day",
            "stop_required",
            "max_risk_per_trade",
            "blocked_entry_window",
            "revenge_trade",
            "max_daily_loss",
        }

    def test_stop_required_hits_are_two_missing_and_one_late(
        self, sample_csv: Path, tmp_path: Path
    ):
        config = load_rules_config(EXAMPLE_RULES)
        factory = _session_factory(tmp_path / "t.db")
        with factory() as session:
            load_sample(session, sample_csv, config)
            session.commit()
        with factory() as session:
            hits = session.scalars(
                select(Violation).where(Violation.rule_id == "stop_required")
            ).all()
            assert len(hits) == 3
            assert sum("No planned stop" in v.message for v in hits) == 2
            assert sum("min after entry" in v.message for v in hits) == 1

    def test_rerun_is_idempotent_and_reapplies_annotations(self, sample_csv: Path, tmp_path: Path):
        config = load_rules_config(EXAMPLE_RULES)
        factory = _session_factory(tmp_path / "t.db")
        with factory() as session:
            load_sample(session, sample_csv, config)
            session.commit()
        with factory() as session:
            second = load_sample(session, sample_csv, config)
            session.commit()

        assert second.imported.inserted == 0  # every fill dedups
        assert second.trades == 28  # no duplication
        assert second.violations_recorded == 8

    def test_without_rules_config_skips_audit(self, sample_csv: Path, tmp_path: Path):
        factory = _session_factory(tmp_path / "t.db")
        with factory() as session:
            result = load_sample(session, sample_csv, None)
            session.commit()
        assert result.violations_recorded == 0
        with factory() as session:
            assert session.scalars(select(Violation)).all() == []


class TestFindSampleFile:
    def test_discoverable_from_the_repo(self):
        assert find_sample_file() is not None

    def test_none_outside_the_repo(self, tmp_path: Path):
        assert find_sample_file(tmp_path) is None
