"""Integration tests for the complete end-to-end participation loop (Task B)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from engine.app.main import app
from engine.ledger import api, db
from engine.ledger.participation import run_full_participation_loop
from engine.ledger.review import record_review
from engine.wallet.audit import verify
from engine.wallet.tests.conftest import (
    CAP,
    TODAY,
    seed_wallet_tenant,
)

TENANT = "ten_participation_test"
TENANT_HTTP = "ten_part_http_test"
HEADERS = {"X-Fiona-Tenant": TENANT}
HEADERS_HTTP = {"X-Fiona-Tenant": TENANT_HTTP}
CLOCK = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def seed_participation_tenant(conn: psycopg.Connection, tenant_id: str) -> None:
    row = conn.execute("select id from tenants where id = %s", (tenant_id,)).fetchone()
    if row:
        return
    seed_wallet_tenant(conn, tenant_id, payment_autonomy="prepare")  # the persona default
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            """
            insert into accounts (tenant_id, code, name, class, neutral_class) values
            (%s, '1200', 'Inventory', 'asset', 'inventory'),
            (%s, '1300', 'Input tax', 'asset', 'tax'),
            (%s, '6600', 'Supplies', 'expense', 'expenses')
            on conflict do nothing
            """,
            (tenant_id, tenant_id, tenant_id),
        )
        conn.execute(
            "update parties set tax_id = '4417023-6', tax_id_type = 'NTN' where id = 'sup_001'"
        )


@pytest.fixture(scope="module", autouse=True)
def setup_tenant(migrated_db: str) -> None:
    with db.connect(migrated_db, autocommit=True) as conn:
        seed_participation_tenant(conn, TENANT)
        seed_participation_tenant(conn, TENANT_HTTP)


@pytest.fixture(scope="module")
def client(migrated_db: str) -> Iterator[TestClient]:
    def conn_override() -> Iterator[psycopg.Connection]:
        with db.connect(migrated_db, autocommit=True) as connection:
            yield connection

    app.dependency_overrides[api.get_conn] = conn_override
    app.dependency_overrides[api.get_clock] = lambda: CLOCK
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _guardian_reviews(conn, result: dict) -> None:
    """The Guardian service's model review (G-12) arrives; the wallet pays nothing before it."""
    record_review(
        conn,
        TENANT,
        result["proposal"]["id"],
        result["verdict"]["id"],
        {"concern": "none", "reasons": [], "injection_detected": False},
        now=CLOCK,
    )


def test_participation_loop_cleared_waits_for_owner_then_executes(migrated_db: str) -> None:
    """A compliant bill within mandate clears, but the Treasurer prepares (persona default):
    nothing pays until the owner approves, then the full loop runs."""
    with db.connect(migrated_db, autocommit=True) as conn:
        bill = {
            "id": "bill_auto_001",
            "supplier_id": "sup_001",
            "number": "INV-UTIL-001",
            "total_minor": 4_500_000,
            "subtotal_minor": 4_000_000,
            "tax_minor": 500_000,
            "category": "utilities",
            "contract_ref": "cnt_util_001",
            "issue_date": TODAY,
            "due_date": TODAY,
        }

        waiting = run_full_participation_loop(conn, TENANT, bill, now=CLOCK)
        assert waiting["verdict"]["outcome"] == "approve"
        assert waiting["status"] == "needs_owner"
        assert waiting["wallet_payment"] is None
        _guardian_reviews(conn, waiting)

        result = run_full_participation_loop(
            conn,
            TENANT,
            bill,
            owner_approval={
                "decision": "approve",
                "note": "Utilities bill checked.",
                "decided_by": "usr_owner_01",
            },
            now=CLOCK,
        )

        # 1. Proposal and verdict
        assert result["status"] == "executed"
        assert result["verdict"]["outcome"] == "approve"
        assert result["proposal"]["status"] == "executed"

        # 2. Document and intake
        intake = result["intake"]
        assert intake["document_id"].startswith("doc_")
        assert len(intake["document_sha256"]) == 64

        # 3. Sandbox wallet execution
        wallet_payment = result["wallet_payment"]
        assert wallet_payment is not None
        assert wallet_payment["status"] == "executed"
        assert wallet_payment["amount_minor"] == 4_500_000

        # 4. Double-entry ledger verification (Dr 2000 Payables / Cr 1000 Cash)
        journal_lines = result["journal_lines"]
        assert len(journal_lines) == 2
        debit_line = next(j for j in journal_lines if j["debit_minor"] > 0)
        credit_line = next(j for j in journal_lines if j["credit_minor"] > 0)
        assert debit_line["account_code"] == "2000"
        assert debit_line["debit_minor"] == 4_500_000
        assert credit_line["account_code"] == "1000"
        assert credit_line["credit_minor"] == 4_500_000

        # 5. SHA-256 audit chain verification
        audit = result["audit_chain"]
        assert audit["verified"] is True
        assert audit["first_bad_seq"] is None
        assert audit["length"] >= 2


def test_participation_loop_escalated_and_owner_approved_flow(migrated_db: str) -> None:
    """Over-cap bill escalates to owner, executes after approval, and verifies audit chain."""
    with db.connect(migrated_db, autocommit=True) as conn:
        over_cap_amount = CAP + 8_000_000  # 23_000_000 PKR
        bill = {
            "id": "bill_large_002",
            "supplier_id": "sup_001",
            "number": "INV-LARGE-002",
            "total_minor": over_cap_amount,
            "subtotal_minor": over_cap_amount - 1_000_000,
            "tax_minor": 1_000_000,
            "category": "utilities",
            "contract_ref": "cnt_util_002",
            "issue_date": TODAY,
            "due_date": TODAY,
        }

        # First attempt: without owner approval -> status is needs_owner
        unapproved = run_full_participation_loop(conn, TENANT, bill, now=CLOCK)
        assert unapproved["status"] == "needs_owner"
        assert unapproved["verdict"]["outcome"] == "escalate"
        assert unapproved["wallet_payment"] is None
        _guardian_reviews(conn, unapproved)

        # Second run: with owner approval -> executed
        approved_result = run_full_participation_loop(
            conn,
            TENANT,
            bill,
            owner_approval={
                "decision": "approve",
                "note": "Owner approves seasonal payment above cap.",
                "decided_by": "usr_owner_01",
            },
            now=CLOCK,
        )

        assert approved_result["status"] == "executed"
        assert approved_result["decision"] is not None
        assert approved_result["decision"]["decision"]["decision"] == "approve"
        assert approved_result["wallet_payment"] is not None
        assert approved_result["wallet_payment"]["status"] == "executed"

        # Audit chain intact across all steps
        assert approved_result["audit_chain"]["verified"] is True


def test_participation_loop_blocked_prevents_payment(migrated_db: str) -> None:
    """Unconfirmed cooling-off bank change blocks proposal and prevents payment execution."""
    with db.connect(migrated_db, autocommit=True) as conn:
        bill = {
            "id": "bill_blocked_003",
            "supplier_id": "sup_017",  # unconfirmed email bank change within cooling off
            "number": "INV-BLOCKED-003",
            "total_minor": 500_000,
            "subtotal_minor": 450_000,
            "tax_minor": 50_000,
            "issue_date": TODAY,
            "due_date": TODAY,
        }

        result = run_full_participation_loop(conn, TENANT, bill, now=CLOCK)
        assert result["status"] == "blocked"
        assert result["verdict"]["outcome"] == "block"
        assert result["wallet_payment"] is None
        assert len(result["journal_lines"]) == 0

        # Audit chain intact
        verify_res = verify(conn, TENANT)
        assert verify_res.ok is True


def test_participation_loop_http_api(client: TestClient) -> None:
    """Test POST /v1/participation/run HTTP endpoint."""
    bill = {
        "id": "bill_http_004",
        "supplier_id": "sup_001",
        "number": "INV-HTTP-004",
        "total_minor": 2_000_000,
        "subtotal_minor": 1_800_000,
        "tax_minor": 200_000,
        "category": "utilities",
        "contract_ref": "cnt_util_004",
        "issue_date": TODAY,
        "due_date": TODAY,
    }

    res = client.post("/v1/participation/run", json={"bill": bill}, headers=HEADERS_HTTP)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "needs_owner"
    assert res.json()["wallet_payment"] is None
    reviewed = client.post(
        f"/v1/proposals/{res.json()['proposal']['id']}/review",
        json={
            "reviewed_verdict_id": res.json()["verdict"]["id"],
            "concern": "none",
            "reasons": [],
            "injection_detected": False,
        },
        headers={**HEADERS_HTTP, "X-Fiona-Agent": "guardian"},
    )
    assert reviewed.status_code == 200, reviewed.text

    approval = {"decision": "approve", "note": "Checked.", "decided_by": "usr_owner"}
    as_agent = {**HEADERS_HTTP, "X-Fiona-Agent": "treasurer"}
    res = client.post(
        "/v1/participation/run", json={"bill": bill, "owner_approval": approval}, headers=as_agent
    )
    assert res.status_code == 403, res.text  # an agent cannot approve, whatever the body says

    as_owner = {**HEADERS_HTTP, "X-User-Id": "usr_owner_01"}
    res = client.post(
        "/v1/participation/run", json={"bill": bill, "owner_approval": approval}, headers=as_owner
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["api_version"] == "v1"
    assert data["decision"]["decision"]["decided_by"] == "usr_owner_01"  # the caller, not the body
    assert data["status"] == "executed"
    assert data["verdict"]["outcome"] == "approve"
    assert data["wallet_payment"]["status"] == "executed"
    assert data["audit_chain"]["verified"] is True
