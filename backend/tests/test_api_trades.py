"""Trades API: list filters, pagination, detail, and annotation editing.

The `api` fixture's rules are max_trades_per_day(n=2) and
max_risk_per_trade(1% = $250): a third same-day entry violates, and a patched
stop with risk over $250 (entry 100, qty 100 -> stop below 97.50) violates.
"""

from __future__ import annotations

from tests.conftest import ApiHarness, make_fill, round_trip

DAY = 24 * 60  # minutes


def seed_three_days(api: ApiHarness) -> None:
    """One clean-PnL round trip per day on three symbols across three days."""
    api.seed(
        round_trip(symbol="AAPL", day_offset_min=0)
        + round_trip(symbol="MSFT", day_offset_min=DAY)
        + round_trip(symbol="TSLA", day_offset_min=2 * DAY, exit_price="99")
    )


class TestListTrades:
    def test_page_shape_and_money_as_strings(self, api: ApiHarness):
        api.seed(round_trip())
        body = api.client.get("/api/trades").json()
        assert body["total"] == 1
        assert (body["limit"], body["offset"]) == (50, 0)
        trade = body["items"][0]
        assert trade["symbol"] == "AAPL"
        assert trade["status"] == "closed"
        assert trade["net_pnl"] == "100"  # string, never a JSON float
        assert isinstance(trade["net_pnl"], str)

    def test_newest_first(self, api: ApiHarness):
        seed_three_days(api)
        symbols = [t["symbol"] for t in api.client.get("/api/trades").json()["items"]]
        assert symbols == ["TSLA", "MSFT", "AAPL"]

    def test_symbol_filter_is_case_insensitive(self, api: ApiHarness):
        seed_three_days(api)
        body = api.client.get("/api/trades", params={"symbol": "msft"}).json()
        assert [t["symbol"] for t in body["items"]] == ["MSFT"]
        assert body["total"] == 1

    def test_date_range_filter(self, api: ApiHarness):
        seed_three_days(api)  # days 2026-06-01..03 UTC
        body = api.client.get(
            "/api/trades", params={"from": "2026-06-02", "to": "2026-06-02"}
        ).json()
        assert [t["symbol"] for t in body["items"]] == ["MSFT"]

    def test_status_filter(self, api: ApiHarness):
        api.seed(round_trip() + [make_fill("buy", "50", "10", minute=200, symbol="NVDA")])
        open_items = api.client.get("/api/trades", params={"status": "open"}).json()["items"]
        assert [t["symbol"] for t in open_items] == ["NVDA"]

    def test_has_violations_filter(self, api: ApiHarness):
        seed_three_days(api)
        # An oversized patched-in stop ($1000 risk > $250) dirties MSFT on re-audit.
        msft = api.client.get("/api/trades", params={"symbol": "MSFT"}).json()["items"][0]
        api.client.patch(f"/api/trades/{msft['id']}", json={"planned_stop": "90"})

        dirty = api.client.get("/api/trades", params={"has_violations": "true"}).json()
        clean = api.client.get("/api/trades", params={"has_violations": "false"}).json()
        assert {t["symbol"] for t in dirty["items"]} == {"MSFT"}
        assert {t["symbol"] for t in clean["items"]} == {"AAPL", "TSLA"}

    def test_tag_filter(self, api: ApiHarness):
        seed_three_days(api)
        tsla = api.client.get("/api/trades", params={"symbol": "TSLA"}).json()["items"][0]
        api.client.patch(f"/api/trades/{tsla['id']}", json={"setup_tag": "breakout"})
        body = api.client.get("/api/trades", params={"tag": "breakout"}).json()
        assert [t["symbol"] for t in body["items"]] == ["TSLA"]

    def test_pagination(self, api: ApiHarness):
        seed_three_days(api)
        page = api.client.get("/api/trades", params={"limit": 2, "offset": 2}).json()
        assert page["total"] == 3
        assert [t["symbol"] for t in page["items"]] == ["AAPL"]

    def test_limit_validation(self, api: ApiHarness):
        assert api.client.get("/api/trades", params={"limit": 0}).status_code == 422
        assert api.client.get("/api/trades", params={"offset": -1}).status_code == 422

    def test_bad_date_param(self, api: ApiHarness):
        assert api.client.get("/api/trades", params={"from": "not-a-date"}).status_code == 422


class TestTradeDetail:
    def test_includes_fills_timeline_and_violations(self, api: ApiHarness):
        # Third same-day entry (TSLA) violates max_trades_per_day(2)
        api.seed(
            round_trip(symbol="AAPL", entry_min=0, exit_min=10)
            + round_trip(symbol="MSFT", entry_min=20, exit_min=30)
            + round_trip(symbol="TSLA", entry_min=40, exit_min=50)
        )
        tsla = api.client.get("/api/trades", params={"symbol": "TSLA"}).json()["items"][0]
        detail = api.client.get(f"/api/trades/{tsla['id']}").json()
        assert [e["side"] for e in detail["executions"]] == ["buy", "sell"]
        assert detail["executions"][0]["price"] == "100"
        assert [v["rule_id"] for v in detail["violations"]] == ["max_trades_per_day"]

    def test_unknown_id_is_404(self, api: ApiHarness):
        response = api.client.get("/api/trades/999")
        assert response.status_code == 404
        assert "999" in response.json()["detail"]


class TestUpdateTrade:
    def trade_id(self, api: ApiHarness) -> int:
        api.seed(round_trip())
        return api.client.get("/api/trades").json()["items"][0]["id"]

    def test_setting_stop_records_stop_set_at(self, api: ApiHarness):
        trade_id = self.trade_id(api)
        body = api.client.patch(f"/api/trades/{trade_id}", json={"planned_stop": "99.50"}).json()
        assert body["planned_stop"] == "99.50"
        assert body["stop_set_at"] is not None
        assert body["violations"] == []  # risk $50 is within the $250 limit
        assert body["r_multiple"] is not None

    def test_editing_stop_price_keeps_original_stop_set_at(self, api: ApiHarness):
        trade_id = self.trade_id(api)
        first = api.client.patch(f"/api/trades/{trade_id}", json={"planned_stop": "99"}).json()
        second = api.client.patch(f"/api/trades/{trade_id}", json={"planned_stop": "98"}).json()
        assert second["stop_set_at"] == first["stop_set_at"]

    def test_reaudit_flags_oversized_risk_and_clears_it_again(self, api: ApiHarness):
        trade_id = self.trade_id(api)
        dirty = api.client.patch(f"/api/trades/{trade_id}", json={"planned_stop": "90"}).json()
        assert [v["rule_id"] for v in dirty["violations"]] == ["max_risk_per_trade"]

        clean = api.client.patch(f"/api/trades/{trade_id}", json={"planned_stop": None}).json()
        assert clean["planned_stop"] is None
        assert clean["stop_set_at"] is None
        assert clean["violations"] == []  # risk rule needs a stop to evaluate

    def test_partial_update_leaves_other_fields_alone(self, api: ApiHarness):
        trade_id = self.trade_id(api)
        api.client.patch(f"/api/trades/{trade_id}", json={"planned_stop": "99"})
        body = api.client.patch(f"/api/trades/{trade_id}", json={"notes": "late entry"}).json()
        assert body["notes"] == "late entry"
        assert body["planned_stop"] == "99"

    def test_unknown_field_rejected(self, api: ApiHarness):
        trade_id = self.trade_id(api)
        response = api.client.patch(f"/api/trades/{trade_id}", json={"net_pnl": "9999"})
        assert response.status_code == 422

    def test_non_positive_stop_rejected(self, api: ApiHarness):
        trade_id = self.trade_id(api)
        assert (
            api.client.patch(f"/api/trades/{trade_id}", json={"planned_stop": "-1"}).status_code
            == 422
        )

    def test_unknown_id_is_404(self, api: ApiHarness):
        assert api.client.patch("/api/trades/999", json={"notes": "x"}).status_code == 404
