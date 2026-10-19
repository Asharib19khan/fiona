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


def test_oversized_bodies_are_refused() -> None:
    res = TestClient(create_app()).post(
        "/v1/guardian/review",
        content=b"x" * (1024 * 1024 + 1),
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "request_too_large"


def test_live_mode_hides_the_api_docs(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FIONA_MODE", "live")
    assert TestClient(create_app()).get("/openapi.json").status_code == 404
