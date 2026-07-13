"""App factory wiring: health check, DB creation, CORS for the dev frontend."""

from __future__ import annotations

from tests.conftest import ApiHarness


def test_health(api: ApiHarness):
    response = api.client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_creates_sqlite_db_at_given_path(api: ApiHarness):
    assert api.db_path.exists()


def test_cors_allows_dev_frontend_origin(api: ApiHarness):
    response = api.client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin(api: ApiHarness):
    response = api.client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers
