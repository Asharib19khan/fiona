from fastapi.testclient import TestClient

from engine.analysis.stub import FY2025, FY2026
from engine.app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_get_stage_serves_labelled_stub():
    body = _client().get("/v1/stage").json()
    assert body["api_version"] == "v1"
    assert body["data_source"] == "stub"
    assert body["result"]["owner_stated_stage"] == "growth"
    assert body["result"]["stage"] in {"shake_out", "mature"}


def test_other_tenant_has_no_statements():
    resp = _client().get(
        "/v1/analysis/ratios", headers={"X-Fiona-Tenant": "ten_shenzhen_electronics"}
    )
    assert resp.status_code == 404


def test_post_ratios_returns_figures_with_metric_ids():
    payload = {
        "latest": FY2026.model_dump(mode="json"),
        "prior": FY2025.model_dump(mode="json"),
        "country": "PK",
    }
    body = _client().post("/v1/analysis/ratios", json=payload).json()
    ids = {f["metric_id"] for f in body["figures"]}
    assert {"solvency.dscr", "liquidity.current_ratio", "profit.roic"} <= ids
    dscr = next(f for f in body["figures"] if f["metric_id"] == "solvency.dscr")
    assert dscr["value"] == 18246 and dscr["unit"] == "bp"
