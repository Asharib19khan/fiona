"""D3 posting rules: every event becomes a balanced journal in framework-neutral accounts.

Events hold facts; these rules turn them into postings. Bank lines that settle something already
recorded (a supplier payment) post nothing, because the book event posts it. Bank lines with no
book event (payroll, the BR02 lease, utilities, the loan, taxes, drawings, capex) post by narration
rule. A line that no rule explains goes to bank suspense (1990) so it is never silently dropped.

Known simplifications (ASSUMPTION, refined by the frameworks engine, B5): cost of sales uses the
cost carried on the sale line or the item's current cost; depreciation and the monthly sales-tax
offset of input against output tax are not posted here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import psycopg

from engine.ledger import db

CASH, DRAWERS, CARD_CLEARING, WALLET_CLEARING = "1000", "1010", "1020", "1030"
RECEIVABLES, INVENTORY, INPUT_TAX, ADVANCE_TAX = "1100", "1200", "1300", "1350"
PPE, SUSPENSE = "1500", "1990"
PAYABLES, OUTPUT_TAX, LOAN = "2000", "2100", "2200"
DRAWINGS = "3100"
REVENUE, RETURNS, COST_OF_SALES = "4000", "4010", "5000"
PAYROLL, RENT, UTILITIES, SERVICES, MARKETING, BANK_CHARGES, SUPPLIES, INTEREST = (
    "6000",
    "6100",
    "6200",
    "6250",
    "6270",
    "6300",
    "6600",
    "7000",
)
TENDER_ACCOUNT = {
    "cash": DRAWERS,
    "card": CARD_CLEARING,
    "bank_qr": CARD_CLEARING,
    "raast": CARD_CLEARING,
    "jazzcash": WALLET_CLEARING,
    "easypaisa": WALLET_CLEARING,
}

# Bank narration rules for lines with no book event: (pattern, account on the other side of cash).
# `None` means a book event already posts this movement. D4 adds confirmed matches as new rules.
NARRATION_RULES: list[tuple[re.Pattern[str], str | None]] = [
    (re.compile(r"^(POS CARD SETTL|QR SETTL|RAAST P2M SETTL)"), CARD_CLEARING),
    (re.compile(r"^(JAZZCASH|EASYPAISA) MERCH SETTL"), WALLET_CLEARING),
    (re.compile(r"^CASH DEPOSIT"), DRAWERS),
    (re.compile(r"^IBFT FROM "), RECEIVABLES),
    (re.compile(r"^IBFT TO .* FA_\d+$"), PPE),
    (re.compile(r"^IBFT TO "), None),  # a supplier_payment event posts it
    (re.compile(r"^(SALARY BULK TRF|FBR WHT SALARIES)"), PAYROLL),
    (re.compile(r"^RENT "), RENT),
    (re.compile(r"^(ELECTRICITY|GAS) BILL"), UTILITIES),
    (re.compile(r"^SECURITY AND CLEANING"), SERVICES),
    (re.compile(r"^DIGITAL MARKETING"), MARKETING),
    (re.compile(r"^(MDR CHARGES|BANK CHARGES)"), BANK_CHARGES),
    (re.compile(r"^LOAN DISBURSEMENT"), LOAN),
    (re.compile(r"^FBR SALES TAX"), OUTPUT_TAX),
    (re.compile(r"^FBR ADVANCE INCOME TAX"), ADVANCE_TAX),
    (re.compile(r"^OWNER DRAWINGS"), DRAWINGS),
]
LOAN_INSTALMENT = re.compile(r"^LOAN INSTALMENT (\d+)/\d+")


@dataclass
class PostingContext:
    item_costs: dict[str, int] = field(default_factory=dict)
    landlords: set[str] = field(default_factory=set)
    loan_schedule: dict[int, tuple[int, int]] = field(
        default_factory=dict
    )  # n -> (principal, interest)


def _line(account: str, debit: int = 0, credit: int = 0, memo: str | None = None) -> dict:
    return {"account": account, "debit_minor": debit, "credit_minor": credit, "memo": memo}


def _bank(amount: int, other: str, memo: str) -> list[dict]:
    if amount >= 0:
        return [_line(CASH, debit=amount, memo=memo), _line(other, credit=amount, memo=memo)]
    return [_line(other, debit=-amount, memo=memo), _line(CASH, credit=-amount, memo=memo)]


def post_event(kind: str, payload: dict, ctx: PostingContext) -> list[dict]:
    """Journal lines for one event (empty when the event moves no money or another event posts it)."""
    if kind == "sale":
        if payload["txn"] == "void":
            return []
        total, tax = payload["total_minor"], payload["tax_minor"]
        cost = sum(ln["qty"] * ln["cost_minor"] for ln in payload["lines"])
        tender = TENDER_ACCOUNT[payload["payment"]["method"]]
        if (
            payload["txn"] != "refund"
        ):  # branch on the transaction, not the sign (a refund can be 0)
            lines = [
                _line(tender, debit=total),
                _line(REVENUE, credit=total - tax),
                _line(OUTPUT_TAX, credit=tax),
            ]
            return [*lines, _line(COST_OF_SALES, debit=cost), _line(INVENTORY, credit=cost)]
        lines = [
            _line(RETURNS, debit=tax - total),
            _line(OUTPUT_TAX, debit=-tax),
            _line(tender, credit=-total),
        ]
        return [*lines, _line(INVENTORY, debit=-cost), _line(COST_OF_SALES, credit=-cost)]
    if kind == "purchase_bill":
        stock = sum(ln["line_total_minor"] for ln in payload["lines"] if ln.get("sku"))
        other = sum(ln["line_total_minor"] for ln in payload["lines"] if not ln.get("sku"))
        if stock:
            debits = [
                _line(INVENTORY, debit=stock + other)
            ]  # freight and finishing are capitalised
        else:
            debits = [_line(RENT if payload["party"] in ctx.landlords else SUPPLIES, debit=other)]
        return [
            *debits,
            _line(INPUT_TAX, debit=payload["tax_minor"]),
            _line(PAYABLES, credit=payload["total_minor"]),
        ]
    if kind == "supplier_payment":
        amount = payload["amount_minor"]
        return [_line(PAYABLES, debit=amount), _line(CASH, credit=amount)]
    if kind == "customer_invoice":
        cost = sum(ln["qty"] * ctx.item_costs.get(ln["sku"], 0) for ln in payload["lines"])
        return [
            _line(RECEIVABLES, debit=payload["total_minor"]),
            _line(REVENUE, credit=payload["subtotal_minor"]),
            _line(OUTPUT_TAX, credit=payload["tax_minor"]),
            _line(COST_OF_SALES, debit=cost),
            _line(INVENTORY, credit=cost),
        ]
    if kind == "journal_adjustment":
        return [
            _line(ln["account"], ln["debit_minor"], ln["credit_minor"], payload.get("reason"))
            for ln in payload["lines"]
        ]
    if kind == "bank_line":
        amount, narration = payload["amount_minor"], payload["narration"]
        instalment = LOAN_INSTALMENT.match(narration)
        if instalment and int(instalment.group(1)) in ctx.loan_schedule and amount < 0:
            principal, interest = ctx.loan_schedule[int(instalment.group(1))]
            if principal + interest == -amount:
                return [
                    _line(LOAN, debit=principal, memo=narration),
                    _line(INTEREST, debit=interest, memo=narration),
                    _line(CASH, credit=-amount, memo=narration),
                ]
        for pattern, account in NARRATION_RULES:
            if pattern.match(narration):
                return [] if account is None else _bank(amount, account, narration)
        return _bank(amount, SUSPENSE, f"unexplained: {narration}")
    return []  # customer_receipt (the bank line posts it), stock_movement, bank_detail_change


def balanced(lines: list[dict]) -> bool:
    return sum(ln["debit_minor"] for ln in lines) == sum(ln["credit_minor"] for ln in lines)


def post_unposted(
    conn: psycopg.Connection, tenant_id: str, ctx: PostingContext, *, now: datetime
) -> int:
    """Post every event that has no journal yet. Returns the number of journal lines written."""
    written = 0
    with db.tenant_session(conn, tenant_id):
        currency = conn.execute("select currency from tenants").fetchone()[0]
        events = conn.execute(
            "select e.id, e.type, e.business_date, e.payload from events e"
            " where not exists (select 1 from journal_lines j where j.event_id = e.id) order by e.occurred_at, e.id"
        ).fetchall()
        rows = []
        for event_id, kind, business_date, payload in events:
            lines = [
                ln
                for ln in post_event(kind, payload, ctx)
                if ln["debit_minor"] or ln["credit_minor"]
            ]
            if not lines:
                continue
            if not balanced(lines):
                raise ValueError(f"posting rule produced an unbalanced journal for {event_id}")
            journal_id = "jnl_" + event_id[4:]
            for n, ln in enumerate(lines, start=1):
                rows.append(
                    (
                        tenant_id,
                        journal_id,
                        n,
                        event_id,
                        ln["account"],
                        ln["debit_minor"],
                        ln["credit_minor"],
                        currency,
                        business_date,
                        ln["memo"],
                        now,
                    )
                )
        # RLS forbids COPY FROM, so rows go in as one INSERT ... SELECT FROM unnest(...) per chunk.
        for chunk in range(0, len(rows), 20_000):
            part = rows[chunk : chunk + 20_000]
            columns = list(zip(*part, strict=True))
            conn.execute(
                "insert into journal_lines (tenant_id, journal_id, line_no, event_id, account_code, debit_minor,"
                " credit_minor, currency, business_date, memo, posted_at)"
                " select * from unnest(%s::text[], %s::text[], %s::smallint[], %s::text[], %s::text[], %s::bigint[],"
                " %s::bigint[], %s::text[], %s::date[], %s::text[], %s::timestamptz[])",
                [list(c) for c in columns],
            )
        written = len(rows)
    return written


def context_from_db(
    conn: psycopg.Connection, tenant_id: str, loans: list[dict] | None = None
) -> PostingContext:
    with db.tenant_session(conn, tenant_id):
        costs = dict(conn.execute("select sku, unit_cost_minor from items").fetchall())
        landlords = {r[0] for r in conn.execute("select id from parties where kind = 'landlord'")}
    schedule = {
        row["n"]: (row["principal_minor"], row["interest_minor"])
        for loan in loans or []
        for row in loan["schedule"]
    }
    return PostingContext(item_costs=costs, landlords=landlords, loan_schedule=schedule)
