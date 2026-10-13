"""Mock financing match: bridging the week-7 cash dip (Rs 2.0M, seasonal working capital).

The catalogue rows are ILLUSTRATIVE stubs until rulebook/financing.yaml (B14) lands, and the
business's DSCR inputs are labelled stub values until engine.analysis (Y2) is wired in. The
cost and instalment maths is real: effective annual cost is the IRR of the borrower's own
cash flows, fees included.
"""

from __future__ import annotations

from datetime import date

from engine.decisions.tvm import annual_rate, irr
from engine.financing.schemas import CatalogueRef, FinancingMatchResponse, FinancingOption
from engine.forecast._contracts import Figure, Money, Origin, Threshold, Unit
from engine.forecast.figures import (
    InsufficientData,
    RuleCheck,
    bp_figure,
    bp_threshold,
    money_figure,
    money_input,
    stable_id,
)
from engine.forecast.mocks import AS_OF, CURRENCY, envelope

AMOUNT = 2_000_000_00
EBITDA_NEXT_12M = 9_600_000_00  # stub until engine.analysis
EXISTING_SERVICE_12M = 5_400_000_00  # loan instalments, stub
KIBOR_STUB = 0.1242
MIN_DSCR = 1.25


def _annuity(principal: float, monthly: float, months: int) -> float:
    return (
        principal / months if monthly == 0 else principal * monthly / (1 - (1 + monthly) ** -months)
    )


def _option(option_id, name, kind, rate_annual, fee, months, style, eligible_rules, dilution=0.0):
    fee_minor = AMOUNT * fee
    monthly = rate_annual / 12
    if style == "annuity":
        pay = _annuity(AMOUNT, monthly, months)
        flows = [AMOUNT - fee_minor] + [-pay] * months
        service_12m = pay * min(12, months)
    elif style == "revolving":  # interest monthly, principal at the end of the facility
        pay = AMOUNT * monthly
        flows = [AMOUNT - fee_minor] + [-pay] * (months - 1) + [-(pay + AMOUNT)]
        service_12m = pay * min(12, months)
    elif style == "equity":
        pay, flows, service_12m = 0.0, [], 0.0
    else:  # supplier credit: the cost is the early-payment discount given up
        pay = AMOUNT
        flows = [AMOUNT * (1 - fee)] + [0.0] * (months - 1) + [-AMOUNT]
        service_12m = 0.0
    r = irr(flows) if flows else None
    eac = annual_rate(r.rate) if r is not None and r.valid else None
    dscr_after = EBITDA_NEXT_12M / (EXISTING_SERVICE_12M + service_12m)
    stub = [
        money_input(
            "ebitda_next_12m",
            EBITDA_NEXT_12M,
            CURRENCY,
            Origin.STUB,
            ref="engine.analysis.coverage",
        ),
        money_input("existing_debt_service_12m", EXISTING_SERVICE_12M, CURRENCY, Origin.STUB),
    ]
    figures = [
        bp_figure(
            "financing.effective_annual_cost",
            "Effective annual cost (fees included)",
            eac,
            formula="annualise(IRR of borrower cash flows)",
            source_refs=[f"stub:{option_id}"],
        )
        if eac is not None
        else Figure(
            metric_id="financing.effective_annual_cost",
            label="Effective annual cost",
            unit=Unit.BP,
            status="not_applicable",
            note="equity has no interest cost: the cost is dilution and the investor's target return",
        ),
        money_figure(
            "financing.instalment",
            "Monthly payment",
            pay if style != "supplier_credit" else 0,
            CURRENCY,
        ),
        money_figure(
            "financing.total_cost",
            "Total cost over the term",
            -sum(flows) if flows else 0,
            CURRENCY,
        ),
        bp_figure(
            "financing.dscr_after",
            "Debt-service cover after borrowing",
            dscr_after,
            inputs=stub,
            formula="ebitda_next_12m / (existing + new debt service, next 12 months)",
            thresholds=[
                bp_threshold("min_dscr", MIN_DSCR, Origin.RULEBOOK, ">=", dscr_after >= MIN_DSCR)
            ],
        ),
        bp_figure("financing.dilution", "Share of the business given up", dilution),
    ]
    checks = [
        RuleCheck(rule_id=rid, description=desc, metric_id=metric, threshold=thr, passed=ok)
        for rid, desc, metric, thr, ok in eligible_rules
    ]
    checks.append(
        RuleCheck(
            rule_id="T-SOL-DSCR-01",
            description="Debt-service cover stays at or above the minimum",
            metric_id="financing.dscr_after",
            threshold=bp_threshold(
                "min_dscr", MIN_DSCR, Origin.RULEBOOK, ">=", dscr_after >= MIN_DSCR
            ),
            passed=dscr_after >= MIN_DSCR,
        )
    )
    eligible = all(c.passed for c in checks if c.hard and c.passed is not None)
    if any(c.passed is None for c in checks):
        eligible = None if eligible else False
    figures = [f for f in figures if f is not None]
    return FinancingOption(
        option_id=option_id,
        name=name,
        kind=kind,
        provider_label=None,
        illustrative=True,
        source_ref=f"stub:{option_id} (illustrative until rulebook/financing.yaml)",
        eligible=eligible,
        eligibility=checks,
        verification="indicative_range",
        figures=figures,
    ), eac


def build() -> FinancingMatchResponse:
    years_trading = Threshold(
        name="min_years_trading",
        value=24,
        unit=Unit.MONTHS,
        origin=Origin.STUB,
        comparison=">=",
        passed=True,
    )
    options = [
        _option(
            "pk_running_finance",
            "Running finance (overdraft line)",
            "running_finance",
            KIBOR_STUB + 0.035,
            0.005,
            12,
            "revolving",
            [
                (
                    "RF-01",
                    "Trading for at least two years",
                    "business.months_trading",
                    years_trading,
                    True,
                )
            ],
        ),
        _option(
            "pk_term_loan_sme",
            "SME term loan",
            "term_loan",
            KIBOR_STUB + 0.045,
            0.01,
            36,
            "annuity",
            [
                (
                    "TL-01",
                    "Trading for at least two years",
                    "business.months_trading",
                    years_trading,
                    True,
                )
            ],
        ),
        _option(
            "pk_supplier_credit",
            "Extended supplier credit (60 days)",
            "supplier_credit",
            0.0,
            0.02,
            2,
            "supplier_credit",
            [
                (
                    "SC-01",
                    "Supplier offers extended terms",
                    "supplier.terms_available",
                    Threshold(
                        name="supplier_terms_confirmed",
                        value=1,
                        unit=Unit.COUNT,
                        origin=Origin.STUB,
                        comparison=">=",
                        passed=None,
                    ),
                    None,
                )
            ],
        ),
        _option(
            "pk_angel_equity",
            "Angel investment",
            "equity_angel",
            0.0,
            0.0,
            1,
            "equity",
            [
                (
                    "EQ-01",
                    "Ticket size at least Rs 10M",
                    "request.amount",
                    Threshold(
                        name="min_ticket",
                        money=Money(minor=10_000_000_00, currency=CURRENCY),
                        unit=Unit.MINOR,
                        origin=Origin.STUB,
                        comparison=">=",
                        passed=False,
                    ),
                    False,
                )
            ],
            dilution=0.10,
        ),
    ]
    ranked = sorted(
        ((o, eac) for o, eac in options if o.eligible),
        key=lambda t: t[1] if t[1] is not None else 9e9,
    )
    rank_of = {o.option_id: i + 1 for i, (o, _) in enumerate(ranked)}
    out = []
    for o, _ in options:
        reasons = ["lowest_effective_cost"] if rank_of.get(o.option_id) == 1 else []
        if o.kind == "running_finance":
            reasons.append("matches_seasonal_need")
        out.append(o.model_copy(update={"rank": rank_of.get(o.option_id), "rank_reasons": reasons}))
    out.sort(key=lambda o: (o.rank is None, o.rank or 0))
    stub_inputs = [money_input("ebitda_next_12m", EBITDA_NEXT_12M, CURRENCY, Origin.STUB)]
    return FinancingMatchResponse(
        **envelope(),
        run_id=stable_id("fin", "mock", AS_OF.isoformat()),
        currency=CURRENCY,
        as_of=AS_OF,
        amount=Money(minor=AMOUNT, currency=CURRENCY),
        purpose="working_capital_seasonal",
        catalogue=CatalogueRef(version="stub-0", as_of=date(2026, 10, 12)),
        business_figures=[
            money_figure(
                "business.ebitda_next_12m",
                "Operating profit before interest, next 12 months",
                EBITDA_NEXT_12M,
                CURRENCY,
                inputs=stub_inputs,
            ),
            bp_figure(
                "solvency.dscr_forward",
                "Debt-service cover today",
                EBITDA_NEXT_12M / EXISTING_SERVICE_12M,
                inputs=stub_inputs,
            ),
            money_figure(
                "cash.shortfall_vs_buffer",
                "Cash shortfall against your buffer (week 7)",
                1_753_881_00,
                CURRENCY,
            ),
            bp_figure("market.reference_lending_rate", "6-month KIBOR (stub)", KIBOR_STUB),
        ],
        options=out,
        insufficient_data=[
            InsufficientData(
                need="Supplier confirmation of 60-day terms",
                why="Supplier credit eligibility depends on it.",
                blocking=False,
                metric_ids=["supplier.terms_available"],
            )
        ],
    )
