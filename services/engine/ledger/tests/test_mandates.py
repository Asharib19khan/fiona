"""Permission tiers: reading mandates, and the owner changing an agent's autonomy within the
rulebook ceiling, as a new version with an audit record. Also the single-bill read."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from engine.app.main import app
from engine.ledger import api, db
from engine.ledger.participation import record_bill_intake
from engine.wallet.tests.conftest import TODAY, seed_wallet_tenant

TENANT = "ten_mandates_test"
HEADERS = {"X-Fiona-Tenant": TENANT}
AS_OWNER = {**HEADERS, "X-User-Id": "usr_owner_01"}
AS_TREASURER = {**HEADERS, "X-Fiona-Agent": "treasurer"}
CLOCK = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def client(migrated_db: str) -> Iterator[TestClient]:
    with db.connect(migrated_db, autocommit=True) as conn:
        seed_wallet_tenant(conn, TENANT, payment_autonomy="prepare")
        with db.tenant_session(conn, TENANT):
            conn.execute(
                "insert into accounts (tenant_id, code, name, class, neutral_class) values"
                " (%s, '1200', 'Inventory', 'asset', 'inventory'), (%s, '1300', 'Input tax', 'asset', 'tax')"
                " on conflict do nothing",
                (TENANT, TENANT),
            )
        record_bill_intake(
            conn,
            TENANT,
            {
                "id": "bill_m1",
                "supplier_id": "sup_001",
                "number": "INV-M1",
                "total_minor": 500_000,
                "issue_date": TODAY,
                "due_date": TODAY,
            },
            now=CLOCK,
        )

    def conn_override() -> Iterator[psycopg.Connection]:
        with db.connect(migrated_db, autocommit=True) as connection:
            yield connection

    app.dependency_overrides[api.get_conn] = conn_override
    app.dependency_overrides[api.get_clock] = lambda: CLOCK
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def treasurer(client: TestClient) -> dict:
    data = client.get("/v1/mandates", headers=HEADERS).json()
    assert data["levels"] == ["advise", "prepare", "act_within_mandate"]
    return next(m for m in data["mandates"] if m["agent"] == "treasurer")


def test_owner_raises_autonomy_as_a_new_audited_version(client: TestClient) -> None:
    before = treasurer(client)
    assert before["autonomy"] == {"payment": "prepare"}
    assert before["ceiling"] == {"payment": "act_within_mandate"}

    res = client.post(
        "/v1/mandates/treasurer/autonomy",
        json={"action_type": "payment", "level": "act_within_mandate"},
        headers=AS_OWNER,
    )
    assert res.status_code == 200, res.text
    after = res.json()["mandate"]
    assert after["version"] == before["version"] + 1 and after["source"] == "owner"
    assert after["autonomy"] == {"payment": "act_within_mandate"}

    records = client.get("/v1/audit", headers=HEADERS).json()["records"]
    change = [r["record"] for r in records if r["record"].get("action") == "mandate_change"][-1]
    assert change["from"] == "prepare" and change["to"] == "act_within_mandate"
    assert change["changed_by"] == "usr_owner_01"

    back = client.post(
        "/v1/mandates/treasurer/autonomy",
        json={"action_type": "payment", "level": "prepare"},
        headers=AS_OWNER,
    )
    assert back.json()["mandate"]["version"] == before["version"] + 2


@pytest.mark.parametrize(
    ("headers", "body", "status", "code"),
    [
        (
            AS_TREASURER,
            {"action_type": "payment", "level": "act_within_mandate"},
            403,
            "owner_only",
        ),
        (AS_OWNER, {"action_type": "payment", "level": "autopilot"}, 422, "invalid_level"),
        (AS_OWNER, {"action_type": "journal_adjustment", "level": "prepare"}, 403, "not_permitted"),
    ],
)
def test_autonomy_changes_are_guarded(
    client: TestClient, headers: dict, body: dict, status: int, code: str
) -> None:
    res = client.post("/v1/mandates/treasurer/autonomy", json=body, headers=headers)
    assert res.status_code == status, res.text
    assert res.json()["error"]["code"] == code


def test_no_owner_setting_can_exceed_the_system_ceiling(client: TestClient) -> None:
    res = client.post(
        "/v1/mandates/cfo_strategist/autonomy",
        json={"action_type": "payment", "level": "prepare"},
        headers=AS_OWNER,
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "not_permitted"


def test_single_bill_read_names_its_document(client: TestClient) -> None:
    bill = client.get("/v1/bills/bill_m1", headers=HEADERS).json()["bill"]
    assert bill["number"] == "INV-M1" and bill["document_id"].startswith("doc_")
    assert bill["open"] == {"minor": 500_000, "currency": "PKR"}
    assert client.get("/v1/bills/bill_nope", headers=HEADERS).status_code == 404
