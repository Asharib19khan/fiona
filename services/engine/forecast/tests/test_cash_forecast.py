"""Y1: the 13-week cash forecast on generator data and on hand-built ledgers."""

from datetime import date, timedelta

import pytest

from engine.forecast.cash.engine import forecast_cash
from engine.forecast.cash.schemas import CashCategory
from engine.forecast.ledger_source import (
    FIXTURES_ROOT,
    BankLine,
    CustomerInvoice,
    LedgerSnapshot,
    PurchaseBill,
    load_fixture_snapshot,
)

AS_OF = date(2026, 10, 22)


def _snapshot(**kw) -> LedgerSnapshot:
    """Six weeks of steady takings (Rs 1M a week) and an opening balance of Rs 5M."""
    lines = []
    day = AS_OF - timedelta(days=41)
    balance = 400_000_000
    n = 0
    while day <= AS_OF:
        n += 1
        balance += 14_285_714
        lines.append(
            BankLine(f"bln_{n}", day, f"POS CARD SETTL MID 1 BATCH {n}", 14_285_714, balance, n)
        )
        day += timedelta(days=1)
    base = dict(
        tenant_id="ten_test",
        currency="PKR",
        as_of=AS_OF,
        cash_buffer_minor=200_000_000,
        bank_lines=lines,
        bills=[],
        payments=[],
        invoices=[],
        receipts=[],
        source="test",
    )
    base.update(kw)
    return LedgerSnapshot(**base)


def _sum(result, category, basis=None):
    return sum(
        ln.money.minor
        for w in result.weeks
        for ln in w.lines
        if ln.category == category and (basis is None or ln.basis == basis)
    )


def test_weeks_add_up_and_start_from_the_bank_balance():
    snap = _snapshot()
    r = forecast_cash(snap)
    assert r.opening_balance.money.minor == snap.bank_lines[-1].balance_minor
    for prev, w in zip([None, *r.weeks], r.weeks, strict=False):
        assert w.closing.minor == w.opening.minor + w.inflows.minor - w.outflows.minor
        if prev is not None:
            assert w.opening == prev.closing
        assert w.closing_low.minor <= w.closing.minor <= w.closing_high.minor
    assert r.method.name == "trailing_mean"


def test_planted_dip_raises_one_high_finding_in_the_right_week():
    big = PurchaseBill(
        "bill_big",
        "sup_1",
        "INV-1",
        AS_OF - timedelta(days=20),
        AS_OF + timedelta(days=45),
        1_600_000_000,
    )
    r = forecast_cash(_snapshot(bills=[big]))
    dip_week = (45 - 1) // 7 + 1
    assert r.first_week_below_buffer == dip_week
    [finding] = [f for f in r.findings if f.type == "cash_below_buffer"]
    assert finding.severity == "high"
    assert finding.money_at_stake == r.shortfall.money
    assert any(e.ref == "bill_big" for e in finding.evidence)
    assert r.shortfall.money.minor == 200_000_000 - r.lowest_closing.money.minor


def test_every_open_bill_and_invoice_is_scheduled_exactly_once():
    bills = [
        PurchaseBill(
            f"bill_{i}",
            "sup_1",
            f"N{i}",
            AS_OF - timedelta(days=5),
            AS_OF + timedelta(days=3 * i),
            1_000_000 * i,
        )
        for i in range(1, 6)
    ]
    invoices = [
        CustomerInvoice(
            "inv_1",
            "evt_1",
            "cus_1",
            AS_OF - timedelta(days=30),
            AS_OF - timedelta(days=2),
            5_000_000,
        )
    ]
    r = forecast_cash(_snapshot(bills=bills, invoices=invoices))
    assert _sum(r, CashCategory.SUPPLIER_BILLS, "scheduled") == sum(b.total_minor for b in bills)
    assert _sum(r, CashCategory.CUSTOMER_RECEIPTS) == 5_000_000  # overdue: expected in week 1
    assert r.weeks[0].lines and any(
        ln.category == CashCategory.CUSTOMER_RECEIPTS for ln in r.weeks[0].lines
    )


def test_loan_instalments_stop_after_the_last_one():
    lines = _snapshot().bank_lines
    loan = BankLine(
        "bln_loan",
        AS_OF - timedelta(days=12),
        "LOAN INSTALMENT 34/36",
        -45_000_000,
        lines[-1].balance_minor,
        999,
    )
    r = forecast_cash(_snapshot(bank_lines=sorted([*lines, loan], key=lambda b: b.posted_on)))
    assert _sum(r, CashCategory.LOAN_REPAYMENT) == 2 * 45_000_000


def test_missing_buffer_is_reported_not_guessed():
    r = forecast_cash(_snapshot(cash_buffer_minor=None))
    assert r.buffer.status == "insufficient_data"
    assert r.first_week_below_buffer is None
    assert any("buffer" in g.need for g in r.insufficient_data)


def test_a_year_of_history_switches_on_seasonality():
    lines = []
    balance = 0
    for n, k in enumerate(range(400, -1, -1)):
        day = AS_OF - timedelta(days=k)
        amount = 30_000_000 if day.month in (11, 12) else 10_000_000
        balance += amount
        lines.append(BankLine(f"bln_{n}", day, "RAAST P2M SETTL 1", amount, balance, n))
    r = forecast_cash(_snapshot(bank_lines=lines))
    assert r.method.name == "seasonal_naive_scaled"
    nov = next(w for w in r.weeks if w.start.month == 11 and w.end.month == 11)
    oct_week = r.weeks[0]
    pos = lambda w: sum(ln.money.minor for ln in w.lines if ln.category == CashCategory.POS_SALES)  # noqa: E731
    assert pos(nov) > 2 * pos(oct_week)


def test_same_ledger_gives_the_same_run():
    a, b = forecast_cash(_snapshot()), forecast_cash(_snapshot())
    assert a.run_id == b.run_id
    assert a.model_dump() == b.model_dump()


@pytest.mark.skipif(
    not (FIXTURES_ROOT / "ten_karachi_apparel" / "events.jsonl").is_file(),
    reason="generator fixtures absent",
)
def test_runs_on_the_generator_ledger():
    snap = load_fixture_snapshot("ten_karachi_apparel")
    r = forecast_cash(snap)
    assert r.horizon_weeks == 13 and len(r.weeks) == 13
    assert r.opening_balance.money.minor == snap.bank_lines[-1].balance_minor
    paid = {p.bill_id for p in snap.payments}
    open_total = sum(b.total_minor for b in snap.bills if b.bill_id not in paid)
    assert _sum(r, CashCategory.SUPPLIER_BILLS, "scheduled") == open_total
    payroll_weeks = [
        w.week for w in r.weeks if any(ln.category == CashCategory.PAYROLL for ln in w.lines)
    ]
    assert len(payroll_weeks) == 3  # 1 Nov, 1 Dec, 1 Jan
