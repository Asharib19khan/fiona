"""Payment timing on the live ledger (Y8): every open supplier bill, against the live forecast.

The optimiser (payment_timing.optimise_payment_timing) is unchanged; this module feeds it the
tenant's open bills (posted bills with no supplier payment yet) and the 13-week closing path
from the cash forecast, then shapes the contract response. Bills already overdue are scheduled
for today, never for a date in the past.
"""

from __future__ import annotations

from datetime import UTC, datetime

from engine.decisions.payment_timing import OpenBill, WeekBalance, optimise_payment_timing
from engine.decisions.schemas import PaymentTimingRequest, PaymentTimingResponse, TimingWeek
from engine.forecast._contracts import Money, Origin
from engine.forecast.cash.schemas import CashForecastResponse
from engine.forecast.figures import bp_figure, bp_input, money_figure, stable_id
from engine.forecast.ledger_source import LedgerSnapshot

COST_OF_MONEY_BP = 2_200  # rulebook launch_lab.cost_of_capital_annual_bp (PK, provisional)


def open_bills(snapshot: LedgerSnapshot, names: dict[str, str]) -> list[OpenBill]:
    paid: dict[str, int] = {}
    for payment in snapshot.payments:
        paid[payment.bill_id] = paid.get(payment.bill_id, 0) + payment.amount_minor
    return [
        OpenBill(
            bill_id=bill.bill_id,
            supplier_id=bill.party,
            supplier_name=names.get(bill.party, bill.party),
            amount_minor=bill.total_minor - paid.get(bill.bill_id, 0),
            issue_date=bill.issue_date,
            due_date=bill.due_date,
        )
        for bill in snapshot.bills
        if bill.total_minor - paid.get(bill.bill_id, 0) > 0
    ]


def live_payment_timing(
    body: PaymentTimingRequest,
    snapshot: LedgerSnapshot,
    cash: CashForecastResponse,
    names: dict[str, str],
    *,
    mode: str,
) -> PaymentTimingResponse:
    bills = open_bills(snapshot, names)
    if body.bill_ids is not None:
        wanted = set(body.bill_ids)
        bills = [bill for bill in bills if bill.bill_id in wanted]
    weeks = [
        WeekBalance(week=w.week, start=w.start, end=w.end, closing_minor=w.closing.minor)
        for w in cash.weeks
    ]
    buffer_minor = cash.buffer.money.minor if cash.buffer.money else 0
    cost_bp = (
        body.cost_of_money_annual_bp
        if body.cost_of_money_annual_bp is not None
        else COST_OF_MONEY_BP
    )
    timings = optimise_payment_timing(
        bills,
        weeks,
        buffer_minor=buffer_minor,
        cost_of_money_annual_bp=cost_bp,
        as_of=snapshot.as_of,
        currency=snapshot.currency,
    )
    timings = [
        t.model_copy(update={"pay_on": snapshot.as_of})
        if t.pay_on is not None and t.pay_on < snapshot.as_of
        else t
        for t in timings
    ]
    saving = sum(
        f.money.minor
        for t in timings
        if t.action == "pay_early"
        for f in t.figures
        if f.metric_id == "payments.saving_if_early" and f.money
    )
    return PaymentTimingResponse(
        mode=mode,
        tenant_id=snapshot.tenant_id,
        generated_at=datetime.now(UTC),
        run_id=stable_id("pt", snapshot.tenant_id, snapshot.as_of.isoformat(), str(len(timings))),
        currency=snapshot.currency,
        as_of=snapshot.as_of,
        cost_of_money=bp_figure(
            "payments.cost_of_money",
            "Your cost of money",
            cost_bp / 10_000,
            inputs=[bp_input("cost_of_capital_annual", cost_bp / 10_000, Origin.RULEBOOK)],
        ),
        buffer=cash.buffer,
        bills=timings,
        weeks=[
            TimingWeek(
                week=w.week,
                start=w.start,
                end=w.end,
                payments=Money(minor=0, currency=snapshot.currency),
                closing_before=w.closing,
                closing_after=w.closing,
                below_buffer=w.below_buffer,
            )
            for w in cash.weeks
        ],
        totals=[
            money_figure("payments.total_saving", "Discounts captured", saving, snapshot.currency)
        ],
    )
