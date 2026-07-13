"""Stats API: summary, equity curve, calendar."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import ApiHarness, round_trip

DAY = 24 * 60  # minutes


def seed_three_days(api: ApiHarness) -> None:
    """+100 (6/1), -50 (6/2), +300 (6/3)."""
    api.seed(
        round_trip(symbol="AAPL")
        + round_trip(symbol="MSFT", day_offset_min=DAY, exit_price="99.50")
        + round_trip(symbol="TSLA", day_offset_min=2 * DAY, exit_price="103")
    )


class TestSummary:
    def test_numbers(self, api: ApiHarness):
        seed_three_days(api)
        body = api.client.get("/api/stats/summary").json()
        assert (body["closed_trades"], body["wins"], body["losses"]) == (3, 2, 1)
        assert body["win_rate_pct"] == "66.7"
        assert body["profit_factor"] == "8.00"  # 400 gross wins / 50 gross losses
        assert body["avg_win"] == "200"
        assert body["avg_loss"] == "-50.00"  # Decimal keeps the cents scale of 99.50
        assert body["net_pnl"] == "350.00"
        assert Decimal(body["expectancy"]) == Decimal("350") / 3

    def test_date_range_filters_on_close_day(self, api: ApiHarness):
        seed_three_days(api)
        body = api.client.get(
            "/api/stats/summary", params={"from": "2026-06-02", "to": "2026-06-02"}
        ).json()
        assert body["closed_trades"] == 1
        assert body["net_pnl"] == "-50.00"

    def test_empty_db(self, api: ApiHarness):
        body = api.client.get("/api/stats/summary").json()
        assert body["closed_trades"] == 0
        assert body["win_rate_pct"] is None
        assert body["profit_factor"] is None
        assert body["net_pnl"] == "0"

    def test_bad_date_rejected(self, api: ApiHarness):
        assert api.client.get("/api/stats/summary", params={"from": "junk"}).status_code == 422

    def test_open_trades_excluded(self, api: ApiHarness):
        from tests.conftest import make_fill

        api.seed(round_trip() + [make_fill("buy", "10", "50", minute=500, symbol="NVDA")])
        assert api.client.get("/api/stats/summary").json()["closed_trades"] == 1


class TestEquity:
    def test_cumulative_curve(self, api: ApiHarness):
        seed_three_days(api)
        points = api.client.get("/api/stats/equity").json()
        assert [p["cumulative_pnl"] for p in points] == ["100", "50.00", "350.00"]
        assert [p["net_pnl"] for p in points] == ["100", "-50.00", "300"]

    def test_empty(self, api: ApiHarness):
        assert api.client.get("/api/stats/equity").json() == []


class TestCalendar:
    def test_one_bucket_per_session_day(self, api: ApiHarness):
        seed_three_days(api)
        days = api.client.get("/api/stats/calendar").json()
        assert [(d["day"], d["net_pnl"], d["trade_count"]) for d in days] == [
            ("2026-06-01", "100", 1),
            ("2026-06-02", "-50.00", 1),
            ("2026-06-03", "300", 1),
        ]

    def test_empty(self, api: ApiHarness):
        assert api.client.get("/api/stats/calendar").json() == []
