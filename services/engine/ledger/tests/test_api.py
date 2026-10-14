"""The ledger, import, wallet and audit endpoints, through the real app (router auto-discovery)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.app.main import app
from engine.ledger import api, db
from engine.wallet.tests.conftest import seed_wallet_tenant

TENANT = "ten_api_test"
HEADERS = {"X-Fiona-Tenant": TENANT}
NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
BANK = (
    "account_iban,line_no,posted_on,value_date,narration,reference,amount_minor,balance_minor,currency\n"
    "PK00SYNWAPI,1,2026-10-20,2026-10-20,CASH DEPOSIT BR01 SLIP 00001,CD1,50000,50000,PKR\n"
    "PK00SYNWAPI,2,2026-10-21,2026-10-21,BANK CHARGES OCT-2026,BC1,-2500,47500,PKR\n"
)


@pytest.fixture(scope="module")
def client(migrated_db: str) -> Iterator[TestClient]:
    with db.connect(migrated_db, autocommit=True) as conn:
        seed_wallet_tenant(conn, TENANT)

    def conn_override() -> Iterator:
        with db.connect(migrated_db, autocommit=True) as connection:
            yield connection

    app.dependency_overrides[api.get_conn] = conn_override
    app.dependency_overrides[api.get_clock] = lambda: NOW
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_bank_import_is_idempotent(client: TestClient) -> None:
    first = client.post(
        "/v1/import/bank", content=BANK, headers={**HEADERS, "Content-Type": "text/csv"}
    )
    assert first.status_code == 200, first.text
    assert (first.json()["inserted"], first.json()["api_version"]) == (2, "v1")
    again = client.post(
        "/v1/import/bank", content=BANK, headers={**HEADERS, "Content-Type": "text/csv"}
    )
    assert (again.json()["inserted"], again.json()["skipped"]) == (0, 2)


def test_events_are_filtered_and_tenant_scoped(client: TestClient) -> None:
    mine = client.get("/v1/ledger/events", params={"type": "bank_line"}, headers=HEADERS).json()
    assert [e["narration"] for e in mine["events"]] == [
        "CASH DEPOSIT BR01 SLIP 00001",
        "BANK CHARGES OCT-2026",
    ]
    other = client.get(
        "/v1/ledger/events",
        params={"type": "bank_line"},
        headers={"X-Fiona-Tenant": "ten_someone_else"},
    ).json()
    assert other["events"] == []


def test_wallet_refuses_without_a_verdict_and_audits_it(client: TestClient) -> None:
    body = {
        "proposal_id": "prop_missing",
        "verdict_id": "vrd_missing",
        "payee_id": "sup_001",
        "amount_minor": 1000,
        "currency": "PKR",
        "pay_on": "2026-10-22",
    }
    paid = client.post("/v1/wallet/pay", json=body, headers=HEADERS).json()
    assert (paid["status"], paid["label"]) == ("refused", "SIMULATED")
    assert paid["reason"].startswith("NO_PROPOSAL")
    audit = client.get("/v1/audit", params={"proposal_id": "prop_missing"}, headers=HEADERS).json()
    assert audit["verified"] is True and audit["first_bad_seq"] is None
    assert audit["records"][-1]["record"]["action"] == "payment_refused"


def test_tenant_never_comes_from_the_body(client: TestClient) -> None:
    body = {
        "proposal_id": "prop_x",
        "verdict_id": "vrd_x",
        "payee_id": "sup_001",
        "amount_minor": 1,
        "currency": "PKR",
        "pay_on": "2026-10-22",
        "tenant_id": "ten_karachi_apparel",
    }
    client.post("/v1/wallet/pay", json=body, headers=HEADERS)
    audit = client.get("/v1/audit", headers={"X-Fiona-Tenant": "ten_karachi_apparel"}).json()
    assert all(r["proposal_id"] != "prop_x" for r in audit["records"])
