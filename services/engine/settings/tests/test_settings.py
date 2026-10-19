"""Workspace settings: the sealed AI connection and Launch Lab defaults."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.app.errors import ApiError
from engine.app.main import create_app
from engine.app.tenancy import Actor
from engine.ledger import db
from engine.settings import api, store
from engine.wallet.tests.conftest import seed_wallet_tenant

A, B = "ten_settings_a", "ten_settings_b"
OWNER = {"X-Fiona-Tenant": A}
API_KEY = "sk-ant-api03-" + "x" * 40 + "abcd"
TOKEN = "sk-ant-oat01-" + "y" * 40 + "wxyz"
KEY = base64.urlsafe_b64encode(b"k" * 32).decode()


@pytest.fixture(scope="module")
def client(migrated_db: str) -> Iterator[TestClient]:
    with db.connect(migrated_db, autocommit=True) as conn:
        seed_wallet_tenant(conn, A)
        seed_wallet_tenant(conn, B)

    def conn_override() -> Iterator:
        with db.connect(migrated_db, autocommit=True) as connection:
            yield connection

    app = create_app(modules=["settings"])
    app.dependency_overrides[api.get_conn] = conn_override
    app.dependency_overrides[api.get_clock] = lambda: datetime(2026, 10, 22, 9, tzinfo=UTC)
    yield TestClient(app)


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", KEY)


def agent(tenant: str = A) -> dict[str, str]:
    return {"X-Fiona-Tenant": tenant, "X-Fiona-Agent": "treasurer"}


def test_a_new_workspace_uses_the_servers_own_claude(client: TestClient) -> None:
    res = client.get("/v1/settings/ai", headers={"X-Fiona-Tenant": B}).json()
    assert (res["mode"], res["hint"], res["storage_ready"]) == ("server", None, True)


def test_the_owner_connects_a_key_and_no_browser_ever_sees_it(
    client: TestClient, migrated_db: str
) -> None:
    saved = client.post(
        "/v1/settings/ai", json={"mode": "api_key", "secret": API_KEY}, headers=OWNER
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["hint"] == "…abcd" and API_KEY not in saved.text
    assert API_KEY not in client.get("/v1/settings/ai", headers=OWNER).text
    with db.connect(migrated_db, autocommit=True) as conn:
        stored = conn.execute(
            "select secret_ciphertext from tenant_settings where tenant_id = %s", (A,)
        ).fetchone()[0]
    assert stored.startswith("v1.") and API_KEY not in stored
    # Only Fiona's services receive the secret, to start Claude with it.
    assert client.get("/v1/settings/ai/credential", headers=OWNER).status_code == 403
    given = client.get("/v1/settings/ai/credential", headers=agent()).json()
    assert (given["mode"], given["secret"]) == ("api_key", API_KEY)
    guardian = {"X-Fiona-Tenant": A, "X-Fiona-Agent": "guardian"}
    assert client.get("/v1/settings/ai/credential", headers=guardian).json()["secret"] == API_KEY


def test_a_sealed_secret_only_opens_for_its_own_workspace() -> None:
    sealed = store.seal(A, "ai_connection", API_KEY)
    assert store.unseal(A, "ai_connection", sealed) == API_KEY
    with pytest.raises(store.SecretStorageUnavailable):
        store.unseal(B, "ai_connection", sealed)


def test_wrong_kinds_and_missing_storage_are_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for mode, secret in (
        ("api_key", TOKEN),
        ("subscription_token", API_KEY),
        ("api_key", "nope" * 6),
    ):
        res = client.post("/v1/settings/ai", json={"mode": mode, "secret": secret}, headers=OWNER)
        assert res.status_code == 422, (mode, res.text)
    assert (
        client.post(
            "/v1/settings/ai", json={"mode": "subscription_token"}, headers=OWNER
        ).status_code
        == 422
    )
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY")
    res = client.post(
        "/v1/settings/ai", json={"mode": "subscription_token", "secret": TOKEN}, headers=OWNER
    )
    assert res.status_code == 503 and res.json()["error"]["code"] == "secret_storage_unavailable"
    # With the key gone, a stored secret is refused rather than replaced by the server's account.
    assert client.get("/v1/settings/ai/credential", headers=agent()).status_code == 503


def test_agents_cannot_change_settings_and_finance_is_not_owner(client: TestClient) -> None:
    res = client.post("/v1/settings/ai", json={"mode": "server"}, headers=agent())
    assert res.status_code == 403
    with pytest.raises(ApiError):
        api._owner_only(Actor("usr_finance", "finance"))


def test_switching_back_to_the_server_forgets_the_secret(client: TestClient) -> None:
    client.post(
        "/v1/settings/ai", json={"mode": "subscription_token", "secret": TOKEN}, headers=OWNER
    )
    back = client.post("/v1/settings/ai", json={"mode": "server"}, headers=OWNER).json()
    assert (back["mode"], back["hint"]) == ("server", None)
    assert client.get("/v1/settings/ai/credential", headers=agent()).json()["secret"] is None


def test_launch_lab_defaults_round_trip(client: TestClient) -> None:
    assert client.get("/v1/settings/launch-lab", headers=OWNER).json()["defaults"] is None
    body = {"currency": "PKR", "freight_share_bp": 300, "marketing_monthly_minor": 1_500_000}
    saved = client.post("/v1/settings/launch-lab", json=body, headers=OWNER)
    assert saved.status_code == 200 and saved.json()["defaults"] == body
    assert client.post("/v1/settings/launch-lab", json=body, headers=agent()).status_code == 403
    bad = client.post(
        "/v1/settings/launch-lab", json={**body, "freight_share_bp": 20_000}, headers=OWNER
    )
    assert bad.status_code in (400, 422)
