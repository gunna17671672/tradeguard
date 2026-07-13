"""Rules API: read rules.yaml, validate-then-write, re-audit on change."""

from __future__ import annotations

import yaml

from tests.conftest import ApiHarness, round_trip

VALID_BODY = {
    "account": {"account_size": "25000", "timezone": "America/New_York"},
    "rules": {"max_trades_per_day": {"n": 10}},
}


def seed_overtraded_day(api: ApiHarness) -> None:
    """Three same-day trades; the third violates max_trades_per_day(2)."""
    api.seed(
        round_trip(symbol="AAPL", entry_min=0, exit_min=10)
        + round_trip(symbol="MSFT", entry_min=20, exit_min=30)
        + round_trip(symbol="TSLA", entry_min=40, exit_min=50)
    )


class TestReadRules:
    def test_returns_sections_and_registry(self, api: ApiHarness):
        body = api.client.get("/api/rules").json()
        assert body["account"]["account_size"] == "25000"
        assert body["rules"]["max_trades_per_day"] == {"n": 2}
        assert set(body["enabled_rule_ids"]) == {"max_trades_per_day", "max_risk_per_trade"}
        assert len(body["available_rules"]) == 6

    def test_invalid_file_is_400(self, api: ApiHarness):
        api.rules_path.write_text("rules: {bogus_rule: {}}\n", encoding="utf-8")
        response = api.client.get("/api/rules")
        assert response.status_code == 400
        assert "account" in response.json()["detail"]


class TestWriteRules:
    def test_validates_then_writes_file(self, api: ApiHarness):
        response = api.client.put("/api/rules", json=VALID_BODY)
        assert response.status_code == 200
        assert response.json()["enabled_rule_ids"] == ["max_trades_per_day"]

        on_disk = yaml.safe_load(api.rules_path.read_text(encoding="utf-8"))
        assert on_disk == VALID_BODY
        assert api.client.get("/api/rules").json()["rules"] == VALID_BODY["rules"]

    def test_loosening_a_rule_clears_old_violations(self, api: ApiHarness):
        seed_overtraded_day(api)
        assert api.client.get("/api/violations").json()["total"] == 1

        body = api.client.put("/api/rules", json=VALID_BODY).json()  # n: 2 -> 10
        assert body["violations_recorded"] == 0
        assert api.client.get("/api/violations").json()["total"] == 0

    def test_tightening_a_rule_records_new_violations(self, api: ApiHarness):
        seed_overtraded_day(api)
        tighter = {"account": VALID_BODY["account"], "rules": {"max_trades_per_day": {"n": 1}}}
        body = api.client.put("/api/rules", json=tighter).json()
        assert body["violations_recorded"] == 2  # trades #2 and #3 now violate
        assert api.client.get("/api/violations").json()["total"] == 2

    def test_disabled_rule_kept_but_not_enabled(self, api: ApiHarness):
        payload = {
            "account": VALID_BODY["account"],
            "rules": {"max_trades_per_day": {"enabled": False, "n": 5}},
        }
        body = api.client.put("/api/rules", json=payload).json()
        assert body["enabled_rule_ids"] == []
        assert body["rules"]["max_trades_per_day"]["n"] == 5

    def test_unknown_rule_rejected_and_file_untouched(self, api: ApiHarness):
        before = api.rules_path.read_text(encoding="utf-8")
        payload = {"account": VALID_BODY["account"], "rules": {"no_fomo": {}}}
        response = api.client.put("/api/rules", json=payload)
        assert response.status_code == 422
        assert "no_fomo" in response.json()["detail"]
        assert api.rules_path.read_text(encoding="utf-8") == before

    def test_bad_params_rejected(self, api: ApiHarness):
        payload = {"account": VALID_BODY["account"], "rules": {"max_trades_per_day": {"n": -1}}}
        assert api.client.put("/api/rules", json=payload).status_code == 422

    def test_bad_severity_rejected(self, api: ApiHarness):
        payload = {
            "account": VALID_BODY["account"],
            "rules": {"max_trades_per_day": {"n": 2, "severity": "nuclear"}},
        }
        assert api.client.put("/api/rules", json=payload).status_code == 422

    def test_missing_account_rejected(self, api: ApiHarness):
        assert api.client.put("/api/rules", json={"rules": {}}).status_code == 422
