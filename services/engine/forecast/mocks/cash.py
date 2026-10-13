"""Mock 13-week cash forecast: the planted winter-stock dip below the buffer in week 7."""

from __future__ import annotations

import math
from datetime import date, timedelta

from engine.forecast._contracts import Action, Evidence, Finding, Origin, Period, Unit
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
from engine.forecast.mocks import AS_OF, CASH_BUFFER_MINOR, CURRENCY, GENERATED_AT, envelope
from engine.forecast.money import Money

OPENING_MINOR = 804_112_300  # last bank balance in the fixture statement
WEEKLY_SIGMA_MINOR = 45_000_000  # spread of weekly net cash, used for the p10-p90 band
Z90 = 1.2816

# Scheduled items: (date, category, amount in rupees, refs). Synthetic.
SCHEDULED: list[tuple[date, CashCategory, int, list[str]]] = [
    (date(2026, 10, 24), CashCategory.SUPPLIER_BILLS, 1_845_000, ["bill_2231"]),
    (date(2026, 10, 31), CashCategory.PAYROLL, 2_400_000, ["pattern_salary_bulk"]),
    (date(2026, 11, 1), CashCategory.RENT, 900_000, ["pattern_rent_br01"]),
    (date(2026, 11, 2), CashCategory.CUSTOMER_RECEIPTS, 3_599_996, ["inv_0007"]),
    (date(2026, 11, 5), CashCategory.LOAN_REPAYMENT, 450_000, ["pattern_loan_instalment"]),
    (date(2026, 11, 15), CashCategory.TAX, 1_200_000, ["pattern_fbr_sales_tax"]),
    (date(2026, 11, 17), CashCategory.UTILITIES, 350_000, ["pattern_electricity", "pattern_gas"]),
    (date(2026, 11, 20), CashCategory.SUPPLIER_BILLS, 3_400_000, ["po_1061"]),
    (date(2026, 11, 30), CashCategory.PAYROLL, 2_400_000, ["pattern_salary_bulk"]),
    (date(2026, 12, 1), CashCategory.RENT, 900_000, ["pattern_rent_br01"]),
    (date(2026, 12, 2), CashCategory.SUPPLIER_BILLS, 4_100_000, ["po_1064"]),
    (date(2026, 12, 5), CashCategory.LOAN_REPAYMENT, 450_000, ["pattern_loan_instalment"]),
    (date(2026, 12, 7), CashCategory.SUPPLIER_BILLS, 3_000_000, ["po_1066", "po_1067"]),
    (date(2026, 12, 15), CashCategory.TAX, 1_350_000, ["pattern_fbr_sales_tax"]),
    (date(2026, 12, 17), CashCategory.UTILITIES, 420_000, ["pattern_electricity", "pattern_gas"]),
    (date(2026, 12, 18), CashCategory.CUSTOMER_RECEIPTS, 2_100_000, ["inv_0011"]),
    (date(2026, 12, 31), CashCategory.PAYROLL, 2_400_000, ["pattern_salary_bulk"]),
    (date(2027, 1, 1), CashCategory.RENT, 900_000, ["pattern_rent_br01"]),
    (date(2027, 1, 5), CashCategory.LOAN_REPAYMENT, 450_000, ["pattern_loan_instalment"]),
    (date(2027, 1, 15), CashCategory.TAX, 1_500_000, ["pattern_fbr_sales_tax"]),
    (date(2027, 1, 17), CashCategory.UTILITIES, 450_000, ["pattern_electricity", "pattern_gas"]),
]

# Statistical weekly estimates in rupees: POS takings rise into winter; routine bills.
POS_WEEKLY = [3.0, 3.1, 3.1, 3.2, 3.3, 3.5, 3.4, 3.8, 4.0, 4.1, 3.9, 3.6, 3.5]
ROUTINE_BILLS_WEEKLY = [1.8] * 13
INFLOWS = {CashCategory.POS_SALES, CashCategory.CUSTOMER_RECEIPTS, CashCategory.OTHER_INFLOW}


def _m(minor: int) -> Money:
    return Money(minor=minor, currency=CURRENCY)


def build() -> CashForecastResponse:
    run_id = stable_id("fc", "mock", "cash", AS_OF.isoformat())
    weeks: list[CashWeek] = []
    opening = OPENING_MINOR
    for w in range(1, 14):
        start = AS_OF + timedelta(days=1 + 7 * (w - 1))
        end = start + timedelta(days=6)
        lines = [
            CashLine(
                category=CashCategory.POS_SALES,
                direction="in",
                money=_m(round(POS_WEEKLY[w - 1] * 1_000_000) * 100),
                basis="forecast",
                refs=["pattern_pos_settlements"],
            ),
            CashLine(
                category=CashCategory.SUPPLIER_BILLS,
                direction="out",
                money=_m(round(ROUTINE_BILLS_WEEKLY[w - 1] * 1_000_000) * 100),
                basis="forecast",
                refs=["pattern_routine_purchases"],
            ),
        ]
        for when, category, rupees, refs in SCHEDULED:
            if start <= when <= end:
                lines.append(
                    CashLine(
                        category=category,
                        direction="in" if category in INFLOWS else "out",
                        money=_m(rupees * 100),
                        basis="scheduled",
                        refs=refs,
                    )
                )
        inflow = sum(x.money.minor for x in lines if x.direction == "in")
        outflow = sum(x.money.minor for x in lines if x.direction == "out")
        closing = opening + inflow - outflow
        half_band = round(Z90 * WEEKLY_SIGMA_MINOR * math.sqrt(w))
        weeks.append(
            CashWeek(
                week=w,
                start=start,
                end=end,
                opening=_m(opening),
                inflows=_m(inflow),
                outflows=_m(outflow),
                net=_m(inflow - outflow),
                closing=_m(closing),
                closing_low=_m(closing - half_band),
                closing_high=_m(closing + half_band),
                below_buffer=closing < CASH_BUFFER_MINOR,
                lines=lines,
            )
        )
        opening = closing

    lowest = min(weeks, key=lambda wk: wk.closing.minor)
    first_below = next((wk.week for wk in weeks if wk.below_buffer), None)
    shortfall_minor = max(0, CASH_BUFFER_MINOR - lowest.closing.minor)

    opening_fig = money_figure(
        "cash.opening_balance",
        "Cash in the bank today",
        OPENING_MINOR,
        CURRENCY,
        source_refs=["bank_statement.csv#last_line"],
        inputs=[
            money_input(
                "bank_balance", OPENING_MINOR, CURRENCY, Origin.LEDGER, ref="bank_statement.csv"
            )
        ],
    )
    buffer_fig = money_figure(
        "cash.buffer",
        "Your minimum cash buffer",
        CASH_BUFFER_MINOR,
        CURRENCY,
        inputs=[
            money_input(
                "cash_buffer",
                CASH_BUFFER_MINOR,
                CURRENCY,
                Origin.TENANT_POLICY,
                ref="tenant.policies.cash_buffer_minor",
            )
        ],
    )
    lowest_fig = money_figure(
        "cash.lowest_closing",
        f"Lowest forecast balance (week {lowest.week})",
        lowest.closing.minor,
        CURRENCY,
        formula="min over weeks of (opening + inflows - outflows)",
        inputs=[figure_ref(opening_fig)],
        source_refs=[run_id],
    )
    shortfall_fig = money_figure(
        "cash.shortfall_vs_buffer",
        "Shortfall against your buffer",
        shortfall_minor,
        CURRENCY,
        formula="max(0, buffer - lowest_closing)",
        inputs=[figure_ref(buffer_fig), figure_ref(lowest_fig)],
        thresholds=[
            money_threshold(
                "cash_buffer",
                CASH_BUFFER_MINOR,
                CURRENCY,
                Origin.TENANT_POLICY,
                ">=",
                passed=shortfall_minor == 0,
            )
        ],
    )
    receivables = money_figure(
        "cash.open_receivables",
        "Invoices customers still owe",
        (3_599_996 + 2_100_000) * 100,
        CURRENCY,
        source_refs=["inv_0007", "inv_0011"],
        note="customer_invoices.json minus matched customer receipts (answer key) until D4 runs",
    )
    payables = money_figure(
        "cash.open_payables",
        "Supplier bills not yet paid",
        1_845_000 * 100,
        CURRENCY,
        source_refs=["bill_2231"],
    )

    findings = []
    if first_below is not None:
        dip_week = weeks[first_below - 1]
        findings.append(
            Finding(
                id=stable_id("fnd", "cash_below_buffer", AS_OF.isoformat()),
                source="forecast",
                severity="high",
                title=f"Cash dips below your buffer in week {first_below}",
                money_at_stake=_m(shortfall_minor),
                evidence=[
                    Evidence(kind="forecast_run", ref=run_id),
                    Evidence(kind="purchase_order", ref="po_1066"),
                    Evidence(kind="purchase_order", ref="po_1067"),
                ],
                actions=[
                    Action(label="Open forecast", route="/forecast"),
                    Action(label="Optimise payment timing", route="/decisions/payment-timing"),
                    Action(label="Compare financing", route="/financing"),
                ],
                type="cash_below_buffer",
                detail="Winter stock bills in weeks 5 to 7 overlap payroll, rent and the loan instalment.",
                period=Period(start=dip_week.start, end=dip_week.end),
                created_at=GENERATED_AT,
                dedupe_key=f"cash_below_buffer:{dip_week.start.isoformat()}",
                figures=[lowest_fig, buffer_fig, shortfall_fig],
            )
        )

    return CashForecastResponse(
        **envelope(),
        run_id=run_id,
        currency=CURRENCY,
        as_of=AS_OF,
        horizon_weeks=13,
        method=ForecastMethod(
            name="mock_fixture",
            description="Mock data in the contract's shape. Live mode replaces it with Y1.",
            history=Period(start=date(2026, 8, 23), end=AS_OF),
            band="closing +/- 1.2816 x weekly sigma x sqrt(week) (p10 to p90)",
        ),
        opening_balance=opening_fig,
        buffer=buffer_fig,
        lowest_closing=lowest_fig,
        first_week_below_buffer=first_below,
        shortfall=shortfall_fig,
        open_receivables=receivables,
        open_payables=payables,
        weeks=weeks,
        assumptions=[
            money_input("weekly_net_sigma", WEEKLY_SIGMA_MINOR, CURRENCY, Origin.ASSUMPTION),
            value_input("band_z_p10_p90", Z90 * 10_000, Unit.BP, Origin.ASSUMPTION),
        ],
        insufficient_data=[
            InsufficientData(
                need="24 months of POS history (generator v1)",
                why="Seasonal weekly patterns need at least a year of history.",
                blocking=False,
                metric_ids=["cash.closing"],
            )
        ],
        findings=findings,
    )
