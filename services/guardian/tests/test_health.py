from fastapi.testclient import TestClient

from fiona_guardian.main import create_app


def test_healthz_matches_the_contract_shape() -> None:
    res = TestClient(create_app()).get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"api_version": "v1", "status": "ok", "service": "guardian"}
    assert res.headers["X-Request-Id"].startswith("req_")


def test_unknown_path_uses_the_error_envelope() -> None:
    res = TestClient(create_app()).get("/v1/nowhere")
    assert res.status_code == 404
    body = res.json()
    assert body["api_version"] == "v1"
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"].startswith("req_")
