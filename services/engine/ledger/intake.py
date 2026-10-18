"""Bills taken in from the web, suppliers to match them to, and the full trail of one proposal.

`intake_bill` records a bill a person confirmed after reading it (document, purchase_bill
event, ledger posting) through the same path the participation loop uses. The document's text
and anything the reader flagged (instructions embedded in the bill, a bank account that differs
from the one on file) are stored with it as data, so the Guardian's reviewer sees them.

`proposal_trace` gathers everything about one proposal in order: the bill and its document,
every verdict in the chain, the owner's decisions, the wallet payment, the journal lines for the
bill and the payment, and the audit records, with the chain verified.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any

import psycopg

from engine.app.errors import ApiError
from engine.ledger import db
from engine.ledger.ids import encode_ulid
from engine.ledger.participation import record_bill_intake
from engine.wallet.audit import verify

MAX_TEXT = 20_000


def search_parties(
    conn: psycopg.Connection, tenant_id: str, query: str, limit: int = 8
) -> list[dict[str, Any]]:
    q = query.strip()
    if len(q) < 2:
        return []
    with db.tenant_session(conn, tenant_id):
        rows = conn.execute(
            "select id, kind, name, tax_id, bank_iban, on_allow_list, bank_account_changed_at from parties"
            " where kind <> 'customer' and (name ilike %s or tax_id = %s or bank_iban = %s or id = %s)"
            " order by (tax_id = %s) desc, (bank_iban = %s) desc, name limit %s",
            (f"%{q}%", q, q.replace(" ", ""), q, q, q.replace(" ", ""), limit),
        ).fetchall()
    return [
        {
            "id": r[0],
            "kind": r[1],
            "name": r[2],
            "tax_id": r[3],
            "bank_iban": r[4],
            "on_allow_list": r[5],
            "bank_account_changed_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def intake_bill(
    conn: psycopg.Connection,
    tenant_id: str,
    bill: dict[str, Any],
    *,
    received_by: str,
    now: datetime,
) -> dict[str, Any]:
    supplier_id = str(bill.get("supplier_id") or "")
    with db.tenant_session(conn, tenant_id):
        party = conn.execute(
            "select id, name, bank_iban from parties where id = %s", (supplier_id,)
        ).fetchone()
        currency = conn.execute(
            "select currency from tenants where id = %s", (tenant_id,)
        ).fetchone()[0]
    if party is None:
        raise ApiError(422, "unknown_supplier", "Choose a supplier that exists in your ledger.")
    if (bill.get("currency") or currency) != currency:
        raise ApiError(422, "invalid_currency", f"Bills must be in {currency}.")
    for key in ("subtotal_minor", "tax_minor", "total_minor"):
        value = bill.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ApiError(
                422, "invalid_amount", f"{key} must be a non-negative integer in minor units."
            )
    if bill["total_minor"] <= 0:
        raise ApiError(422, "invalid_amount", "The total must be more than zero.")
    for key in ("issue_date", "due_date"):
        try:
            datetime.fromisoformat(str(bill.get(key)))
        except ValueError:
            raise ApiError(422, "invalid_date", f"{key} must be a date (YYYY-MM-DD).") from None
    text = str(bill.get("document_text") or "")[:MAX_TEXT]
    raw = text.encode("utf-8") or repr(sorted(bill.items())).encode("utf-8")
    ms = int(now.timestamp() * 1000)
    bill_id = f"bill_{encode_ulid(ms, secrets.token_bytes(10))}"
    warnings = [str(w)[:300] for w in bill.get("warnings") or []][:20]
    if bill.get("bank_iban") and party[2] and str(bill["bank_iban"]).replace(" ", "") != party[2]:
        warnings.append(
            f"The bill asks for payment to {bill['bank_iban']}, but the account on file for {party[1]} is {party[2]}."
        )
    record = {
        "id": bill_id,
        "supplier_id": supplier_id,
        "number": str(bill.get("number") or "")[:80] or None,
        "issue_date": str(bill["issue_date"]),
        "due_date": str(bill["due_date"]),
        "currency": currency,
        "subtotal_minor": bill["subtotal_minor"],
        "tax_minor": bill["tax_minor"],
        "total_minor": bill["total_minor"],
        "category": bill.get("category") or "inventory_supplier",
        "po_number": bill.get("po_number"),
        "bank_iban_on_bill": bill.get("bank_iban"),
        "document_filename": str(bill.get("document_filename") or "")[:120] or None,
        "document_text": text,
        "embedded_instructions": [str(i)[:500] for i in bill.get("embedded_instructions") or []][
            :20
        ],
        "warnings": warnings,
        "arithmetic_ok": bill["subtotal_minor"] + bill["tax_minor"] == bill["total_minor"],
        "received_by": received_by,
        "document_sha256": hashlib.sha256(raw).hexdigest(),
    }
    intake = record_bill_intake(conn, tenant_id, record, document_bytes=raw, now=now)
    return {
        "api_version": "v1",
        "bill_id": intake["bill_id"],
        "document_id": intake["document_id"],
        "warnings": warnings,
    }


def proposal_trace(conn: psycopg.Connection, tenant_id: str, proposal_id: str) -> dict[str, Any]:
    with db.tenant_session(conn, tenant_id):
        p = conn.execute(
            "select id, agent, type, created_at, summary, amount_minor, currency, payload, evidence,"
            " reasoning, created_by from proposals where id = %s",
            (proposal_id,),
        ).fetchone()
        if p is None:
            raise ApiError(404, "not_found", f"No proposal found with ID: {proposal_id}")
        payload = p[7] or {}
        bill_id = payload.get("bill_id")
        bill = None
        bill_lines: list[dict[str, Any]] = []
        document = None
        if bill_id:
            row = conn.execute(
                "select id, business_date, payload from events where type = 'purchase_bill'"
                " and payload->>'bill_id' = %s order by business_date desc limit 1",
                (bill_id,),
            ).fetchone()
            if row:
                bill = {
                    "event_id": row[0],
                    "posted_on": row[1].isoformat(),
                    **{k: v for k, v in (row[2] or {}).items() if k != "lines"},
                }
                bill_lines = _journal(conn, row[0])
                doc_id = (row[2] or {}).get("document_id")
                if doc_id:
                    d = conn.execute(
                        "select id, kind, sha256, received_at, extracted from documents where id = %s",
                        (doc_id,),
                    ).fetchone()
                    if d:
                        extracted = d[4] or {}
                        document = {
                            "id": d[0],
                            "kind": d[1],
                            "sha256": d[2],
                            "received_at": d[3].isoformat(),
                            "text": str(
                                extracted.get("document_text") or extracted.get("notes") or ""
                            )[:MAX_TEXT],
                            "embedded_instructions": extracted.get("embedded_instructions") or [],
                            "warnings": extracted.get("warnings") or [],
                        }
        verdicts = [
            {
                "id": v[0],
                "outcome": v[1],
                "decided_at": v[2].isoformat(),
                "previous_verdict_id": v[3],
                "checks": v[4],
            }
            for v in conn.execute(
                "select id, outcome, decided_at, previous_verdict_id, checks from verdicts"
                " where proposal_id = %s order by decided_at, id",
                (proposal_id,),
            )
        ]
        # Follow the chain (each verdict names the one it replaces); timestamps can tie.
        by_previous = {v["previous_verdict_id"]: v for v in verdicts}
        ordered = []
        current = by_previous.get(None)
        while current is not None and len(ordered) < len(verdicts):
            ordered.append(current)
            current = by_previous.get(current["id"])
        verdicts = ordered + [v for v in verdicts if v not in ordered]
        decisions = [
            {
                "id": d[0],
                "verdict_id": d[1],
                "decision": d[2],
                "note": d[3],
                "decided_by": d[4],
                "decided_at": d[5].isoformat(),
            }
            for d in conn.execute(
                "select id, verdict_id, decision, note, decided_by, decided_at from decisions"
                " where proposal_id = %s order by decided_at, id",
                (proposal_id,),
            )
        ]
        pay = conn.execute(
            "select id, business_date, payload from events where type = 'supplier_payment'"
            " and payload->>'proposal_id' = %s limit 1",
            (proposal_id,),
        ).fetchone()
        payment = None
        if pay:
            payment = {
                "event_id": pay[0],
                "paid_on": pay[1].isoformat(),
                **(pay[2] or {}),
                "journal": _journal(conn, pay[0]),
            }
        audit = [
            {
                "seq": a[0],
                "recorded_at": a[1].isoformat(),
                "record": a[2],
                "hash": a[3],
                "prev_hash": a[4],
            }
            for a in conn.execute(
                "select seq, recorded_at, record, hash, prev_hash from audit_log where proposal_id = %s order by seq",
                (proposal_id,),
            )
        ]
        chain = verify(conn, tenant_id)
    return {
        "api_version": "v1",
        "proposal": {
            "id": p[0],
            "agent": p[1],
            "type": p[2],
            "created_at": p[3].isoformat(),
            "summary": p[4],
            "amount": {"minor": p[5], "currency": p[6]} if p[5] is not None else None,
            "payload": payload,
            "evidence": p[8],
            "reasoning": p[9],
            "created_by": p[10],
        },
        "bill": bill,
        "bill_journal": bill_lines,
        "document": document,
        "verdicts": verdicts,
        "decisions": decisions,
        "payment": payment,
        "audit": audit,
        "audit_chain": {
            "verified": chain.ok,
            "length": chain.length,
            "first_bad_seq": chain.first_bad_seq,
        },
    }


def _journal(conn: psycopg.Connection, event_id: str) -> list[dict[str, Any]]:
    return [
        {
            "line_no": r[0],
            "account_code": r[1],
            "account_name": r[2],
            "debit_minor": r[3],
            "credit_minor": r[4],
        }
        for r in conn.execute(
            "select j.line_no, j.account_code, a.name, j.debit_minor, j.credit_minor from journal_lines j"
            " left join accounts a on a.tenant_id = j.tenant_id and a.code = j.account_code"
            " where j.event_id = %s order by j.line_no",
            (event_id,),
        )
    ]
