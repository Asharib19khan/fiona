"""Generate submission execution evidence for ten_karachi_apparel (Deliverable 06)."""

from __future__ import annotations

import json
import shutil
import tempfile
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure `services/` is in sys.path so `engine.*` packages are importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))

from engine.ledger import db
from engine.wallet.audit import append, verify
from engine.wallet.oplog import export_operation_log
from engine.wallet.wallet import PaymentRequest, execute_payment, open_account
from fiona_contracts.hashing import verdict_hash

T0 = "2026-10-22T09:00:00Z"
NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
TODAY = "2026-10-22"
TENANT_ID = "ten_karachi_apparel"


def store_proposal(
    conn,
    tenant_id: str,
    prop_id: str,
    amount_minor: int,
    payee_id: str,
    bill_id: str,
    summary: str,
    doc_ref: str,
) -> None:
    with db.tenant_session(conn, tenant_id):
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM public.proposals WHERE tenant_id = %s AND id = %s", (tenant_id, prop_id)
        )
        if cur.fetchone():
            return
        conn.execute(
            """
            INSERT INTO public.proposals (
                tenant_id, id, agent, type, created_at, summary, amount_minor, currency, payload, evidence, reasoning, created_by
            ) VALUES (
                %s, %s, 'treasurer', 'payment', %s, %s, %s, 'PKR',
                %s, %s, 'Supplier bill awaiting payment', %s
            ) ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (
                tenant_id,
                prop_id,
                T0,
                summary,
                amount_minor,
                json.dumps(
                    {"payee_id": payee_id, "bill_id": bill_id, "pay_on": TODAY, "channel": "wallet"}
                ),
                json.dumps([{"kind": "document", "ref": doc_ref}]),
                json.dumps({"kind": "agent", "id": "treasurer"}),
            ),
        )
        append(
            conn,
            tenant_id,
            {
                "event": "proposal_created",
                "proposal_id": prop_id,
                "agent": "treasurer",
                "amount_minor": amount_minor,
                "payee_id": payee_id,
                "bill_id": bill_id,
            },
            proposal_id=prop_id,
            now=NOW,
        )


def store_verdict(
    conn, tenant_id: str, prop_id: str, verdict_id: str, outcome: str, checks: list[dict]
) -> None:
    body = {
        "id": verdict_id,
        "proposal_id": prop_id,
        "outcome": outcome,
        "checks": checks,
        "conditions": [],
        "decided_at": T0,
        "policy_version": "1.0.0",
    }
    digest = verdict_hash(body)
    with db.tenant_session(conn, tenant_id):
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM public.verdicts WHERE tenant_id = %s AND id = %s",
            (tenant_id, verdict_id),
        )
        if cur.fetchone():
            return
        conn.execute(
            """
            INSERT INTO public.verdicts (
                tenant_id, id, proposal_id, outcome, checks, conditions, decided_at, verdict_hash, policy_version, body
            ) VALUES (%s, %s, %s, %s, %s, '[]', %s, %s, '1.0.0', %s)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (
                tenant_id,
                verdict_id,
                prop_id,
                outcome,
                json.dumps(checks),
                T0,
                digest,
                json.dumps(body),
            ),
        )
        append(
            conn,
            tenant_id,
            {
                "event": "verdict_rendered",
                "proposal_id": prop_id,
                "verdict_id": verdict_id,
                "outcome": outcome,
                "checks_count": len(checks),
            },
            proposal_id=prop_id,
            now=NOW,
        )


def store_decision(
    conn, tenant_id: str, prop_id: str, verdict_id: str, decided_by: str, note: str
) -> None:
    dec_id = f"dec_{prop_id}_{decided_by}"
    with db.tenant_session(conn, tenant_id):
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM public.decisions WHERE tenant_id = %s AND id = %s", (tenant_id, dec_id)
        )
        if cur.fetchone():
            return
        conn.execute(
            """
            INSERT INTO public.decisions (
                tenant_id, id, proposal_id, verdict_id, decision, decided_by, decided_at, note
            ) VALUES (%s, %s, %s, %s, 'approve', %s, %s, %s)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tenant_id, dec_id, prop_id, verdict_id, decided_by, T0, note),
        )
        append(
            conn,
            tenant_id,
            {
                "event": "owner_decision",
                "proposal_id": prop_id,
                "verdict_id": verdict_id,
                "decision": "approve",
                "decided_by": decided_by,
                "note": note,
            },
            proposal_id=prop_id,
            now=NOW,
        )


def populate_and_export() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    dest_dir = repo_root / "docs" / "submission" / "06-execution-evidence"

    with db.connect("fiona_dev", autocommit=True) as conn:
        with db.tenant_session(conn, TENANT_ID):
            cur = conn.cursor()
            cur.execute("SELECT id FROM public.wallet_accounts WHERE tenant_id = %s", (TENANT_ID,))
            row = cur.fetchone()

        if not row:
            open_account(
                conn,
                TENANT_ID,
                iban="PK00SYNW0000000000000001",
                currency="PKR",
                opening_balance_minor=350_000_000,  # PKR 3.5M
                now=NOW,
            )
            print("[OK] Opened simulated wallet account with PKR 3,500,000 balance.")

        # ==============================================================
        # Transaction 1: DEMO-1 Fraud Block
        # ==============================================================
        prop_demo_1 = "prop_demo01"
        ver_demo_1 = "vrd_demo01"
        amount_demo_1 = 18_450_000  # PKR 184,500

        store_proposal(
            conn,
            TENANT_ID,
            prop_demo_1,
            amount_demo_1,
            "sup_017",
            "bill_2231",
            "Re-sent invoice INV-2231 (Mehran Garments)",
            "doc_88",
        )
        store_verdict(
            conn,
            TENANT_ID,
            prop_demo_1,
            ver_demo_1,
            "block",
            [
                {
                    "name": "policy",
                    "rule": "G-01",
                    "result": "fail",
                    "outcome": "escalate",
                    "detail": "Amount PKR 184,500 exceeds per-payment cap PKR 150,000",
                },
                {
                    "name": "payee",
                    "rule": "G-03",
                    "result": "fail",
                    "outcome": "block",
                    "detail": "Bank details changed 2 days ago via unconfirmed email",
                },
                {
                    "name": "duplicate",
                    "rule": "G-05",
                    "result": "fail",
                    "outcome": "block",
                    "detail": "Normalized invoice ID INV2231 identical to settled bill_2188",
                },
                {
                    "name": "arithmetic",
                    "rule": "G-07",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Lines and GST 1800 bp balance arithmetic verified",
                },
                {
                    "name": "matching",
                    "rule": "G-09",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Three-way match verified against PO and GRN",
                },
                {
                    "name": "adversarial",
                    "rule": "G-12",
                    "result": "fail",
                    "outcome": "escalate",
                    "detail": "Adversarial scan detected urgency coercion: 'Pay urgently or stock will be withheld'",
                },
            ],
        )

        res_demo_1 = execute_payment(
            conn,
            TENANT_ID,
            PaymentRequest(
                proposal_id=prop_demo_1,
                verdict_id=ver_demo_1,
                payee_id="sup_017",
                amount_minor=amount_demo_1,
                currency="PKR",
                pay_on=TODAY,
            ),
            now=NOW,
        )
        print(
            f"[OK] DEMO-1 wallet execution result: {res_demo_1.status} (Reason: {res_demo_1.reason})"
        )

        # ==============================================================
        # Transaction 2: S-01 Legitimate High-Value Payment (Escalate -> Human Approval -> Paid)
        # ==============================================================
        prop_s01 = "prop_s01"
        ver_s01 = "vrd_s01"
        amount_s01 = 28_036_800  # PKR 280,368

        store_proposal(
            conn,
            TENANT_ID,
            prop_s01,
            amount_s01,
            "sup_001",
            "bill_2240",
            "Batch payment for raw cotton fabric (sup_001)",
            "doc_95",
        )
        store_verdict(
            conn,
            TENANT_ID,
            prop_s01,
            ver_s01,
            "escalate",
            [
                {
                    "name": "policy",
                    "rule": "G-01",
                    "result": "fail",
                    "outcome": "escalate",
                    "detail": "Amount PKR 280,368 exceeds per-payment cap PKR 150,000",
                },
                {
                    "name": "payee",
                    "rule": "G-02",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Payee sup_001 is on allow-list",
                },
                {
                    "name": "payee",
                    "rule": "G-03",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Bank account verified and unchanged",
                },
                {
                    "name": "duplicate",
                    "rule": "G-05",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Invoice number verified unique across tenant ledger",
                },
                {
                    "name": "arithmetic",
                    "rule": "G-07",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Invoice arithmetic and tax calculation verified",
                },
                {
                    "name": "matching",
                    "rule": "G-09",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Three-way match verified against PO-4481 and GRN-4481",
                },
            ],
        )
        store_decision(
            conn,
            TENANT_ID,
            prop_s01,
            ver_s01,
            "usr_owner_01",
            "Approved fabric batch payment exceeding Treasurer cap",
        )

        res_s01 = execute_payment(
            conn,
            TENANT_ID,
            PaymentRequest(
                proposal_id=prop_s01,
                verdict_id=ver_s01,
                payee_id="sup_001",
                amount_minor=amount_s01,
                currency="PKR",
                pay_on=TODAY,
            ),
            now=NOW,
        )
        print(
            f"[OK] S-01 wallet execution result: {res_s01.status} (Wallet Ref: {res_s01.wallet_ref})"
        )

        # ==============================================================
        # Transaction 3: C-01 Autonomous Payment Within Mandate
        # ==============================================================
        prop_c01 = "prop_c01"
        ver_c01 = "vrd_c01"
        amount_c01 = 8_500_000  # PKR 85,000

        store_proposal(
            conn,
            TENANT_ID,
            prop_c01,
            amount_c01,
            "sup_001",
            "bill_2235",
            "Monthly trims and packaging supplies (sup_001)",
            "doc_92",
        )
        store_verdict(
            conn,
            TENANT_ID,
            prop_c01,
            ver_c01,
            "approve",
            [
                {
                    "name": "policy",
                    "rule": "G-01",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Amount PKR 85,000 within per-payment cap PKR 150,000",
                },
                {
                    "name": "payee",
                    "rule": "G-02",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Payee sup_001 on allow-list",
                },
                {
                    "name": "duplicate",
                    "rule": "G-05",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Invoice number verified unique",
                },
                {
                    "name": "arithmetic",
                    "rule": "G-07",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Balance and GST verified",
                },
                {
                    "name": "matching",
                    "rule": "G-09",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Three-way match verified",
                },
                {
                    "name": "mandate",
                    "rule": "G-13",
                    "result": "pass",
                    "outcome": "pass",
                    "detail": "Payment action permitted by Treasurer mandate",
                },
            ],
        )

        res_c01 = execute_payment(
            conn,
            TENANT_ID,
            PaymentRequest(
                proposal_id=prop_c01,
                verdict_id=ver_c01,
                payee_id="sup_001",
                amount_minor=amount_c01,
                currency="PKR",
                pay_on=TODAY,
            ),
            now=NOW,
        )
        print(
            f"[OK] C-01 autonomous execution result: {res_c01.status} (Wallet Ref: {res_c01.wallet_ref})"
        )

        # Verify audit chain in database
        v_result = verify(conn, TENANT_ID)
        print(f"[OK] DB Audit chain verification: ok={v_result.ok}, length={v_result.length}")
        assert v_result.ok is True

        # Export operation log to temporary directory
        with tempfile.TemporaryDirectory(prefix="fiona-oplog-") as tmpdir:
            export_operation_log(conn, TENANT_ID, tmpdir)
            tmppath = Path(tmpdir)

            for fname in ("operations.jsonl", "audit_chain.jsonl", "verification_report.json"):
                src_file = tmppath / fname
                dst_file = dest_dir / fname
                shutil.copy2(src_file, dst_file)
                print(f"[OK] Exported {dst_file.name} ({dst_file.stat().st_size} bytes)")

    print("[SUCCESS] Deliverable 06 execution evidence successfully generated and verified!")


if __name__ == "__main__":
    populate_and_export()
