"""End-to-end participation loop wiring (Task B / Scored Core 1).

Orchestrates the canonical Fiona participation loop:
1. Bill extraction / intake -> stores document (SHA-256) & purchase_bill event.
2. Posts purchase bill to double-entry ledger (Dr 1200 Inventory / Dr 1300 Tax / Cr 2000 Payables).
3. Treasurer agent proposes payment within or outside mandate cap.
4. Guardian deterministic checks evaluate proposal & generate SHA-256 hashed verdict.
5. Audit log appends proposal_submitted to the tamper-evident hash chain.
6. If cleared: sandbox wallet executes payment directly.
   If escalated: owner reviews & records decision (maker-checker enforced), then wallet executes.
   If blocked: payment is strictly prevented.
7. Wallet payment inserts supplier_payment event & posts to ledger (Dr 2000 Payables / Cr 1000 Cash).
8. Audit log appends payment_executed, and full SHA-256 audit chain is cryptographically verified.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from engine.app.errors import ApiError
from engine.ledger import db, proposals
from engine.ledger.ids import encode_ulid
from engine.ledger.posting import PostingContext, post_event_in_session
from engine.wallet.audit import verify
from engine.wallet.wallet import PaymentRequest, execute_payment
from fiona_contracts.models import DecisionRequest, ProposalDraft

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _ulid(prefix: str, moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    ms = (moment - EPOCH) // timedelta(milliseconds=1)
    randomness = secrets.token_bytes(10)
    return f"{prefix}_{encode_ulid(ms, randomness)}"


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    s = str(dt)
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s


def record_bill_intake(
    conn: psycopg.Connection,
    tenant_id: str,
    bill: dict[str, Any],
    *,
    document_bytes: bytes | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Store extracted bill document, emit purchase_bill event, and post to ledger."""
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    with db.tenant_session(conn, tenant_id):
        # 1. Resolve document SHA-256 and store in documents table
        doc_bytes = document_bytes or json.dumps(bill, sort_keys=True).encode("utf-8")
        doc_sha256 = bill.get("document_sha256") or hashlib.sha256(doc_bytes).hexdigest()
        doc_id = bill.get("document_id") or _ulid("doc", now)

        conn.execute(
            """
            insert into documents (
                tenant_id, id, kind, storage_path, sha256, mime_type, size_bytes,
                extracted, received_at
            ) values (%s, %s, 'bill', %s, %s, %s, %s, %s, %s)
            on conflict (tenant_id, id) do nothing
            """,
            (
                tenant_id,
                doc_id,
                f"bills/{tenant_id}/{doc_id}.pdf",
                doc_sha256,
                "application/pdf",
                len(doc_bytes),
                json.dumps(bill),
                now,
            ),
        )

        # 2. Extract key fields
        bill_id = bill.get("id") or bill.get("bill_id") or _ulid("bill", now)
        supplier_id = bill.get("supplier_id") or bill.get("payee_id")
        if not supplier_id:
            raise ApiError(400, "missing_supplier", "Bill must specify supplier_id.")

        currency = bill.get("currency") or "PKR"
        total_minor = int(bill.get("total_minor") or bill.get("amount_minor") or 0)
        tax_minor = int(bill.get("tax_minor") or 0)
        subtotal_minor = int(bill.get("subtotal_minor") or (total_minor - tax_minor))
        number = bill.get("number") or bill.get("invoice_number") or f"INV-{bill_id}"
        issue_date = bill.get("issue_date") or bill.get("date") or str(now.date())
        due_date = bill.get("due_date") or issue_date
        category = bill.get("category") or "inventory_supplier"

        # Check if bill was already recorded (idempotent on source_type, source_key)
        source_key = f"bill:{bill_id}"
        existing_event = conn.execute(
            """
            select id, payload from events
            where tenant_id = %s and source_type = 'extraction' and source_key = %s
            """,
            (tenant_id, source_key),
        ).fetchone()

        if existing_event:
            evt_id = existing_event[0]
            evt_payload = existing_event[1] if isinstance(existing_event[1], dict) else {}
            return {
                "document_id": evt_payload.get("document_id") or doc_id,
                "document_sha256": evt_payload.get("document_sha256") or doc_sha256,
                "bill_id": bill_id,
                "event_id": evt_id,
                "supplier_id": supplier_id,
                "number": number,
                "total_minor": total_minor,
                "currency": currency,
                "category": category,
                "contract_ref": bill.get("contract_ref"),
                "po_id": bill.get("po_id"),
                "grn_id": bill.get("grn_id"),
            }

        # 3. Insert purchase_bill event
        event_id = _ulid("evt", now)
        lines = bill.get("lines")
        if not lines:
            lines = [{"sku": bill.get("sku", "ITEM_001"), "line_total_minor": subtotal_minor}]
        event_payload = {
            "bill_id": bill_id,
            "party": supplier_id,
            "supplier_id": supplier_id,
            "document_id": doc_id,
            "document_sha256": doc_sha256,
            "number": number,
            "lines": lines,
            "total_minor": total_minor,
            "subtotal_minor": subtotal_minor,
            "tax_minor": tax_minor,
            "currency": currency,
            "issue_date": issue_date,
            "due_date": due_date,
            "category": category,
            "contract_ref": bill.get("contract_ref"),
            "po_id": bill.get("po_id"),
            "grn_id": bill.get("grn_id"),
        }

        conn.execute(
            """
            insert into events (
                tenant_id, id, type, occurred_at, business_date, recorded_at,
                party_id, currency, payload, source
            ) values (%s, %s, 'purchase_bill', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                event_id,
                now,
                issue_date,
                now,
                supplier_id,
                currency,
                json.dumps(event_payload),
                json.dumps({"type": "extraction", "key": f"bill:{bill_id}"}),
            ),
        )

        # 4. Post double-entry journal lines (Dr 1200 / Dr 1300 / Cr 2000)
        post_event_in_session(conn, tenant_id, event_id, PostingContext(), now=now)

    return {
        "document_id": doc_id,
        "document_sha256": doc_sha256,
        "bill_id": bill_id,
        "event_id": event_id,
        "supplier_id": supplier_id,
        "number": number,
        "total_minor": total_minor,
        "currency": currency,
        "category": category,
        "contract_ref": bill.get("contract_ref"),
        "po_id": bill.get("po_id"),
        "grn_id": bill.get("grn_id"),
    }


def run_full_participation_loop(
    conn: psycopg.Connection,
    tenant_id: str,
    bill: dict[str, Any],
    *,
    owner_approval: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Execute the complete end-to-end participation loop.

    Steps:
    1. Bill extraction & intake (documents + purchase_bill event + ledger posting).
    2. Treasurer generates payment proposal.
    3. Guardian evaluates deterministic checks (G-01..G-13) and signs verdict.
    4. Audit log stores proposal_submitted in hash chain.
    5. If escalated and owner_approval provided: records owner decision with maker-checker.
    6. If cleared or approved: executes wallet payment, posts supplier_payment to ledger,
       and records payment_executed in audit chain.
    7. Cryptographically verifies the entire tenant audit chain with SHA-256.
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    # Step 1: Record bill intake & post bill to ledger
    intake = record_bill_intake(conn, tenant_id, bill, now=now)

    # Step 2 & 3: Check for existing proposal or create new proposal
    existing_prop = conn.execute(
        """
        select id from proposals
        where tenant_id = %s and payload->>'bill_id' = %s
        order by created_at desc limit 1
        """,
        (tenant_id, intake["bill_id"]),
    ).fetchone()

    if existing_prop:
        stored_prop = proposals.get_proposal(conn, tenant_id, existing_prop[0])
        proposal = stored_prop or {}
        verdict = proposal.get("verdict") or {}
    else:
        proposal_draft = {
            "agent": "treasurer",
            "type": "payment",
            "summary": f"Payment for bill {intake['number']} to {intake['supplier_id']}",
            "amount": {"minor": intake["total_minor"], "currency": intake["currency"]},
            "payload": {
                "payee_id": intake["supplier_id"],
                "bill_id": intake["bill_id"],
                "category": intake["category"],
                "pay_on": str(now.date()),
                "channel": "wallet",
            },
            "evidence": [
                {"kind": "ledger_row", "ref": intake["bill_id"]},
                {"kind": "document", "ref": intake["document_id"]},
            ],
            "reasoning": f"Payment proposed for verified bill {intake['number']}.",
            "mandate_ref": "mnd_treasurer_v1",
            "created_by": {"kind": "agent", "id": "treasurer"},
        }

        proposal, verdict = proposals.create_proposal(
            conn,
            tenant_id,
            ProposalDraft(**proposal_draft),
            now=now,
        )

    decision_record: dict[str, Any] | None = None
    wallet_payment: dict[str, Any] | None = None

    # Step 5: Handle escalated proposals requiring owner review
    if proposal["status"] == "needs_owner" and owner_approval:
        dec_req = DecisionRequest(
            decision=owner_approval.get("decision", "approve"),
            note=owner_approval.get("note", "Approved via participation loop"),
            assertion=owner_approval.get("assertion"),
        )
        decision_record = proposals.record_owner_decision(
            conn,
            tenant_id,
            proposal["id"],
            dec_req,
            decided_by=owner_approval.get("decided_by", "usr_owner"),
            now=now,
        )
        # Re-fetch proposal after owner decision
        updated_p = proposals.get_proposal(conn, tenant_id, proposal["id"])
        if updated_p:
            proposal = updated_p

    # Step 6: If cleared or approved, execute sandbox wallet payment
    if proposal["status"] in ("cleared", "approved"):
        pay_req = PaymentRequest(
            proposal_id=proposal["id"],
            verdict_id=verdict["id"],
            payee_id=intake["supplier_id"],
            amount_minor=intake["total_minor"],
            currency=intake["currency"],
            pay_on=str(now.date()),
        )
        pay_res = execute_payment(
            conn,
            tenant_id,
            pay_req,
            now=now,
        )
        wallet_payment = {
            "status": pay_res.status,
            "reason": pay_res.reason,
            "payment_id": pay_res.payment_id,
            "wallet_ref": pay_res.wallet_ref,
            "event_id": pay_res.event_id,
            "amount_minor": pay_res.amount_minor,
            "label": pay_res.label,
        }
        # Update proposal state to projected executed
        updated_p = proposals.get_proposal(conn, tenant_id, proposal["id"])
        if updated_p:
            proposal = updated_p

    # Step 7: Cryptographic SHA-256 audit chain verification
    audit_verify = verify(conn, tenant_id)

    # Query posted journal lines for the payment if executed
    journal_lines = []
    if wallet_payment and wallet_payment.get("event_id"):
        j_rows = conn.execute(
            """
            select line_no, account_code, debit_minor, credit_minor, memo
            from journal_lines
            where tenant_id = %s and event_id = %s
            order by line_no
            """,
            (tenant_id, wallet_payment["event_id"]),
        ).fetchall()
        journal_lines = [
            {
                "line_no": r[0],
                "account_code": r[1],
                "debit_minor": r[2],
                "credit_minor": r[3],
                "memo": r[4],
            }
            for r in j_rows
        ]

    return {
        "status": proposal["status"],
        "intake": intake,
        "proposal": proposal,
        "verdict": verdict,
        "decision": decision_record,
        "wallet_payment": wallet_payment,
        "journal_lines": journal_lines,
        "audit_chain": {
            "verified": audit_verify.ok,
            "length": audit_verify.length,
            "first_bad_seq": audit_verify.first_bad_seq,
        },
    }
