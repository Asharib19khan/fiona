"""What the forecast engines read from the ledger, behind one small interface.

Until D3 loads the database (G2), the snapshot is read from Daniyal's generator files in
data/fixtures/<tenant_id>/ (formats in data/fixtures/FORMATS.md). A database-backed loader
returns the same `LedgerSnapshot`, so the engines never change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "data" / "fixtures"


@dataclass(frozen=True)
class BankLine:
    id: str
    posted_on: date
    narration: str
    amount_minor: int
    balance_minor: int
    line_no: int


@dataclass(frozen=True)
class PurchaseBill:
    bill_id: str
    party: str
    number: str
    issue_date: date
    due_date: date
    total_minor: int


@dataclass(frozen=True)
class SupplierPayment:
    bill_id: str
    paid_on: date
    amount_minor: int


@dataclass(frozen=True)
class CustomerInvoice:
    invoice_id: str
    event_id: str
    party: str
    issue_date: date
    due_date: date
    total_minor: int


@dataclass(frozen=True)
class CustomerReceipt:
    invoice_ids: tuple[str, ...]
    received_on: date
    amount_minor: int


@dataclass(frozen=True)
class LedgerSnapshot:
    tenant_id: str
    currency: str
    as_of: date
    cash_buffer_minor: int | None
    bank_lines: list[BankLine]
    bills: list[PurchaseBill]
    payments: list[SupplierPayment]
    invoices: list[CustomerInvoice]
    receipts: list[CustomerReceipt]
    source: str
    notes: list[str] = field(default_factory=list)
    country: str | None = None
    sales: list[tuple[date, int]] = field(
        default_factory=list
    )  # (day, receipt total incl. refunds as negatives)


class TenantDataMissing(LookupError):
    pass


def _d(value: str) -> date:
    return date.fromisoformat(value)


def load_fixture_snapshot(tenant_id: str, root: Path = FIXTURES_ROOT) -> LedgerSnapshot:
    folder = root / tenant_id
    if not (folder / "tenant.json").is_file():
        raise TenantDataMissing(tenant_id)
    tenant = json.loads((folder / "tenant.json").read_text(encoding="utf-8"))
    as_of = _d(tenant["as_of"])

    bank_lines: list[BankLine] = []
    bills: list[PurchaseBill] = []
    payments: list[SupplierPayment] = []
    invoices: list[CustomerInvoice] = []
    receipt_events: list[CustomerReceipt] = []
    sales: list[tuple[date, int]] = []
    with (folder / "events.jsonl").open(encoding="utf-8") as fh:
        for raw in fh:
            e = json.loads(raw)
            kind = e["event"]
            if kind == "bank_line":
                bank_lines.append(
                    BankLine(
                        e["bank_line_id"],
                        _d(e["date"]),
                        e["narration"],
                        e["amount_minor"],
                        e["balance_minor"],
                        e["line_no"],
                    )
                )
            elif kind == "purchase_bill":
                bills.append(
                    PurchaseBill(
                        e["bill_id"],
                        e["party"],
                        e["number"],
                        _d(e["issue_date"]),
                        _d(e["due_date"]),
                        e["total_minor"],
                    )
                )
            elif kind == "supplier_payment":
                payments.append(SupplierPayment(e["bill_id"], _d(e["date"]), e["amount_minor"]))
            elif kind == "customer_invoice":
                invoices.append(
                    CustomerInvoice(
                        e["invoice_id"],
                        e["id"],
                        e["party"],
                        _d(e["issue_date"]),
                        _d(e["due_date"]),
                        e["total_minor"],
                    )
                )
            elif kind == "sale":
                sales.append((_d(e["date"]), e["total_minor"]))
            elif kind == "customer_receipt":
                receipt_events.append(
                    CustomerReceipt(tuple(e["invoice_ids"]), _d(e["date"]), e["amount_minor"])
                )
    bank_lines.sort(key=lambda b: (b.posted_on, b.line_no))

    # customer_receipt events come from reconciliation (D4). Until it runs, the answer key's
    # true receipt matches stand in, as the orchestrator ruled on 13 Oct.
    notes: list[str] = []
    receipts: list[CustomerReceipt] = receipt_events
    key_path = folder / "answer_key.json"
    if not receipt_events and key_path.is_file():
        key = json.loads(key_path.read_text(encoding="utf-8"))
        by_line = {b.id: b for b in bank_lines}
        for m in key.get("matches", []):
            if m.get("kind") == "customer_receipt" and m.get("bank_line_id") in by_line:
                line = by_line[m["bank_line_id"]]
                receipts.append(
                    CustomerReceipt(
                        tuple(m.get("invoice_ids", [])), line.posted_on, line.amount_minor
                    )
                )
        if receipts:
            notes.append(
                "customer receipts taken from the answer key until reconciliation (D4) creates them"
            )

    return LedgerSnapshot(
        tenant_id=tenant_id,
        currency=tenant["currency"],
        as_of=as_of,
        cash_buffer_minor=(tenant.get("policies") or {}).get("cash_buffer_minor"),
        bank_lines=[b for b in bank_lines if b.posted_on <= as_of],
        bills=[b for b in bills if b.issue_date <= as_of],
        payments=[p for p in payments if p.paid_on <= as_of],
        invoices=[i for i in invoices if i.issue_date <= as_of],
        receipts=[r for r in receipts if r.received_on <= as_of],
        country=tenant.get("country"),
        sales=[s for s in sales if s[0] <= as_of],
        source=f"fixtures:{folder.relative_to(root.parent.parent).as_posix()}",
        notes=notes,
    )
