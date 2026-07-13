"""Violations feed API: trade-joined items, filters, pagination."""

from __future__ import annotations

from tests.conftest import ApiHarness, round_trip


def seed_two_violations(api: ApiHarness) -> None:
    """Three same-day round trips: the third (TSLA) breaks the 2-per-day limit,
    and an oversized stop patched onto AAPL breaks max_risk_per_trade."""
    api.seed(
        round_trip(symbol="AAPL", entry_min=0, exit_min=10)
        + round_trip(symbol="MSFT", entry_min=20, exit_min=30)
        + round_trip(symbol="TSLA", entry_min=40, exit_min=50, exit_price="99")
    )
    aapl = api.client.get("/api/trades", params={"symbol": "AAPL"}).json()["items"][0]
    api.client.patch(f"/api/trades/{aapl['id']}", json={"planned_stop": "90"})


def test_feed_items_join_trade_fields(api: ApiHarness):
    seed_two_violations(api)
    body = api.client.get("/api/violations").json()
    assert body["total"] == 2
    item = body["items"][0]
    assert {"rule_id", "severity", "message", "trade_id", "symbol", "net_pnl"} <= set(item)
    # Newest trade first: TSLA entered last
    assert item["symbol"] == "TSLA"
    assert isinstance(item["net_pnl"], str)


def test_rule_id_filter(api: ApiHarness):
    seed_two_violations(api)
    body = api.client.get("/api/violations", params={"rule_id": "max_trades_per_day"}).json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "TSLA"


def test_severity_filter(api: ApiHarness):
    seed_two_violations(api)
    assert api.client.get("/api/violations", params={"severity": "warn"}).json()["total"] == 0
    assert api.client.get("/api/violations", params={"severity": "violation"}).json()["total"] == 2


def test_bad_severity_rejected(api: ApiHarness):
    assert api.client.get("/api/violations", params={"severity": "fatal"}).status_code == 422


def test_pagination(api: ApiHarness):
    seed_two_violations(api)
    page = api.client.get("/api/violations", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2
    assert [item["symbol"] for item in page["items"]] == ["AAPL"]


def test_empty_db(api: ApiHarness):
    body = api.client.get("/api/violations").json()
    assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}
