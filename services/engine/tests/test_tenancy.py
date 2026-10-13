"""R15: the tenant comes from the server side, never from the client's query or body."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.app import errors
from engine.app.tenancy import TenantId


def make_client(mode: str = "mock") -> TestClient:
    app = FastAPI()
    app.state.mode = mode
    errors.install(app)

    @app.get("/v1/whoami")
    def whoami(tenant_id: TenantId) -> dict[str, str]:
        return {"tenant_id": tenant_id}

    return TestClient(app)


def test_mock_mode_defaults_to_the_demo_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_TENANT_ID", raising=False)
    assert make_client().get("/v1/whoami").json() == {"tenant_id": "ten_karachi_apparel"}


def test_mock_mode_accepts_the_tenant_header() -> None:
    res = make_client().get("/v1/whoami", headers={"X-Fiona-Tenant": "ten_shenzhen_electronics"})
    assert res.json() == {"tenant_id": "ten_shenzhen_electronics"}


def test_a_query_parameter_never_sets_the_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_TENANT_ID", raising=False)
    res = make_client().get("/v1/whoami?tenant_id=ten_someone_else")
    assert res.json() == {"tenant_id": "ten_karachi_apparel"}


def test_a_malformed_tenant_is_rejected() -> None:
    res = make_client().get("/v1/whoami", headers={"X-Fiona-Tenant": "ten_x'; drop table"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_tenant"


def test_live_mode_fails_closed_until_token_verification_lands() -> None:
    res = make_client(mode="live").get(
        "/v1/whoami", headers={"X-Fiona-Tenant": "ten_karachi_apparel"}
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"
