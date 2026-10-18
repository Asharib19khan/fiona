"""Build analysis statement windows from D3's posted ledger.

The adapter only reads ``journal_lines`` joined to the tenant's neutral account classes.  This
keeps the analysis engine independent of import formats and gives every statement figure a
stable event reference.  A rolling twelve-month latest window and the twelve months before it
are returned for the stage detector and year-on-year ratios.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import psycopg

from engine.analysis.statements import BalanceSheet, CashFlows, IncomeStatement, Window
from engine.ledger import db

_OPERATING_EXPENSES = {
    "payroll",
    "occupancy",
    "utilities",
    "services",
    "marketing",
    "bank_charges",
    "cash_over_short",
    "supplies",
}
_CURRENT_ASSETS = {"clearing", "tax_receivable", "suspense"}
_NONCURRENT_ASSETS = {"deposits", "ppe"}
_CURRENT_LIABILITIES = {"tax_payable"}


@dataclass(frozen=True)
class _Line:
    event_id: str
    business_date: date
    account_class: str
    neutral_class: str
    debit_minor: int
    credit_minor: int

    @property
    def normal_balance(self) -> int:
        """Positive is the account's normal balance, regardless of its debit/credit side."""
        if self.account_class in {"asset", "expense"}:
            return self.debit_minor - self.credit_minor
        return self.credit_minor - self.debit_minor

    @property
    def cash_movement(self) -> int:
        """Signed bank and drawer movement: positive is cash received."""
        return self.debit_minor - self.credit_minor


class NoLedgerStatements(LookupError):
    pass


def _fetch(conn: psycopg.Connection, tenant_id: str) -> tuple[str, list[_Line]]:
    with db.tenant_session(conn, tenant_id):
        tenant = conn.execute("select currency from tenants").fetchone()
        if tenant is None:
            raise NoLedgerStatements(tenant_id)
        rows = conn.execute(
            "select j.event_id, j.business_date, a.class, a.neutral_class, "
            "j.debit_minor, j.credit_minor "
            "from journal_lines j join accounts a on a.tenant_id = j.tenant_id "
            "and a.code = j.account_code order by j.business_date, j.id"
        ).fetchall()
    if not rows:
        raise NoLedgerStatements(tenant_id)
    return tenant[0], [_Line(*row) for row in rows]


def _amount(lines: list[_Line], neutral: str) -> int:
    return sum(line.normal_balance for line in lines if line.neutral_class == neutral)


def _income(lines: list[_Line]) -> IncomeStatement:
    revenue = _amount(lines, "revenue") - _amount(lines, "sales_returns")
    return IncomeStatement(
        revenue=revenue,
        cogs=_amount(lines, "cost_of_sales"),
        operating_expenses=sum(
            line.normal_balance for line in lines if line.neutral_class in _OPERATING_EXPENSES
        ),
        depreciation_amortisation=_amount(lines, "depreciation"),
        interest_expense=_amount(lines, "interest"),
        other_income=sum(
            line.normal_balance
            for line in lines
            if line.account_class == "income"
            and line.neutral_class not in {"revenue", "sales_returns"}
        ),
        tax_expense=_amount(lines, "income_tax"),
    )


def _closing(lines: list[_Line], as_of: date) -> BalanceSheet:
    through = [line for line in lines if line.business_date <= as_of]
    cumulative_income = _income(through).net_income
    return BalanceSheet(
        as_of=as_of,
        cash=_amount(through, "cash"),
        trade_receivables=_amount(through, "receivables"),
        inventory=_amount(through, "inventory"),
        other_current_assets=sum(_amount(through, neutral) for neutral in _CURRENT_ASSETS),
        non_current_assets=sum(_amount(through, neutral) for neutral in _NONCURRENT_ASSETS),
        trade_payables=_amount(through, "payables"),
        other_current_liabilities=sum(
            _amount(through, neutral) for neutral in _CURRENT_LIABILITIES
        ),
        # D3 does not yet persist loan maturity buckets, so all posted borrowing is presented
        # as current until the loan schedule is modelled in the ledger schema.
        borrowings_current=_amount(through, "borrowings"),
        equity=_amount(through, "equity") - _amount(through, "drawings") + cumulative_income,
    )


def _cash_flows(lines: list[_Line], start: date, end: date) -> CashFlows:
    period = [line for line in lines if start <= line.business_date <= end]
    by_event: dict[str, list[_Line]] = defaultdict(list)
    for line in period:
        by_event[line.event_id].append(line)
    buckets = {"operating": 0, "investing": 0, "financing": 0}
    capex = principal_repaid = dividends_paid = largest_financing_inflow = largest_disposal = 0
    for event_lines in by_event.values():
        cash = sum(line.cash_movement for line in event_lines if line.neutral_class == "cash")
        if cash == 0:
            continue
        counterparts = {line.neutral_class for line in event_lines if line.neutral_class != "cash"}
        if counterparts & _NONCURRENT_ASSETS:
            bucket = "investing"
            if cash < 0:
                capex += cash
            else:
                largest_disposal = max(largest_disposal, cash)
        elif counterparts & {"borrowings", "equity", "drawings"}:
            bucket = "financing"
            if cash > 0:
                largest_financing_inflow = max(largest_financing_inflow, cash)
            if cash < 0 and "borrowings" in counterparts:
                principal_repaid += -cash
            if cash < 0 and "drawings" in counterparts:
                dividends_paid += -cash
        else:
            bucket = "operating"
        buckets[bucket] += cash
    return CashFlows(
        cfo=buckets["operating"],
        cfi=buckets["investing"],
        cff=buckets["financing"],
        capex=capex,
        principal_repaid=principal_repaid,
        dividends_paid=dividends_paid,
        largest_financing_inflow=largest_financing_inflow,
        largest_disposal=largest_disposal,
    )


def _window(lines: list[_Line], currency: str, start: date, end: date, label: str) -> Window:
    period = [line for line in lines if start <= line.business_date <= end]
    if not period:
        raise NoLedgerStatements(f"no posted ledger lines between {start} and {end}")
    refs = sorted({line.event_id for line in period})
    opening_date = start - timedelta(days=1)
    return Window(
        label=label,
        start=start,
        end=end,
        currency=currency,
        months_of_data=min(
            12,
            max(0, ((end - min(line.business_date for line in period)).days + 1) // 30),
        ),
        income=_income(period),
        opening=_closing(lines, opening_date)
        if any(line.business_date <= opening_date for line in lines)
        else None,
        closing=_closing(lines, end),
        cash_flows=_cash_flows(lines, start, end),
        source_refs=refs,
    )


# Computed windows per tenant, reused while the ledger is unchanged. Reading every journal line
# moves ~20 MB from the database per call; the ledger is append-only, so a cheap fingerprint
# (line count and newest posting) tells when a re-read is needed. Lives in engine memory only.
_WINDOWS: dict[str, tuple[tuple, tuple[Window, Window | None]]] = {}


def _fingerprint(conn: psycopg.Connection, tenant_id: str) -> tuple:
    with db.tenant_session(conn, tenant_id):
        return tuple(
            conn.execute(
                "select count(*), max(posted_at), (select count(*) from accounts) from journal_lines"
            ).fetchone()
        )


def ledger_windows(conn: psycopg.Connection, tenant_id: str) -> tuple[Window, Window | None]:
    """Return the latest rolling 12-month statement window and its prior comparison window."""
    key = (conn.info.host, conn.info.port, conn.info.dbname, *_fingerprint(conn, tenant_id))
    cached = _WINDOWS.get(tenant_id)
    if cached and cached[0] == key:
        return cached[1]
    result = _compute_windows(conn, tenant_id)
    _WINDOWS[tenant_id] = (key, result)
    return result


def _compute_windows(conn: psycopg.Connection, tenant_id: str) -> tuple[Window, Window | None]:
    currency, lines = _fetch(conn, tenant_id)
    latest_end = max(line.business_date for line in lines)
    latest_start = latest_end - timedelta(days=364)
    latest = _window(lines, currency, latest_start, latest_end, f"Last 12 months to {latest_end}")
    prior_end, prior_start = latest_start - timedelta(days=1), latest_start - timedelta(days=365)
    try:
        prior = _window(
            lines, currency, prior_start, prior_end, f"Previous 12 months to {prior_end}"
        )
    except NoLedgerStatements:
        prior = None
    return latest, prior
