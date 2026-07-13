"""Weekly report API: adherence, streak, per-rule counts."""

from __future__ import annotations

from tests.conftest import ApiHarness, round_trip

# Seeded trades all close on Mon 2026-06-01 (ET); its Mon-Sun week:
WEEK_PARAM = {"week": "2026-06-03"}


def seed_overtraded_day(api: ApiHarness) -> None:
    api.seed(
        round_trip(symbol="AAPL", entry_min=0, exit_min=10)
        + round_trip(symbol="MSFT", entry_min=20, exit_min=30)
        + round_trip(symbol="TSLA", entry_min=40, exit_min=50, exit_price="99")
    )


def test_week_with_a_violation(api: ApiHarness):
    seed_overtraded_day(api)
    body = api.client.get("/api/reports/weekly", params=WEEK_PARAM).json()
    assert body["week_start"] == "2026-06-01"
    assert body["week_end"] == "2026-06-07"
    assert (body["closed_trades"], body["wins"], body["losses"]) == (3, 2, 1)
    assert body["adherence_pct"] == "66.7"  # 2 of 3 clean
    assert body["violation_count"] == 1
    assert body["violations_by_rule"] == {"max_trades_per_day": 1}
    assert body["streak_days"] == 0  # the only trading day has a violation
    assert body["net_pnl"] == "100"


def test_clean_week(api: ApiHarness):
    api.seed(
        round_trip(symbol="AAPL", entry_min=0, exit_min=10)
        + round_trip(symbol="MSFT", entry_min=20, exit_min=30)
    )
    body = api.client.get("/api/reports/weekly", params=WEEK_PARAM).json()
    assert body["adherence_pct"] == "100.0"
    assert body["violation_count"] == 0
    assert body["streak_days"] == 1


def test_week_without_trades(api: ApiHarness):
    seed_overtraded_day(api)
    body = api.client.get("/api/reports/weekly", params={"week": "2026-06-10"}).json()
    assert body["closed_trades"] == 0
    assert body["adherence_pct"] is None
    assert body["week_start"] == "2026-06-08"


def test_defaults_to_current_week(api: ApiHarness):
    body = api.client.get("/api/reports/weekly").json()
    assert body["closed_trades"] == 0  # no trades seeded today


def test_bad_week_param_rejected(api: ApiHarness):
    assert api.client.get("/api/reports/weekly", params={"week": "junk"}).status_code == 422


def test_missing_rules_file_is_409(api: ApiHarness):
    api.rules_path.unlink()
    response = api.client.get("/api/reports/weekly")
    assert response.status_code == 409
    assert "rules.yaml" in response.json()["detail"]
