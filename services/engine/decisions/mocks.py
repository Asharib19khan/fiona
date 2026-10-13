"""Mocks for the decision calculators and the payment-timing optimiser.

They read the cash-forecast mock, so every screen tells one consistent story: winter stock
pushes cash below the buffer in week 7. Inputs labelled `stub` stand in for other lanes'
engines (Y2 ratios) until those land. All data is SYNTHETIC.
"""

from __future__ import annotations

from datetime import date, timedelta

from engine.decisions.schemas import (
    AmortisationRow,
    BillTiming,
    CashPathPoint,
    DecisionOption,
    DecisionRecommendation,
    DecisionResponse,
    EarlyPaymentTerms,
    PaymentTimingResponse,
    TimingWeek,
)
from engine.forecast._contracts import Money, Origin
from engine.forecast.figures import (
    InsufficientData,
    RuleCheck,
    bp_figure,
    bp_input,
    bp_threshold,
    money_figure,
    money_input,
    money_threshold,
    stable_id,
)
from engine.forecast.mocks import AS_OF, CASH_BUFFER_MINOR, CURRENCY, envelope
from engine.forecast.mocks import cash as cash_mock

COST_OF_MONEY = 0.22  # rulebook launch_lab.cost_of_capital_annual_bp (provisional)
EBITDA_NEXT_12M = 9_600_000_00
EXISTING_SERVICE_12M = 5_400_000_00
MIN_DSCR = 1.25


def _m(minor: float) -> Money:
    return Money(minor=round(minor), currency=CURRENCY)


def _stub_inputs():
    return [
        money_input(
            "ebitda_next_12m",
            EBITDA_NEXT_12M,
            CURRENCY,
            Origin.STUB,
            ref="engine.analysis.coverage",
        ),
        money_input("existing_debt_service_12m", EXISTING_SERVICE_12M, CURRENCY, Origin.STUB),
    ]


def debt_equity() -> DecisionResponse:
    cash = cash_mock.build()
    amount, rate, months = 2_000_000_00, 0.19, 24
    i = rate / 12
    pay = amount * i / (1 - (1 + i) ** -months)
    rows, bal = [], float(amount)
    for k in range(1, months + 1):
        interest = bal * i
        principal = pay - interest
        bal -= principal
        rows.append(
            AmortisationRow(
                month=k,
                due_on=date(2026, 11, 22) + timedelta(days=30 * (k - 1)),
                payment=_m(pay),
                interest=_m(interest),
                principal=_m(principal),
                balance=_m(max(bal, 0)),
            )
        )
    dscr_after = EBITDA_NEXT_12M / (EXISTING_SERVICE_12M + 12 * pay)
    path = []
    for w in cash.weeks:
        instalments = sum(1 for r in rows if r.due_on <= w.end) * pay
        path.append(
            CashPathPoint(
                week=w.week,
                closing_without=w.closing,
                closing_with=_m(w.closing.minor + amount - instalments),
            )
        )
    low_with = min(p.closing_with.minor for p in path)
    debt_checks = [
        RuleCheck(
            rule_id="T-SOL-DSCR-01",
            description="Debt-service cover after the loan stays at or above the minimum",
            metric_id="decision.dscr_after_debt",
            threshold=bp_threshold(
                "min_dscr", MIN_DSCR, Origin.RULEBOOK, ">=", dscr_after >= MIN_DSCR
            ),
            passed=dscr_after >= MIN_DSCR,
        ),
        RuleCheck(
            rule_id="DE-02",
            description="Cash stays above the buffer in every forecast week",
            metric_id="decision.cash_low_point_with_debt",
            threshold=money_threshold(
                "cash_buffer",
                CASH_BUFFER_MINOR,
                CURRENCY,
                Origin.TENANT_POLICY,
                ">=",
                low_with >= CASH_BUFFER_MINOR,
            ),
            passed=low_with >= CASH_BUFFER_MINOR,
        ),
    ]
    stake, pre_money = 0.0625, 30_000_000_00
    equity_checks = [
        RuleCheck(
            rule_id="DE-03",
            description="Owner keeps control (stake given up below 25%)",
            metric_id="decision.dilution",
            threshold=bp_threshold("max_dilution", 0.25, Origin.DRAFT_DEFAULT, "<=", True),
            passed=True,
        ),
    ]
    options = [
        DecisionOption(
            option_id="debt",
            label="Borrow Rs 2.0M over 24 months",
            eligible=True,
            rule_checks=debt_checks,
            amortisation=rows,
            cash_path=path,
            figures=[
                money_figure(
                    "decision.instalment",
                    "Monthly instalment",
                    pay,
                    CURRENCY,
                    formula="P x i / (1 - (1 + i)^-n)",
                    inputs=[
                        money_input("principal", amount, CURRENCY, Origin.USER),
                        bp_input("annual_rate", rate, Origin.STUB),
                    ],
                ),
                money_figure(
                    "decision.total_interest", "Total interest", pay * months - amount, CURRENCY
                ),
                bp_figure(
                    "decision.dscr_after_debt",
                    "Debt-service cover after the loan",
                    dscr_after,
                    inputs=_stub_inputs(),
                ),
                money_figure(
                    "decision.cash_low_point_with_debt",
                    "Lowest weekly cash with the loan",
                    low_with,
                    CURRENCY,
                ),
            ],
        ),
        DecisionOption(
            option_id="equity",
            label="Sell 6.25% to an investor for Rs 2.0M",
            eligible=True,
            rule_checks=equity_checks,
            figures=[
                bp_figure(
                    "decision.dilution",
                    "Share of the business given up",
                    stake,
                    formula="amount / (pre_money + amount)",
                    inputs=[money_input("pre_money_valuation", pre_money, CURRENCY, Origin.USER)],
                ),
                bp_figure(
                    "decision.cost_of_equity",
                    "Return the investor expects",
                    0.30,
                    inputs=[bp_input("target_return", 0.30, Origin.ASSUMPTION)],
                ),
                money_figure(
                    "decision.cash_low_point_with_equity",
                    "Lowest weekly cash with the investment",
                    min(w.closing.minor for w in cash.weeks) + amount,
                    CURRENCY,
                ),
            ],
        ),
    ]
    trace = [
        *debt_checks,
        RuleCheck(
            rule_id="DE-04",
            description="After-tax cost of debt is below the cost of equity",
            metric_id="decision.after_tax_cost_of_debt",
            threshold=bp_threshold(
                "cost_of_equity", 0.3, Origin.ASSUMPTION, "<", rate * (1 - 0.29) < 0.3
            ),
            passed=rate * (1 - 0.29) < 0.3,
        ),
    ]
    return DecisionResponse(
        **envelope(),
        decision="debt_equity",
        run_id=stable_id("dec", "mock", "debt_equity"),
        currency=CURRENCY,
        as_of=AS_OF,
        inputs=[
            money_input("amount", amount, CURRENCY, Origin.USER),
            bp_input("tax_rate", 0.29, Origin.RULEBOOK),
        ],
        figures=[
            cash.lowest_closing,
            cash.buffer,
            bp_figure(
                "solvency.dscr_forward",
                "Debt-service cover today",
                EBITDA_NEXT_12M / EXISTING_SERVICE_12M,
                inputs=_stub_inputs(),
            ),
        ],
        options=options,
        recommendation=DecisionRecommendation(
            outcome="recommend",
            option_id="debt",
            rule_trace=trace,
            reason_codes=[
                "debt_cheaper_after_tax",
                "cover_stays_above_minimum",
                "keeps_full_ownership",
            ],
        ),
    )


def dividend() -> DecisionResponse:
    cash = cash_mock.build()
    proposed = 1_500_000_00
    lowest = min(w.closing.minor for w in cash.weeks)
    after_dip = min(w.closing.minor for w in cash.weeks if w.week >= 9)
    safe_now = max(0, lowest - CASH_BUFFER_MINOR)
    safe_later = max(0, after_dip - CASH_BUFFER_MINOR)
    now_ok = proposed <= safe_now
    later_ok = proposed <= safe_later
    options = [
        DecisionOption(
            option_id="pay_now",
            label="Pay Rs 1.5M now",
            eligible=now_ok,
            figures=[
                money_figure(
                    "decision.max_safe_dividend_now",
                    "Largest dividend that keeps cash above the buffer",
                    safe_now,
                    CURRENCY,
                    formula="max(0, lowest forecast closing - buffer)",
                ),
            ],
            rule_checks=[
                RuleCheck(
                    rule_id="DV-01",
                    description="Cash stays above the buffer after the dividend",
                    metric_id="decision.max_safe_dividend_now",
                    threshold=money_threshold(
                        "proposed_dividend", proposed, CURRENCY, Origin.USER, "<=", now_ok
                    ),
                    passed=now_ok,
                )
            ],
        ),
        DecisionOption(
            option_id="pay_after_week_9",
            label="Pay Rs 1.5M after the winter stock is paid for",
            eligible=later_ok,
            figures=[
                money_figure(
                    "decision.max_safe_dividend_after_week_9",
                    "Largest safe dividend from week 9",
                    safe_later,
                    CURRENCY,
                ),
            ],
            rule_checks=[
                RuleCheck(
                    rule_id="DV-01",
                    description="Cash stays above the buffer after the dividend",
                    metric_id="decision.max_safe_dividend_after_week_9",
                    threshold=money_threshold(
                        "proposed_dividend", proposed, CURRENCY, Origin.USER, "<=", later_ok
                    ),
                    passed=later_ok,
                )
            ],
        ),
    ]
    return DecisionResponse(
        **envelope(),
        decision="dividend",
        run_id=stable_id("dec", "mock", "dividend"),
        currency=CURRENCY,
        as_of=AS_OF,
        inputs=[money_input("proposed_dividend", proposed, CURRENCY, Origin.USER)],
        figures=[cash.lowest_closing, cash.buffer],
        options=options,
        recommendation=DecisionRecommendation(
            outcome="recommend",
            option_id="pay_after_week_9",
            rule_trace=options[0].rule_checks,
            reason_codes=["dividend_now_breaches_buffer", "safe_after_winter_stock_paid"],
        ),
        insufficient_data=[
            InsufficientData(
                need="Reinvestment return for the winter range",
                why="Needed to compare paying out with reinvesting.",
                blocking=False,
                metric_ids=["decision.reinvestment_return"],
            )
        ],
    )


def _annualised_discount(discount: float, within: int, net: int) -> float:
    return (1 / (1 - discount)) ** (365 / (net - within)) - 1


def payment_timing() -> PaymentTimingResponse:
    cash = cash_mock.build()
    week_of = {w.week: w for w in cash.weeks}
    bills = [
        (
            "bill_2231",
            "sup_017",
            "Mehran Garments",
            1_845_000_00,
            date(2026, 10, 17),
            date(2026, 10, 24),
            None,
        ),
        (
            "bill_2244",
            "sup_031",
            "Northern Wool Traders",
            1_800_000_00,
            date(2026, 11, 26),
            date(2026, 12, 26),
            (0.02, 10, 30),
        ),
        (
            "bill_2245",
            "sup_031",
            "Northern Wool Traders",
            1_200_000_00,
            date(2026, 11, 26),
            date(2027, 1, 10),
            (0.01, 10, 45),
        ),
    ]

    def week_for(d: date) -> int:
        return next((w.week for w in cash.weeks if w.start <= d <= w.end), 13)

    out, total_saving = [], 0.0
    for bill_id, sup, name, amount, issued, due, terms in bills:
        figs, checks, action, pay_on = [], [], "pay_on_due", due
        if terms:
            disc, within, net = terms
            ann = _annualised_discount(disc, within, net)
            early_day = issued + timedelta(days=within)
            wk = week_for(early_day)
            closing_if_early = week_of[wk].closing.minor - amount * (1 - disc)
            worth = ann > COST_OF_MONEY
            safe = closing_if_early >= CASH_BUFFER_MINOR
            checks = [
                RuleCheck(
                    rule_id="PT-01",
                    description="The discount earns more than the cost of money",
                    metric_id="payments.annualised_discount_return",
                    threshold=bp_threshold(
                        "cost_of_money", COST_OF_MONEY, Origin.RULEBOOK, ">", worth
                    ),
                    passed=worth,
                ),
                RuleCheck(
                    rule_id="PT-02",
                    description="Paying early keeps cash above the buffer that week",
                    metric_id="payments.closing_if_paid_early",
                    threshold=money_threshold(
                        "cash_buffer", CASH_BUFFER_MINOR, CURRENCY, Origin.TENANT_POLICY, ">=", safe
                    ),
                    passed=safe,
                ),
            ]
            figs = [
                bp_figure(
                    "payments.annualised_discount_return",
                    "Discount as an annual return",
                    ann,
                    formula="(1 / (1 - discount))^(365 / (net_days - discount_days)) - 1",
                ),
                money_figure(
                    "payments.saving_if_early", "Saving if paid early", amount * disc, CURRENCY
                ),
                money_figure(
                    "payments.closing_if_paid_early",
                    f"Cash at the end of week {wk} if paid early",
                    closing_if_early,
                    CURRENCY,
                ),
            ]
            if worth and safe:
                action, pay_on = "pay_early", early_day
                total_saving += amount * disc
        out.append(
            BillTiming(
                bill_id=bill_id,
                supplier_id=sup,
                supplier_name=name,
                amount=_m(amount),
                issue_date=issued,
                due_date=due,
                terms=EarlyPaymentTerms(
                    discount_bp=round(terms[0] * 10_000),
                    within_days=terms[1],
                    net_days=terms[2],
                    origin="bill_text",
                )
                if terms
                else None,
                action=action,
                pay_on=pay_on,
                figures=figs,
                rule_checks=checks,
            )
        )

    weeks = [
        TimingWeek(
            week=w.week,
            start=w.start,
            end=w.end,
            payments=_m(0),
            closing_before=w.closing,
            closing_after=w.closing,
            below_buffer=w.below_buffer,
        )
        for w in cash.weeks
    ]
    return PaymentTimingResponse(
        **envelope(),
        run_id=stable_id("pt", "mock", AS_OF.isoformat()),
        currency=CURRENCY,
        as_of=AS_OF,
        cost_of_money=bp_figure(
            "payments.cost_of_money",
            "Your cost of money",
            COST_OF_MONEY,
            inputs=[bp_input("cost_of_capital_annual", COST_OF_MONEY, Origin.RULEBOOK)],
        ),
        buffer=cash.buffer,
        bills=out,
        weeks=weeks,
        totals=[
            money_figure("payments.total_saving", "Discounts captured", total_saving, CURRENCY)
        ],
    )


def build_all() -> dict:
    return {
        "debt_equity": debt_equity(),
        "dividend": dividend(),
        "payment_timing": payment_timing(),
    }
