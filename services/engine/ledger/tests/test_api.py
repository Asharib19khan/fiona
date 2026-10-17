"""The ledger, import, wallet and audit endpoints, through the real app (router auto-discovery)."""

from __future__ import annotations

import base64
import hashlib
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


def test_reconciliation_findings_are_ranked_by_amount(client: TestClient) -> None:
    response = client.get("/v1/reconcile/findings", headers=HEADERS)
    assert response.status_code == 200, response.text
    findings = response.json()["findings"]
    assert [finding["money_at_stake"]["minor"] for finding in findings] == [50_000, 2_500]
    assert all(finding["source"] == "reconciliation" for finding in findings)


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


def test_bill_duplicate_check_is_read_only(client: TestClient) -> None:
    document = b"same synthetic bill document"
    digest = hashlib.sha256(document).hexdigest()
    bills = [
        {
            "bill_id": bill_id,
            "supplier_id": "sup_001",
            "number": "SYN-100",
            "issue_date": "2026-10-20",
            "due_date": "2026-10-30",
            "po_number": "PO-100",
            "lines": [],
            "subtotal_minor": 125_000,
            "tax": [],
            "total_minor": 125_000,
            "document_id": f"doc_{index}",
            "document_path": f"{bill_id}.txt",
            "document_sha256": digest,
            "currency": "PKR",
            "received_at": "2026-10-22T09:00:00Z",
        }
        for index, bill_id in enumerate(("bill_duplicate_prior", "bill_duplicate_current"), start=1)
    ]
    imported = client.post(
        "/v1/import/bills",
        json={
            "bills": bills,
            "documents": {
                "bill_duplicate_prior.txt": base64.b64encode(document).decode("ascii"),
                "bill_duplicate_current.txt": base64.b64encode(document).decode("ascii"),
            },
        },
        headers=HEADERS,
    )
    assert imported.status_code == 200, imported.text
    checked = client.post(
        "/v1/bills/check", json={"bill_id": "bill_duplicate_current"}, headers=HEADERS
    )
    assert checked.status_code == 200, checked.text
    result = checked.json()
    assert result["check"]["rule"] == "G-05"
    assert result["check"]["outcome"] == "block"
    assert result["check"]["audit"]["matched_bill_id"] == "bill_duplicate_prior"
