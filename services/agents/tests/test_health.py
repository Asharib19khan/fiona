from fastapi.testclient import TestClient

from fiona_agents.main import create_app


def test_healthz_matches_the_contract_shape() -> None:
    res = TestClient(create_app()).get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"api_version": "v1", "status": "ok", "service": "agents"}
    assert res.headers["X-Request-Id"].startswith("req_")


def test_unknown_path_uses_the_error_envelope() -> None:
    res = TestClient(create_app()).get("/v1/nowhere")
    assert res.status_code == 404
    body = res.json()
    assert body["api_version"] == "v1"
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"].startswith("req_")


def test_oversized_bodies_are_refused() -> None:
    from fastapi.testclient import TestClient

    from fiona_agents.main import create_app

    res = TestClient(create_app()).post(
        "/v1/agents/ask",
        content=b"x" * (8 * 1024 * 1024 + 1),
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "request_too_large"
