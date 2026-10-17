"""Read-only bill checks backed by canonical purchase-bill events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from engine.guardian_checks.checks import g05_duplicate_bill
from engine.guardian_checks.context import BillContext, CheckContext, PriorBillContext
from engine.ledger import db


def _bill_context(bill_id: str, party_id: str | None, payload: dict[str, Any]) -> BillContext:
    return BillContext(
        bill_id=bill_id,
        supplier_id=party_id,
        number=payload.get("number"),
        subtotal_minor=payload.get("subtotal_minor"),
        total_minor=payload.get("total_minor"),
        stated_tax_minor=payload.get("tax_minor"),
        document_sha256=payload.get("document_sha256"),
        po_number=payload.get("po_number"),
        issue_date=payload.get("issue_date"),
        due_date=payload.get("due_date"),
        created_by=(payload.get("created_by") or {}).get("id"),
    )


def duplicate_bill_check(
    conn: psycopg.Connection, tenant_id: str, bill_id: str, *, now: datetime
) -> dict[str, Any] | None:
    """Run G-05 for one imported bill, returning ``None`` when it does not exist.

    Imported events remain immutable. This assembles an explicit Guardian context from those
    facts and reports the result for review.
    """
    with db.tenant_session(conn, tenant_id):
        tenant = conn.execute(
            "select cash_buffer_minor, currency, country from tenants where id = %s", (tenant_id,)
        ).fetchone()
        rows = conn.execute(
            "select party_id, payload from events where type = 'purchase_bill' order by business_date, id"
        ).fetchall()
    if tenant is None:
        return None

    current: BillContext | None = None
    prior_bills: list[PriorBillContext] = []
    for party_id, payload in rows:
        found_id = payload.get("bill_id")
        if not isinstance(found_id, str):
            continue
        if found_id == bill_id:
            current = _bill_context(found_id, party_id, payload)
            continue
        prior_bills.append(
            PriorBillContext(
                bill_id=found_id,
                supplier_id=party_id,
                number=payload.get("number"),
                total_minor=payload.get("total_minor"),
                document_sha256=payload.get("document_sha256"),
                issue_date=payload.get("issue_date"),
            )
        )
    if current is None:
        return None

    check = g05_duplicate_bill(
        CheckContext(
            proposal={
                "id": f"prop_bill_check_{bill_id}",
                "type": "bill_approval",
                "agent": "ledger",
            },
            buffer_minor=tenant[0],
            currency=tenant[1],
            country=tenant[2],
            bill=current,
            prior_bills=prior_bills,
            now=now,
        )
    )
    return check.model_dump(mode="json") if check is not None else None
