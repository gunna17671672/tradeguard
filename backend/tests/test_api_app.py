"""App factory wiring: health check, DB path resolution, CORS for the dev frontend."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import app.db
from app.db import default_db_path
from app.main import create_app
from tests.conftest import API_TEST_RULES, ApiHarness


def test_health_reports_resolved_paths(api: ApiHarness):
    response = api.client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db_path"] == str(api.db_path.resolve())
    assert body["rules_path"] == str(api.rules_path)


def test_creates_sqlite_db_at_given_path(api: ApiHarness):
    assert api.db_path.exists()


def test_cors_allows_dev_frontend_origin(api: ApiHarness):
    response = api.client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin(api: ApiHarness):
    response = api.client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


class TestCanonicalDbPath:
    """The default DB must not depend on where uvicorn or the CLI was launched."""

    def test_same_file_from_any_launch_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("TRADEGUARD_DB", raising=False)
        monkeypatch.chdir(tmp_path)
        from_tmp = default_db_path()
        (tmp_path / "nested").mkdir()
        monkeypatch.chdir(tmp_path / "nested")
        from_nested = default_db_path()

        assert from_tmp == from_nested
        assert from_tmp.is_absolute()
        # anchored next to the app package: backend/tradeguard.db
        backend_dir = Path(app.db.__file__).resolve().parent.parent
        assert from_tmp == backend_dir / "tradeguard.db"

    def test_env_override_wins_and_is_resolved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRADEGUARD_DB", "custom.db")
        assert default_db_path() == (tmp_path / "custom.db").resolve()

    def test_startup_logs_the_resolved_db_path(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        rules = tmp_path / "rules.yaml"
        rules.write_text(API_TEST_RULES, encoding="utf-8")
        db = tmp_path / "logged.db"
        with caplog.at_level(logging.INFO, logger="tradeguard"):
            create_app(db_path=db, rules_path=rules)
        assert str(db.resolve()) in caplog.text
