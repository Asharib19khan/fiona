"""Tests for persistent proposals and decisions API (Task A)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from engine.app.main import app
from engine.ledger import api, db
from engine.wallet.tests.conftest import (
    CAP,
    TODAY,
    seed_wallet_tenant,
)

TENANT = "ten_proposals_test"
HEADERS = {"X-Fiona-Tenant": TENANT}
CLOCK = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def client(migrated_db: str) -> Iterator[TestClient]:
    with db.connect(migrated_db, autocommit=True) as conn:
        seed_wallet_tenant(conn, TENANT)
        with db.tenant_session(conn, TENANT):
            conn.execute(
                "update parties set tax_id = '4417023-6', tax_id_type = 'NTN' where id = 'sup_001'"
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


def test_create_and_fetch_proposal(client: TestClient) -> None:
    draft = {
        "agent": "treasurer",
        "type": "payment",
        "summary": "Pay verified supplier utilities",
        "amount": {"minor": 5_000_000, "currency": "PKR"},
        "payload": {
            "payee_id": "sup_001",
            "bill_id": "bill_001",
            "category": "utilities",
            "contract_ref": "cnt_util_001",
            "pay_on": TODAY,
            "channel": "wallet",
        },
        "evidence": [
            {"kind": "ledger_row", "ref": "bill_001"},
            {"kind": "document", "ref": "doc_001"},
        ],
        "reasoning": "Within Treasurer mandate; utilities contract.",
        "mandate_ref": "man_treasurer",
        "created_by": {"kind": "agent", "id": "treasurer"},
    }

    create_res = client.post("/v1/proposals", json=draft, headers=HEADERS)
    assert create_res.status_code == 201, create_res.text
    data = create_res.json()
    assert data["api_version"] == "v1"
    proposal = data["proposal"]
    verdict = data["verdict"]

    assert proposal["id"].startswith("prop_")
    assert proposal["status"] == "cleared"  # Within cap and allow-listed
    assert verdict["outcome"] == "approve"
    assert verdict["verdict_hash"].startswith("sha256:")

    # Fetch by ID
    get_res = client.get(f"/v1/proposals/{proposal['id']}", headers=HEADERS)
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["id"] == proposal["id"]
    assert fetched["status"] == "cleared"
    assert fetched["verdict"]["id"] == verdict["id"]

    # Appears in list
    list_res = client.get("/v1/proposals", headers=HEADERS)
    assert list_res.status_code == 200
    proposals_list = list_res.json()["proposals"]
    assert any(p["id"] == proposal["id"] for p in proposals_list)


def test_escalated_proposal_needs_owner_and_approves(client: TestClient) -> None:
    # Over payment cap -> G-01 triggers escalate
    over_cap_amount = CAP + 10_000_000
    draft = {
        "agent": "treasurer",
        "type": "payment",
        "summary": "Large seasonal inventory payment",
        "amount": {"minor": over_cap_amount, "currency": "PKR"},
        "payload": {
            "payee_id": "sup_001",
            "bill_id": "bill_large",
            "pay_on": TODAY,
            "channel": "wallet",
        },
        "evidence": [
            {"kind": "ledger_row", "ref": "bill_large"},
            {"kind": "document", "ref": "doc_large"},
        ],
        "reasoning": "Seasonal order exceeds cap.",
        "mandate_ref": "man_treasurer",
        "created_by": {"kind": "user", "id": "usr_finance_01"},
    }

    res = client.post("/v1/proposals", json=draft, headers=HEADERS)
    assert res.status_code == 201
    proposal = res.json()["proposal"]
    verdict = res.json()["verdict"]
    assert verdict["outcome"] == "escalate"
    assert proposal["status"] == "needs_owner"

    # Filter needs_owner=true includes this proposal
    needs_owner_res = client.get("/v1/proposals?needs_owner=true", headers=HEADERS)
    assert any(p["id"] == proposal["id"] for p in needs_owner_res.json()["proposals"])

    # Maker-checker (G-04): proposer cannot approve their own proposal
    decide_fail = client.post(
        f"/v1/proposals/{proposal['id']}/decision",
        json={"decision": "approve", "note": "Trying to self-approve"},
        headers={**HEADERS, "x-user-id": "usr_finance_01"},
    )
    assert decide_fail.status_code == 400
    assert "maker_checker" in decide_fail.json()["error"]["code"]

    # Owner approves
    decide_res = client.post(
        f"/v1/proposals/{proposal['id']}/decision",
        json={"decision": "approve", "note": "Approved by owner"},
        headers={**HEADERS, "x-user-id": "usr_owner_01"},
    )
    assert decide_res.status_code == 200, decide_res.text
    dec_data = decide_res.json()
    assert dec_data["proposal_status"] == "approved"
    assert dec_data["decision"]["decision"] == "approve"

    # Status is now approved
    updated = client.get(f"/v1/proposals/{proposal['id']}", headers=HEADERS).json()
    assert updated["status"] == "approved"
    assert len(updated["decisions"]) == 1

    # Wallet executes released payment
    pay_res = client.post(
        "/v1/wallet/pay",
        json={
            "proposal_id": proposal["id"],
            "verdict_id": verdict["id"],
            "payee_id": "sup_001",
            "amount_minor": over_cap_amount,
            "currency": "PKR",
            "pay_on": TODAY,
        },
        headers=HEADERS,
    )
    assert pay_res.status_code == 200, pay_res.text
    assert pay_res.json()["status"] == "executed"

    # Status is now projected as executed
    after_pay = client.get(f"/v1/proposals/{proposal['id']}", headers=HEADERS).json()
    assert after_pay["status"] == "executed"


def test_cannot_override_blocked_proposal(client: TestClient) -> None:
    # sup_017 has bank change confirmed via email within cooling-off -> G-03 triggers block
    draft = {
        "agent": "treasurer",
        "type": "payment",
        "summary": "Payment to vendor with unconfirmed bank change",
        "amount": {"minor": 100_000, "currency": "PKR"},
        "payload": {
            "payee_id": "sup_017",  # Bank detail change within cooling off, email-only
            "bill_id": "bill_bad",
            "pay_on": TODAY,
            "channel": "wallet",
        },
        "evidence": [{"kind": "ledger_row", "ref": "bill_bad"}],
        "reasoning": "Unconfirmed supplier attempt.",
        "mandate_ref": "man_treasurer",
        "created_by": {"kind": "agent", "id": "treasurer"},
    }

    res = client.post("/v1/proposals", json=draft, headers=HEADERS)
    assert res.status_code == 201
    proposal = res.json()["proposal"]
    assert proposal["status"] == "blocked"
    assert res.json()["verdict"]["outcome"] == "block"

    # Attempt to approve blocked proposal fails
    decide_res = client.post(
        f"/v1/proposals/{proposal['id']}/decision",
        json={"decision": "approve"},
        headers={**HEADERS, "x-user-id": "usr_owner_01"},
    )
    assert decide_res.status_code == 400
    assert decide_res.json()["error"]["code"] == "cannot_override_block"
