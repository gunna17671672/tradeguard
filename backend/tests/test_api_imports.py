"""Imports API: multipart upload happy paths, idempotency, and rejections.

webull_sample.csv holds 4 filled + 1 cancelled order -> 4 fills, 2 closed
trades. generic_sample.csv uses the default column names -> 4 fills, 2 trades.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import ApiHarness


def upload(api: ApiHarness, path: Path, broker: str, mapping: str | None = None):
    data: dict[str, str] = {"broker": broker}
    if mapping is not None:
        data["mapping"] = mapping
    with path.open("rb") as f:
        return api.client.post(
            "/api/imports", data=data, files={"file": (path.name, f, "text/csv")}
        )


def test_webull_upload(api: ApiHarness, fixtures_dir: Path):
    response = upload(api, fixtures_dir / "webull_sample.csv", "webull")
    assert response.status_code == 201
    body = response.json()
    assert body["inserted"] == 4
    assert body["skipped_duplicates"] == 0
    assert body["skipped_unfilled"] == 1  # the cancelled order row
    assert body["trades_rebuilt"] == 2
    assert body["audited"] is True
    assert body["filename"] == "webull_sample.csv"
    assert api.client.get("/api/trades").json()["total"] == 2


def test_webull_order_history_upload(api: ApiHarness, fixtures_dir: Path):
    response = upload(api, fixtures_dir / "webull_orders_sample.csv", "webull")
    assert response.status_code == 201
    body = response.json()
    assert body["inserted"] == 4
    assert body["skipped_unfilled"] == 3  # cancelled + pending + rejected
    assert body["trades_rebuilt"] == 2
    assert api.client.get("/api/trades").json()["total"] == 2


def test_reimport_is_idempotent(api: ApiHarness, fixtures_dir: Path):
    upload(api, fixtures_dir / "webull_sample.csv", "webull")
    body = upload(api, fixtures_dir / "webull_sample.csv", "webull").json()
    assert body["inserted"] == 0
    assert body["skipped_duplicates"] == 4
    assert api.client.get("/api/trades").json()["total"] == 2


def test_generic_upload_with_default_columns(api: ApiHarness, fixtures_dir: Path):
    body = upload(api, fixtures_dir / "generic_sample.csv", "generic").json()
    assert body["inserted"] == 4
    assert body["trades_rebuilt"] == 2


def test_generic_upload_with_custom_mapping(api: ApiHarness, tmp_path: Path):
    csv = tmp_path / "custom.csv"
    csv.write_text(
        "Ticker,Action,Shares,FillPrice,When\n"
        "AMD,buy,10,150.00,2026-06-03T14:00:00+00:00\n"
        "AMD,sell,10,151.00,2026-06-03T15:00:00+00:00\n",
        encoding="utf-8",
    )
    mapping = json.dumps(
        {
            "symbol": "Ticker",
            "side": "Action",
            "qty": "Shares",
            "price": "FillPrice",
            "executed_at": "When",
        }
    )
    body = upload(api, csv, "generic", mapping=mapping).json()
    assert body["inserted"] == 2
    assert body["trades_rebuilt"] == 1


def test_unknown_broker_rejected(api: ApiHarness, fixtures_dir: Path):
    response = upload(api, fixtures_dir / "webull_sample.csv", "etrade")
    assert response.status_code == 422
    assert "unknown broker" in response.json()["detail"]


def test_mapping_with_non_generic_broker_rejected(api: ApiHarness, fixtures_dir: Path):
    response = upload(api, fixtures_dir / "webull_sample.csv", "webull", mapping="{}")
    assert response.status_code == 422


def test_mapping_must_be_json_object(api: ApiHarness, fixtures_dir: Path):
    assert (
        upload(api, fixtures_dir / "generic_sample.csv", "generic", mapping="not json").status_code
        == 422
    )
    assert (
        upload(api, fixtures_dir / "generic_sample.csv", "generic", mapping='["a"]').status_code
        == 422
    )


def test_wrong_columns_fail_loudly_with_client_filename(api: ApiHarness, tmp_path: Path):
    csv = tmp_path / "orders.csv"
    csv.write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    response = upload(api, csv, "generic")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "orders.csv" in detail
    assert "missing expected column" in detail


def test_empty_file_rejected(api: ApiHarness, tmp_path: Path):
    csv = tmp_path / "empty.csv"
    csv.write_text("", encoding="utf-8")
    assert upload(api, csv, "webull").status_code == 422


def test_missing_broker_field_rejected(api: ApiHarness, fixtures_dir: Path):
    with (fixtures_dir / "webull_sample.csv").open("rb") as f:
        response = api.client.post("/api/imports", files={"file": ("x.csv", f, "text/csv")})
    assert response.status_code == 422


def test_missing_file_rejected(api: ApiHarness):
    assert api.client.post("/api/imports", data={"broker": "webull"}).status_code == 422


def test_broken_rules_yaml_is_400_not_500(api: ApiHarness, fixtures_dir: Path):
    api.rules_path.write_text("rules: {nonsense_rule: {}}\n", encoding="utf-8")
    response = upload(api, fixtures_dir / "webull_sample.csv", "webull")
    assert response.status_code == 400
    assert "account" in response.json()["detail"]  # names the missing section
