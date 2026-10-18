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


def load_ledger_snapshot(
    conn, tenant_id: str, as_of: date | None = None, *, in_tenant_session: bool = False
) -> LedgerSnapshot:
    """The same snapshot, read from the tenant's posted ledger (live mode).

    Everything imported (bank statements, POS exports, bills) and everything the wallet paid
    flows into the forecast, financing and decisions engines from here. Customer receipts come
    from reconciliation matches (proposed or confirmed); until reconciliation runs, the open
    receivables are every unmatched invoice, and the snapshot says so in `notes`.
    `as_of` defaults to today in the tenant's time zone (engine.app.clock). Pass
    in_tenant_session=True when the caller already holds this tenant's session.
    """
    from contextlib import nullcontext

    from engine.app import clock
    from engine.ledger import db

    with nullcontext(conn) if in_tenant_session else db.tenant_session(conn, tenant_id):
        tenant = conn.execute(
            "select currency, cash_buffer_minor, country, timezone from tenants where id = %s",
            (tenant_id,),
        ).fetchone()
        if tenant is None:
            raise TenantDataMissing(tenant_id)
        currency, buffer_minor, country, timezone = tenant
        as_of = as_of or clock.business_date(timezone or "UTC")

        # The ledger is append-only, so these counts change whenever anything that feeds the
        # snapshot changes (an import, a payment, a reconciliation run, a new buffer).
        fingerprint = conn.execute(
            "select (select count(*) from events), (select max(recorded_at) from events),"
            " (select count(*) from bank_lines),"
            " (select count(*) from matches where status <> 'rejected')"
        ).fetchone()
        key = (tenant_id, as_of, tuple(fingerprint), buffer_minor)
        cached = _SNAPSHOTS.get((tenant_id, as_of))
        if cached and cached[0] == key:
            return cached[1]

        bank_lines = [
            BankLine(r[0], r[1], r[2], r[3], r[4], r[5])
            for r in conn.execute(
                "select id, posted_on, narration, amount_minor, balance_minor, line_no from bank_lines"
                " where posted_on <= %s order by posted_on, line_no",
                (as_of,),
            )
        ]
        bills: list[PurchaseBill] = []
        payments: list[SupplierPayment] = []
        invoices: list[CustomerInvoice] = []
        sales: list[tuple[date, int]] = []
        for event_id, kind, business_date, party_id, p in conn.execute(
            "select id, type, business_date, party_id, payload from events"
            " where type in ('purchase_bill', 'supplier_payment', 'customer_invoice', 'sale')"
            " and business_date <= %s order by business_date, id",
            (as_of,),
        ):
            if kind == "purchase_bill":
                bills.append(
                    PurchaseBill(
                        p["bill_id"],
                        p.get("party") or p.get("supplier_id") or party_id,
                        p.get("number") or p["bill_id"],
                        _d(p.get("issue_date") or business_date.isoformat()),
                        _d(p.get("due_date") or p.get("issue_date") or business_date.isoformat()),
                        int(p["total_minor"]),
                    )
                )
            elif kind == "supplier_payment" and p.get("bill_id"):
                payments.append(
                    SupplierPayment(p["bill_id"], business_date, int(p["amount_minor"]))
                )
            elif kind == "customer_invoice":
                invoices.append(
                    CustomerInvoice(
                        p["invoice_id"],
                        event_id,
                        p.get("party") or party_id,
                        _d(p["issue_date"]),
                        _d(p["due_date"]),
                        int(p["total_minor"]),
                    )
                )
            elif kind == "sale":
                sales.append((business_date, int(p["total_minor"])))

        receipts: dict[str, CustomerReceipt] = {}
        for match_id, posted_on, amount_minor, invoice_id in conn.execute(
            "select m.match_id, b.posted_on, b.amount_minor, e.payload->>'invoice_id'"
            " from matches m join bank_lines b on b.tenant_id = m.tenant_id and b.id = m.bank_line_id"
            " join events e on e.tenant_id = m.tenant_id and e.id = m.event_id"
            " where e.type = 'customer_invoice' and m.status <> 'rejected' and b.posted_on <= %s"
            " order by m.match_id",
            (as_of,),
        ):
            seen = receipts.get(match_id)
            ids = (*seen.invoice_ids, invoice_id) if seen else (invoice_id,)
            receipts[match_id] = CustomerReceipt(ids, posted_on, amount_minor)

    notes: list[str] = []
    if invoices and not receipts:
        notes.append(
            "no customer receipts are matched yet: run reconciliation so paid invoices stop counting as receivables"
        )
    snapshot = LedgerSnapshot(
        tenant_id=tenant_id,
        currency=currency,
        as_of=as_of,
        cash_buffer_minor=buffer_minor,
        bank_lines=bank_lines,
        bills=bills,
        payments=payments,
        invoices=invoices,
        receipts=list(receipts.values()),
        country=country,
        sales=sales,
        source="ledger:postgres",
        notes=notes,
    )
    _SNAPSHOTS[(tenant_id, as_of)] = (key, snapshot)
    return snapshot


# Snapshots by (tenant, as_of), reused while the ledger fingerprint is unchanged. Snapshots are
# frozen, so sharing one between requests is safe.
_SNAPSHOTS: dict[tuple[str, date], tuple[tuple, LedgerSnapshot]] = {}


def load_snapshot(tenant_id: str, mode: str) -> LedgerSnapshot:
    """The ledger in live mode; Daniyal's generator files in mock mode (unchanged behaviour)."""
    if mode == "mock":
        return load_fixture_snapshot(tenant_id)
    from engine.ledger import db

    with db.connect(autocommit=True) as conn:
        return load_ledger_snapshot(conn, tenant_id)


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
