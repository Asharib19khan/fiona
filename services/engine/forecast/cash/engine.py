"""13-week cash forecast (task Y1) from a ledger snapshot.

Each week = opening + inflows - outflows, built from four kinds of line:

* scheduled: open supplier bills (paid at the due date plus the observed payment lag), open
  customer invoices (received at the due date plus the observed customer delay) and
  recurring obligations detected in the bank statement (payroll, rent, loan instalments,
  utilities, sales tax, bank fees), each repeated on its usual day of the month;
* forecast: POS and wallet settlements (trailing weekly mean, or seasonal-naive once a year
  of history exists) and purchases not yet billed (the recent weekly billing rate, paid on
  the observed mix of supplier terms).

The band is the closing balance +/- z(90%) x sigma(weekly settlements) x sqrt(week): it covers
takings uncertainty only, and the response says so.
"""

from __future__ import annotations

import calendar
import hashlib
import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine.forecast._contracts import (
    Action,
    Evidence,
    Figure,
    Finding,
    Money,
    Origin,
    Period,
    Unit,
)
from engine.forecast.cash.schemas import (
    CashCategory,
    CashForecastResponse,
    CashLine,
    CashWeek,
    ForecastMethod,
)
from engine.forecast.figures import (
    InsufficientData,
    figure_ref,
    money_figure,
    money_input,
    money_threshold,
    stable_id,
    value_input,
)
from engine.forecast.ledger_source import LedgerSnapshot

METHOD_VERSION = "cash/0.1.0"
Z90 = 1.2816
TRAILING_WEEKS = 4
SIGMA_WEEKS = 8
SEASONAL_MIN_WEEKS = 56
DEFAULT_SIGMA_SHARE = 0.15  # used only when fewer than three weeks of history exist

SETTLEMENT = re.compile(
    r"^(POS CARD SETTL|RAAST P2M SETTL|QR SETTL|JAZZCASH MERCH SETTL|EASYPAISA MERCH SETTL|CASH DEPOSIT)"
)
RECURRING = [
    (re.compile(r"^SALARY BULK TRF"), CashCategory.PAYROLL, lambda m: "payroll"),
    (re.compile(r"^RENT \S+ (BR\d+)"), CashCategory.RENT, lambda m: f"rent:{m.group(1)}"),
    (
        re.compile(r"^LOAN INSTALMENT (\d+)/(\d+)"),
        CashCategory.LOAN_REPAYMENT,
        lambda m: "loan_instalment",
    ),
    (re.compile(r"^ELECTRICITY BILL"), CashCategory.UTILITIES, lambda m: "electricity"),
    (re.compile(r"^GAS BILL"), CashCategory.UTILITIES, lambda m: "gas"),
    (re.compile(r"^FBR SALES TAX"), CashCategory.TAX, lambda m: "fbr_sales_tax"),
    (re.compile(r"^MDR CHARGES"), CashCategory.OTHER_OUTFLOW, lambda m: "mdr_fees"),
    (re.compile(r"^BANK CHARGES"), CashCategory.OTHER_OUTFLOW, lambda m: "bank_charges"),
]
INFLOWS = {CashCategory.POS_SALES, CashCategory.CUSTOMER_RECEIPTS, CashCategory.OTHER_INFLOW}


@dataclass
class _Item:
    day: date
    category: CashCategory
    basis: str
    amount: float  # minor units, positive
    ref: str


def _same_day_next_month(day: date, anchor_dom: int, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    y, m = divmod(index, 12)
    m += 1
    return date(y, m, min(anchor_dom, calendar.monthrange(y, m)[1]))


def _weekly_totals(days: dict[date, float], as_of: date, weeks: int, first: date) -> list[float]:
    """Totals of complete 7-day weeks ending on as_of, oldest first, within available history."""
    out = []
    for k in range(weeks, 0, -1):
        end = as_of - timedelta(days=7 * (k - 1))
        start = end - timedelta(days=6)
        if start < first:
            continue
        out.append(sum(v for d, v in days.items() if start <= d <= end))
    return out


def _median(values: list[float], default: float) -> float:
    return float(statistics.median(values)) if values else default


@dataclass
class _Plan:
    items: list[_Item]
    assumptions: list
    gaps: list[InsufficientData]
    sigma: float
    method: str
    description: str
    history_start: date


def _build_items(snap: LedgerSnapshot, end: date) -> _Plan:
    as_of, cur = snap.as_of, snap.currency
    items: list[_Item] = []
    assumptions: list = []
    gaps: list[InsufficientData] = []
    start = as_of + timedelta(days=1)
    first_day = snap.bank_lines[0].posted_on if snap.bank_lines else as_of

    # Settlements (POS, wallets, cash deposits) -------------------------------------------
    daily: dict[date, float] = defaultdict(float)
    for b in snap.bank_lines:
        if b.amount_minor > 0 and SETTLEMENT.match(b.narration):
            daily[b.posted_on] += b.amount_minor
    history_weeks = (as_of - first_day).days // 7
    recent = _weekly_totals(daily, as_of, TRAILING_WEEKS, first_day)
    spread = _weekly_totals(daily, as_of, SIGMA_WEEKS, first_day)
    if len(spread) >= 3:
        sigma = statistics.stdev(spread)
        assumptions.append(
            money_input(
                "weekly_settlement_sigma",
                sigma,
                cur,
                Origin.LEDGER,
                ref=f"{len(spread)} weeks of settlements",
            )
        )
    else:
        sigma = DEFAULT_SIGMA_SHARE * (statistics.mean(recent) if recent else 0)
        assumptions.append(
            money_input(
                "weekly_settlement_sigma",
                sigma,
                cur,
                Origin.ASSUMPTION,
                ref="15% of weekly takings",
            )
        )
    if not recent:
        gaps.append(
            InsufficientData(
                need="At least one full week of settlement history",
                why="Takings cannot be forecast without it.",
                blocking=True,
                metric_ids=["cash.closing"],
            )
        )
    seasonal = history_weeks >= SEASONAL_MIN_WEEKS
    if seasonal:
        method, description = (
            "seasonal_naive_scaled",
            (
                "Takings: the same week last year, scaled by the last four weeks against the same four weeks a year earlier."
            ),
        )
        last_year_recent = _weekly_totals(
            daily, as_of - timedelta(weeks=52), TRAILING_WEEKS, first_day
        )
        scale = (
            statistics.mean(recent) / statistics.mean(last_year_recent)
            if last_year_recent and statistics.mean(last_year_recent) > 0
            else 1.0
        )
    else:
        method, description = (
            "trailing_mean",
            (
                f"Takings: mean of the last {len(recent)} full weeks (less than a year of history, so no seasonality yet)."
            ),
        )
        gaps.append(
            InsufficientData(
                need="A year of settlement history",
                why="Weekly seasonality (Eid, winter, wedding season) needs it.",
                blocking=False,
                metric_ids=["cash.closing"],
            )
        )
    base_week = statistics.mean(recent) if recent else 0.0
    w = 0
    while start + timedelta(days=7 * w) <= end:
        wk_start = start + timedelta(days=7 * w)
        if seasonal:
            ly_start = wk_start - timedelta(weeks=52)
            amount = scale * sum(
                v for d, v in daily.items() if ly_start <= d <= ly_start + timedelta(days=6)
            )
        else:
            amount = base_week
        items.append(
            _Item(wk_start, CashCategory.POS_SALES, "forecast", amount, "pattern:settlements")
        )
        w += 1
    assumptions.append(
        money_input(
            "weekly_settlements_base",
            base_week,
            cur,
            Origin.LEDGER,
            ref=f"mean of {len(recent)} weeks",
        )
    )

    # Recurring obligations from the bank statement ----------------------------------------
    latest: dict[str, tuple[date, int, CashCategory, re.Match]] = {}
    for b in snap.bank_lines:
        if b.amount_minor >= 0:
            continue
        for pattern, category, keyer in RECURRING:
            m = pattern.match(b.narration)
            if m:
                latest[keyer(m)] = (b.posted_on, -b.amount_minor, category, m)
                break
    for key, (day, amount, category, m) in sorted(latest.items()):
        assumptions.append(
            money_input(
                f"recurring:{key}",
                amount,
                cur,
                Origin.LEDGER,
                ref=f"repeats the last payment ({day.isoformat()}) on day {day.day} of each month",
            )
        )
        remaining = None
        if key == "loan_instalment":
            remaining = int(m.group(2)) - int(m.group(1))
        k = 1
        while True:
            nxt = _same_day_next_month(day, day.day, k)
            if nxt > end or (remaining is not None and k > remaining):
                break
            if nxt >= start:
                items.append(_Item(nxt, category, "scheduled", float(amount), f"pattern:{key}"))
            k += 1

    # Open supplier bills ---------------------------------------------------------------------
    paid = {p.bill_id for p in snap.payments}
    bill_by_id = {b.bill_id: b for b in snap.bills}
    lags = [
        (p.paid_on - bill_by_id[p.bill_id].due_date).days
        for p in snap.payments
        if p.bill_id in bill_by_id
    ]
    pay_lag = round(_median(lags, 0))
    assumptions.append(
        value_input(
            "supplier_payment_lag_days",
            pay_lag,
            Unit.DAYS,
            Origin.LEDGER if lags else Origin.ASSUMPTION,
            ref=f"median of {len(lags)} payments against due dates",
        )
    )
    for b in snap.bills:
        if b.bill_id in paid:
            continue
        day = max(start, b.due_date + timedelta(days=pay_lag))
        if day <= end:
            items.append(
                _Item(
                    day, CashCategory.SUPPLIER_BILLS, "scheduled", float(b.total_minor), b.bill_id
                )
            )

    # Purchases not yet billed ----------------------------------------------------------------
    bill_days: dict[date, float] = defaultdict(float)
    for b in snap.bills:
        bill_days[b.issue_date] += b.total_minor
    billing = _weekly_totals(
        bill_days, as_of, TRAILING_WEEKS, snap.bills[0].issue_date if snap.bills else as_of
    )
    if len(billing) >= 2:
        rate = statistics.mean(billing) / 7
        by_terms: dict[int, float] = defaultdict(float)
        for b in snap.bills:
            by_terms[(b.due_date - b.issue_date).days] += b.total_minor
        total = sum(by_terms.values())
        day = start
        while day <= end:
            for terms, amount in by_terms.items():
                pay_day = day + timedelta(days=terms + pay_lag)
                if pay_day <= end:
                    items.append(
                        _Item(
                            pay_day,
                            CashCategory.SUPPLIER_BILLS,
                            "forecast",
                            rate * amount / total,
                            "pattern:future_purchases",
                        )
                    )
            day += timedelta(days=1)
        assumptions.append(
            money_input(
                "weekly_purchases_billed",
                rate * 7,
                cur,
                Origin.LEDGER,
                ref=f"mean of {len(billing)} weeks of bills",
            )
        )
    else:
        gaps.append(
            InsufficientData(
                need="Two weeks of supplier bills",
                why="Future purchases cannot be projected without a billing rate.",
                blocking=False,
                metric_ids=["cash.closing"],
            )
        )

    # Open customer invoices -----------------------------------------------------------------
    received = {iid for r in snap.receipts for iid in r.invoice_ids}
    inv_by_id = {i.invoice_id: i for i in snap.invoices}
    delays = [
        (r.received_on - inv_by_id[iid].due_date).days
        for r in snap.receipts
        for iid in r.invoice_ids
        if iid in inv_by_id
    ]
    delay = round(_median(delays, 0))
    assumptions.append(
        value_input(
            "customer_payment_delay_days",
            delay,
            Unit.DAYS,
            Origin.LEDGER if len(delays) >= 2 else Origin.ASSUMPTION,
            ref=f"median of {len(delays)} receipts against due dates",
        )
    )
    for inv in snap.invoices:
        if inv.invoice_id in received:
            continue
        day = max(start, inv.due_date + timedelta(days=delay))
        if day <= end:
            items.append(
                _Item(
                    day,
                    CashCategory.CUSTOMER_RECEIPTS,
                    "scheduled",
                    float(inv.total_minor),
                    inv.invoice_id,
                )
            )

    return _Plan(items, assumptions, gaps, sigma, method, description, first_day)


def forecast_cash(
    snap: LedgerSnapshot,
    *,
    weeks: int = 13,
    mode: str = "live",
    generated_at: datetime | None = None,
) -> CashForecastResponse:
    if not 1 <= weeks <= 26:
        raise ValueError("weeks must be 1 to 26")
    if not snap.bank_lines:
        raise ValueError("no bank lines up to as_of: cannot set an opening balance")
    cur, as_of = snap.currency, snap.as_of
    generated_at = generated_at or datetime.combine(as_of, datetime.min.time()).astimezone()
    start = as_of + timedelta(days=1)
    end = start + timedelta(days=7 * weeks - 1)
    plan = _build_items(snap, end)
    run_id = (
        "fc_"
        + hashlib.sha256(
            f"{snap.tenant_id}|{as_of}|{snap.source}|{METHOD_VERSION}|{weeks}".encode()
        ).hexdigest()[:20]
    )

    opening_minor = snap.bank_lines[-1].balance_minor
    buffer_minor = snap.cash_buffer_minor
    m = lambda x: Money(minor=round(x), currency=cur)  # noqa: E731

    rows: list[CashWeek] = []
    opening = float(opening_minor)
    for w in range(1, weeks + 1):
        ws = start + timedelta(days=7 * (w - 1))
        we = ws + timedelta(days=6)
        grouped: dict[tuple[CashCategory, str], list[_Item]] = defaultdict(list)
        for it in plan.items:
            if ws <= it.day <= we:
                grouped[(it.category, it.basis)].append(it)
        lines = []
        for (category, basis), its in sorted(
            grouped.items(), key=lambda kv: (kv[0][0].value, kv[0][1])
        ):
            amount = round(sum(i.amount for i in its))
            if amount == 0:
                continue
            refs = sorted({i.ref for i in its})
            lines.append(
                CashLine(
                    category=category,
                    direction="in" if category in INFLOWS else "out",
                    money=m(amount),
                    basis=basis,
                    refs=refs[:25],
                )
            )
        inflow = sum(x.money.minor for x in lines if x.direction == "in")
        outflow = sum(x.money.minor for x in lines if x.direction == "out")
        closing = round(opening) + inflow - outflow
        half = Z90 * plan.sigma * math.sqrt(w)
        rows.append(
            CashWeek(
                week=w,
                start=ws,
                end=we,
                opening=m(opening),
                inflows=m(inflow),
                outflows=m(outflow),
                net=m(inflow - outflow),
                closing=m(closing),
                closing_low=m(closing - half),
                closing_high=m(closing + half),
                below_buffer=buffer_minor is not None and closing < buffer_minor,
                lines=lines,
            )
        )
        opening = closing

    last_line = snap.bank_lines[-1]
    opening_fig = money_figure(
        "cash.opening_balance",
        "Cash in the bank today",
        opening_minor,
        cur,
        inputs=[money_input("bank_balance", opening_minor, cur, Origin.LEDGER, ref=last_line.id)],
        source_refs=[last_line.id],
    )
    lowest = min(rows, key=lambda r: r.closing.minor)
    lowest_fig = money_figure(
        "cash.lowest_closing",
        f"Lowest forecast balance (week {lowest.week})",
        lowest.closing.minor,
        cur,
        formula="min over weeks of (opening + inflows - outflows)",
        inputs=[figure_ref(opening_fig)],
        source_refs=[run_id],
    )
    gaps = list(plan.gaps)
    findings: list[Finding] = []
    if buffer_minor is None:
        buffer_fig = Figure(
            metric_id="cash.buffer",
            label="Your minimum cash buffer",
            unit=Unit.MINOR,
            status="insufficient_data",
            missing=["tenant.policies.cash_buffer_minor"],
        )
        shortfall_fig = Figure(
            metric_id="cash.shortfall_vs_buffer",
            label="Shortfall against your buffer",
            unit=Unit.MINOR,
            status="insufficient_data",
            missing=["tenant.policies.cash_buffer_minor"],
        )
        gaps.append(
            InsufficientData(
                need="Your minimum cash buffer",
                why="Alerts compare the forecast with it.",
                blocking=False,
                metric_ids=["cash.buffer"],
            )
        )
        first_below = None
    else:
        buffer_fig = money_figure(
            "cash.buffer",
            "Your minimum cash buffer",
            buffer_minor,
            cur,
            inputs=[
                money_input(
                    "cash_buffer",
                    buffer_minor,
                    cur,
                    Origin.TENANT_POLICY,
                    ref="tenant.policies.cash_buffer_minor",
                )
            ],
        )
        shortfall = max(0, buffer_minor - lowest.closing.minor)
        shortfall_fig = money_figure(
            "cash.shortfall_vs_buffer",
            "Shortfall against your buffer",
            shortfall,
            cur,
            formula="max(0, buffer - lowest_closing)",
            inputs=[figure_ref(buffer_fig), figure_ref(lowest_fig)],
            thresholds=[
                money_threshold(
                    "cash_buffer", buffer_minor, cur, Origin.TENANT_POLICY, ">=", shortfall == 0
                )
            ],
        )
        first_below = next((r.week for r in rows if r.below_buffer), None)
        ev = [Evidence(kind="forecast_run", ref=run_id)]
        if first_below is not None:
            wk = rows[first_below - 1]
            drivers = sorted(
                (x for x in wk.lines if x.direction == "out"), key=lambda x: -x.money.minor
            )[:3]
            ev += [Evidence(kind="cash_line", ref=r) for d in drivers for r in d.refs[:3]]
            findings.append(
                Finding(
                    id=stable_id("fnd", "cash_below_buffer", snap.tenant_id, wk.start.isoformat()),
                    source="forecast",
                    severity="high",
                    title=f"Cash dips below your buffer in week {first_below}",
                    money_at_stake=m(shortfall),
                    evidence=ev,
                    actions=[
                        Action(label="Open forecast", route="/forecast"),
                        Action(label="Optimise payment timing", route="/decisions/payment-timing"),
                        Action(label="Compare financing", route="/financing"),
                    ],
                    type="cash_below_buffer",
                    detail="Largest outflows that week: "
                    + ", ".join(d.category.value for d in drivers)
                    + ".",
                    period=Period(start=wk.start, end=wk.end),
                    created_at=generated_at,
                    dedupe_key=f"cash_below_buffer:{snap.tenant_id}:{wk.start.isoformat()}",
                    figures=[lowest_fig, buffer_fig, shortfall_fig],
                )
            )
        else:
            risky = next((r for r in rows if r.closing_low.minor < buffer_minor), None)
            if risky is not None:
                findings.append(
                    Finding(
                        id=stable_id(
                            "fnd", "cash_may_dip", snap.tenant_id, risky.start.isoformat()
                        ),
                        source="forecast",
                        severity="medium",
                        title=f"In a weak-sales week, cash could fall below your buffer by week {risky.week}",
                        money_at_stake=m(buffer_minor - risky.closing_low.minor),
                        evidence=ev,
                        actions=[Action(label="Open forecast", route="/forecast")],
                        type="cash_may_dip_below_buffer",
                        period=Period(start=risky.start, end=risky.end),
                        created_at=generated_at,
                        dedupe_key=f"cash_may_dip:{snap.tenant_id}:{risky.start.isoformat()}",
                        figures=[buffer_fig],
                    )
                )

    paid = {p.bill_id for p in snap.payments}
    open_bills = [b for b in snap.bills if b.bill_id not in paid]
    received = {iid for r in snap.receipts for iid in r.invoice_ids}
    open_invoices = [i for i in snap.invoices if i.invoice_id not in received]
    receivables = money_figure(
        "cash.open_receivables",
        "Invoices customers still owe",
        sum(i.total_minor for i in open_invoices),
        cur,
        source_refs=[i.invoice_id for i in open_invoices][:50],
        note="; ".join(snap.notes) or None,
    )
    payables = money_figure(
        "cash.open_payables",
        "Supplier bills not yet paid",
        sum(b.total_minor for b in open_bills),
        cur,
        source_refs=[b.bill_id for b in open_bills][:50],
    )

    return CashForecastResponse(
        mode=mode,
        tenant_id=snap.tenant_id,
        generated_at=generated_at,
        run_id=run_id,
        currency=cur,
        as_of=as_of,
        horizon_weeks=weeks,
        method=ForecastMethod(
            name=plan.method,
            description=plan.description + " Bills and invoices are scheduled from the ledger.",
            history=Period(start=plan.history_start, end=as_of),
            band="closing +/- 1.2816 x sigma(weekly settlements) x sqrt(week): takings uncertainty only (p10 to p90)",
        ),
        opening_balance=opening_fig,
        buffer=buffer_fig,
        lowest_closing=lowest_fig,
        first_week_below_buffer=first_below,
        shortfall=shortfall_fig,
        open_receivables=receivables,
        open_payables=payables,
        weeks=rows,
        assumptions=plan.assumptions,
        insufficient_data=gaps,
        findings=findings,
    )
