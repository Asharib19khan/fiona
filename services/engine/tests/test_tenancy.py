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


def test_live_mode_accepts_verified_token(monkeypatch: pytest.MonkeyPatch) -> None:
    import base64
    import hashlib
    import hmac
    import json
    import time

    secret = "a" * 32
    monkeypatch.setenv("INTERNAL_JWT_SECRET", secret)

    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "usr_owner_01",
        "tenant_id": "ten_live_test",
        "role": "owner",
        "aud": "fiona-engine",
        "iat": now,
        "exp": now + 60,
    }
    h_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=").decode("ascii")
    )
    p_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    )
    msg = f"{h_b64}.{p_b64}"
    sig = hmac.new(secret.encode("utf-8"), msg.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    token = f"{msg}.{sig_b64}"

    res = make_client(mode="live").get("/v1/whoami", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == {"tenant_id": "ten_live_test"}


def test_live_mode_rejects_expired_or_tampered_token(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "a" * 32
    monkeypatch.setenv("INTERNAL_JWT_SECRET", secret)

    res = make_client(mode="live").get(
        "/v1/whoami", headers={"Authorization": "Bearer bad.token.here"}
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"
