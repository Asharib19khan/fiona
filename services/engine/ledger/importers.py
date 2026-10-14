"""D3 importers: bank CSV, POS CSV and extracted bills become canonical ledger events.

* Idempotent. Each event's ID and source key come from its natural source record (FORMATS.md §1),
  so importing a file twice, or two overlapping statements, adds nothing the second time.
* Row-level validation. A bad row is reported with its row number and reason, and good rows load.
* Raw bank lines go to `bank_lines`; every bill's document goes to `documents` with its SHA-256.
* POS exports carry no cost: the sale lines take `unit_cost_minor` from `items`.
* Everything runs inside `tenant_session`, so row-level security applies to every write.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from engine.ledger import db
from engine.ledger.ids import source_ulid

ENVELOPE = ("id", "tenant_id", "event", "occurred_at", "date", "currency", "source")
POS_COLUMNS = [
    "receipt_no",
    "line_no",
    "txn_type",
    "original_receipt_no",
    "occurred_at",
    "business_date",
    "branch_id",
    "register_id",
    "cashier_id",
    "customer_code",
    "sku",
    "qty",
    "unit_price_minor",
    "discount_minor",
    "line_total_minor",
    "tax_minor",
    "payment_method",
    "payment_status",
    "currency",
]
BANK_COLUMNS = [
    "account_iban",
    "line_no",
    "posted_on",
    "value_date",
    "narration",
    "reference",
    "amount_minor",
    "balance_minor",
    "currency",
]


@dataclass
class ImportResult:
    inserted: int = 0
    skipped: int = 0  # already present (idempotent re-import)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"inserted": self.inserted, "skipped": self.skipped, "errors": self.errors}


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tenant(conn: psycopg.Connection) -> tuple[str, ZoneInfo]:
    currency, timezone = conn.execute("select currency, timezone from tenants").fetchone()
    return currency, ZoneInfo(timezone)


def insert_events(
    conn: psycopg.Connection, tenant_id: str, events: list[dict], recorded_at: datetime
) -> int:
    """Insert canonical events (FORMATS.md §3.13 shape); existing source keys are skipped. Returns inserted."""
    before = conn.execute("select count(*) from events").fetchone()[0]
    rows = []
    for e in events:
        payload = {k: v for k, v in e.items() if k not in ENVELOPE}
        rows.append(
            (
                tenant_id,
                e["id"],
                e["event"],
                e["occurred_at"],
                e["date"],
                recorded_at,
                payload.get("party"),
                e["currency"],
                Jsonb(payload),
                Jsonb(e["source"]),
            )
        )
    for chunk in range(0, len(rows), 10_000):  # one statement per chunk (RLS forbids COPY FROM)
        columns = [list(c) for c in zip(*rows[chunk : chunk + 10_000], strict=True)]
        conn.execute(
            "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, party_id, currency,"
            " payload, source) select * from unnest(%s::text[], %s::text[], %s::text[], %s::timestamptz[],"
            " %s::date[], %s::timestamptz[], %s::text[], %s::text[], %s::jsonb[], %s::jsonb[]) on conflict do nothing",
            columns,
        )
    return conn.execute("select count(*) from events").fetchone()[0] - before


def _read_csv(text: str, columns: list[str], result: ImportResult) -> list[tuple[int, dict]] | None:
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in columns if c not in (reader.fieldnames or [])]
    if missing:
        result.errors.append({"row": 0, "reason": f"missing columns: {', '.join(missing)}"})
        return None
    return list(enumerate(reader, start=1))


# ---------------------------------------------------------------- bank statement
def import_bank_csv(
    conn: psycopg.Connection,
    tenant_id: str,
    text: str,
    *,
    file_name: str = "bank_statement.csv",
    now: datetime,
) -> ImportResult:
    result = ImportResult()
    with db.tenant_session(conn, tenant_id):
        currency, _ = _tenant(conn)
        rows = _read_csv(text, BANK_COLUMNS, result)
        if rows is None:
            return result
        events, lines, previous = [], [], None
        for n, row in rows:
            try:
                line_no, amount, balance = (
                    int(row["line_no"]),
                    int(row["amount_minor"]),
                    int(row["balance_minor"]),
                )
                posted = datetime.fromisoformat(row["posted_on"]).replace(tzinfo=UTC)
                if row["currency"] != currency:
                    raise ValueError(f"currency {row['currency']} is not the tenant's {currency}")
                if previous is not None and previous + amount != balance:
                    raise ValueError(
                        f"balance {balance} does not follow the previous balance {previous} + {amount}"
                    )
            except (ValueError, KeyError) as exc:
                result.errors.append({"row": n, "reason": str(exc)})
                previous = None
                continue
            previous = balance
            key = f"{row['account_iban']}#{line_no}"
            event_id = source_ulid("evt", posted, tenant_id, "bank_statement", key)
            bank_line_id = source_ulid("bln", posted, tenant_id, "bank_statement", key)
            events.append(
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "event": "bank_line",
                    "occurred_at": _iso(posted),
                    "date": row["posted_on"],
                    "currency": currency,
                    "bank_line_id": bank_line_id,
                    "account_iban": row["account_iban"],
                    "line_no": line_no,
                    "narration": row["narration"],
                    "reference": row["reference"] or None,
                    "amount_minor": amount,
                    "balance_minor": balance,
                    "source": {
                        "type": "bank_statement",
                        "file": file_name,
                        "row": line_no,
                        "key": key,
                    },
                }
            )
            lines.append(
                (
                    tenant_id,
                    bank_line_id,
                    row["account_iban"],
                    line_no,
                    row["posted_on"],
                    row["value_date"] or None,
                    row["narration"],
                    row["reference"] or None,
                    amount,
                    balance,
                    currency,
                    event_id,
                )
            )
        result.inserted = insert_events(conn, tenant_id, events, now)
        result.skipped = len(events) - result.inserted
        with conn.cursor() as cur:
            cur.executemany(
                "insert into bank_lines (tenant_id, id, account_iban, line_no, posted_on, value_date, narration,"
                " reference, amount_minor, balance_minor, currency, event_id)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                lines,
            )
    return result


# ---------------------------------------------------------------- POS export
def import_pos_csv(
    conn: psycopg.Connection,
    tenant_id: str,
    text: str,
    *,
    file_name: str = "pos_sales.csv",
    now: datetime,
) -> ImportResult:
    result = ImportResult()
    with db.tenant_session(conn, tenant_id):
        currency, _ = _tenant(conn)
        costs = dict(conn.execute("select sku, unit_cost_minor from items").fetchall())
        rows = _read_csv(text, POS_COLUMNS, result)
        if rows is None:
            return result
        receipts: dict[str, list[tuple[int, dict]]] = {}
        for n, row in rows:
            receipts.setdefault(row["receipt_no"], []).append((n, row))
        events = []
        for receipt_no, group in receipts.items():
            first_row, head = group[0]
            try:
                lines = []
                for n, row in group:
                    if row["sku"] not in costs:
                        raise ValueError(f"row {n}: unknown SKU {row['sku']}")
                    qty, price, discount = (
                        int(row["qty"]),
                        int(row["unit_price_minor"]),
                        int(row["discount_minor"]),
                    )
                    total = int(row["line_total_minor"])
                    if qty * price - discount != total:
                        raise ValueError(
                            f"row {n}: qty x price - discount is {qty * price - discount}, not {total}"
                        )
                    lines.append(
                        {
                            "item": row["sku"],
                            "qty": qty,
                            "price_minor": price,
                            "discount_minor": discount,
                            "total_minor": total,
                            "tax_minor": int(row["tax_minor"]),
                            "cost_minor": costs[row["sku"]],
                        }
                    )
                if head["txn_type"] not in ("sale", "refund", "void"):
                    raise ValueError(f"row {first_row}: unknown txn_type {head['txn_type']}")
            except ValueError as exc:
                result.errors.append({"row": first_row, "reason": str(exc)})
                continue
            moment = _ts(head["occurred_at"])
            customer = head["customer_code"]
            events.append(
                {
                    "id": source_ulid("evt", moment, tenant_id, "pos_export", receipt_no),
                    "tenant_id": tenant_id,
                    "event": "sale",
                    "occurred_at": _iso(moment),
                    "date": head["business_date"],
                    "currency": currency,
                    "party": "cus_" + customer[2:] if customer else None,
                    "receipt_no": receipt_no,
                    "txn": head["txn_type"],
                    "original_receipt_no": head["original_receipt_no"] or None,
                    "branch": head["branch_id"],
                    "register": head["register_id"],
                    "cashier": head["cashier_id"],
                    "lines": lines,
                    "total_minor": sum(ln["total_minor"] for ln in lines),
                    "tax_minor": sum(ln["tax_minor"] for ln in lines),
                    "payment": {"method": head["payment_method"], "status": head["payment_status"]},
                    "source": {
                        "type": "pos_export",
                        "file": file_name,
                        "row": first_row,
                        "key": receipt_no,
                    },
                }
            )
        result.inserted = insert_events(conn, tenant_id, events, now)
        result.skipped = len(events) - result.inserted
    return result


# ---------------------------------------------------------------- extracted bills
def import_bills(
    conn: psycopg.Connection,
    tenant_id: str,
    bills: list[dict],
    documents: dict[str, bytes],
    *,
    storage_prefix: str,
    now: datetime,
) -> ImportResult:
    """`documents` maps each bill's document_path to its bytes, so the hash is checked, not trusted."""
    import hashlib

    result = ImportResult()
    with db.tenant_session(conn, tenant_id):
        currency, tz = _tenant(conn)
        events, docs = [], []
        for n, bill in enumerate(bills, start=1):
            try:
                content = documents[bill["document_path"]]
                if hashlib.sha256(content).hexdigest() != bill["document_sha256"]:
                    raise ValueError("document_sha256 does not match the document bytes")
                if bill["currency"] != currency:
                    raise ValueError(f"currency {bill['currency']} is not the tenant's {currency}")
            except (KeyError, ValueError) as exc:
                result.errors.append({"row": n, "bill_id": bill.get("bill_id"), "reason": str(exc)})
                continue
            received = _ts(bill["received_at"])
            entered_by = bill.get("entered_by", "svc_extraction")
            events.append(
                {
                    "id": source_ulid(
                        "evt", received, tenant_id, "bill_extraction", bill["bill_id"]
                    ),
                    "tenant_id": tenant_id,
                    "event": "purchase_bill",
                    "occurred_at": _iso(received),
                    "date": received.astimezone(tz).date().isoformat(),
                    "currency": currency,
                    "party": bill["supplier_id"],
                    "bill_id": bill["bill_id"],
                    "number": bill["number"],
                    "issue_date": bill["issue_date"],
                    "due_date": bill["due_date"],
                    "po_number": bill["po_number"],
                    "lines": bill["lines"],
                    "subtotal_minor": bill["subtotal_minor"],
                    "tax_minor": sum(t["amount_minor"] for t in bill["tax"]),
                    "total_minor": bill["total_minor"],
                    "document_id": bill["document_id"],
                    "document_sha256": bill["document_sha256"],
                    "created_by": {
                        "kind": "user" if entered_by.startswith("usr_") else "system",
                        "id": entered_by,
                    },
                    "source": {
                        "type": "bill_extraction",
                        "file": "bills.json",
                        "key": bill["bill_id"],
                    },
                }
            )
            mime = "application/pdf" if bill["document_path"].endswith(".pdf") else "text/plain"
            docs.append(
                (
                    tenant_id,
                    bill["document_id"],
                    f"{storage_prefix}/{bill['document_path']}",
                    bill["document_sha256"],
                    mime,
                    len(content),
                    Jsonb(bill),
                    bill["received_at"],
                )
            )
        with conn.cursor() as cur:
            cur.executemany(
                "insert into documents (tenant_id, id, kind, storage_path, sha256, mime_type, size_bytes, extracted,"
                " received_at) values (%s, %s, 'bill', %s, %s, %s, %s, %s, %s) on conflict do nothing",
                docs,
            )
        result.inserted = insert_events(conn, tenant_id, events, now)
        result.skipped = len(events) - result.inserted
    return result


# ---------------------------------------------------------------- other recorded events
def import_events(
    conn: psycopg.Connection,
    tenant_id: str,
    events: list[dict],
    *,
    source_types: set[str],
    now: datetime,
) -> ImportResult:
    """Events that are not file imports (payments, invoices, stock receipts, bank changes, journals)."""
    result = ImportResult()
    chosen = [e for e in events if e["source"]["type"] in source_types]
    with db.tenant_session(conn, tenant_id):
        result.inserted = insert_events(conn, tenant_id, chosen, now)
        result.skipped = len(chosen) - result.inserted
    return result


def events_from_jsonl(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]
