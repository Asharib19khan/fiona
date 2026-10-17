"""Debt-versus-equity comparison (Y4).

The calculator deliberately accepts terms only when they were supplied by the caller.  It
can derive the business cash path and the existing debt service from the synthetic fixture,
but it never invents a loan quote, an investor valuation, or a project return.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext

from engine.analysis import rulebook
from engine.analysis.coverage import dscr_forward, max_principal_at_dscr
from engine.decisions.schemas import (
    AmortisationRow,
    CashPathPoint,
    DebtEquityRequest,
    DecisionOption,
    DecisionRecommendation,
    DecisionResponse,
)
from engine.financing.business import business_figures
from engine.forecast._contracts import Figure, FigureInput, Origin, Unit
from engine.forecast.cash.engine import forecast_cash
from engine.forecast.figures import (
    InsufficientData,
    RuleCheck,
    bp_threshold,
    money_figure,
    money_input,
    money_threshold,
    stable_id,
)
from engine.forecast.ledger_source import LedgerSnapshot

ENGINE_VERSION = "decisions/debt-equity/0.1.0"


def _month_after(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _schedule(
    amount: int, body: DebtEquityRequest, rate_bp: int | None = None
) -> list[tuple[int, int, int, int]]:
    """Return month, payment, interest, principal using integer minor-unit outputs."""
    if body.debt is None:
        return []
    terms = body.debt
    rate = Decimal(rate_bp if rate_bp is not None else terms.annual_rate_bp) / Decimal(120_000)
    balance = Decimal(amount)
    rows: list[tuple[int, int, int, int]] = []
    principal_paid = 0
    with localcontext() as ctx:
        ctx.prec = 40
        repay_months = terms.term_months - terms.grace_months
        if terms.repayment == "annuity":
            payment = (
                balance * rate / (Decimal(1) - (Decimal(1) + rate) ** -repay_months)
                if rate
                else balance / repay_months
            )
        else:
            payment = Decimal(0)
        for month in range(1, terms.term_months + 1):
            interest = balance * rate
            principal = Decimal(0)
            if month > terms.grace_months:
                if terms.repayment == "annuity":
                    principal = min(balance, payment - interest)
                elif terms.repayment == "equal_principal":
                    principal = min(balance, Decimal(amount) / repay_months)
                elif month == terms.term_months:
                    principal = balance
            paid_interest, paid_principal = _round(interest), _round(principal)
            paid_principal = min(paid_principal, amount - principal_paid)
            if month == terms.term_months:
                # The visible schedule is in integer minor units, so settle any intermediate
                # rounding difference here. Its principal always reconciles exactly to amount.
                paid_principal = amount - principal_paid
            balance -= principal
            rows.append((month, paid_interest + paid_principal, paid_interest, paid_principal))
            principal_paid += paid_principal
    return rows


def _service_12m(amount: int, body: DebtEquityRequest, rate_bp: int | None = None) -> int:
    return sum(payment for month, payment, _, _ in _schedule(amount, body, rate_bp) if month <= 12)


def _bp(
    metric_id: str,
    label: str,
    value_bp: int | None,
    *,
    inputs: list[FigureInput] | None = None,
    note: str | None = None,
) -> Figure:
    if value_bp is None:
        return Figure(
            metric_id=metric_id,
            label=label,
            unit=Unit.BP,
            status="insufficient_data",
            missing=["scheduled debt service"],
            note=note,
        )
    return Figure(
        metric_id=metric_id,
        label=label,
        value=value_bp,
        unit=Unit.BP,
        inputs=inputs or [],
        note=note,
    )


def _unknown(metric_id: str, label: str, missing: str) -> Figure:
    return Figure(
        metric_id=metric_id,
        label=label,
        unit=Unit.MINOR,
        status="insufficient_data",
        missing=[missing],
    )


def _debt_option(
    body: DebtEquityRequest,
    snap: LedgerSnapshot,
    cash,
    ebitda: int | None,
    existing_service: int,
    buffer: int | None,
) -> tuple[DecisionOption, list[RuleCheck], list[InsufficientData], int | None]:
    currency, amount = snap.currency, body.amount.minor
    gaps: list[InsufficientData] = []
    if body.debt is None:
        gaps.append(
            InsufficientData(
                need="Indicative debt terms",
                why="Coverage and repayment depend on rate, tenor and repayment structure.",
                blocking=True,
                metric_ids=["decision.dscr_after_debt"],
            )
        )
        check = RuleCheck(
            rule_id="DE-00",
            description="Debt terms are available to test coverage",
            metric_id="decision.dscr_after_debt",
            threshold=bp_threshold("minimum_DSCR", 1.25, Origin.RULEBOOK, ">=", None),
            passed=None,
        )
        return (
            DecisionOption(
                option_id="A_debt",
                label="Borrow",
                eligible=None,
                figures=[
                    _unknown(
                        "decision.dscr_after_debt",
                        "Debt-service cover after borrowing",
                        "indicative debt terms",
                    )
                ],
                rule_checks=[check],
            ),
            [check],
            gaps,
            None,
        )
    if ebitda is None or buffer is None:
        missing = "forward EBITDA" if ebitda is None else "cash buffer"
        gaps.append(
            InsufficientData(
                need=missing.replace("EBITDA", "EBITDA forecast"),
                why="It is needed to test whether new debt is affordable.",
                blocking=True,
                metric_ids=["decision.dscr_after_debt"],
            )
        )
        check = RuleCheck(
            rule_id="DE-00",
            description="Debt coverage inputs are available",
            metric_id="decision.dscr_after_debt",
            threshold=bp_threshold("minimum_DSCR", 1.25, Origin.RULEBOOK, ">=", None),
            passed=None,
        )
        return (
            DecisionOption(
                option_id="A_debt",
                label="Borrow",
                eligible=None,
                figures=[
                    _unknown(
                        "decision.dscr_after_debt", "Debt-service cover after borrowing", missing
                    )
                ],
                rule_checks=[check],
            ),
            [check],
            gaps,
            None,
        )

    min_base = rulebook.value_bp("T-SOL-DSCR-01")
    min_downside = rulebook.value_bp("T-SOL-DSCR-02")
    downside_rate = (
        body.debt.annual_rate_bp + 300
        if (snap.country or "PK") == "PK"
        else body.debt.annual_rate_bp + 200
    )
    service = _service_12m(amount, body)
    downside_service = _service_12m(amount, body, downside_rate)
    base = dscr_forward(ebitda, existing_service, service)
    downside = dscr_forward(ebitda * 8500 // 10_000, existing_service, downside_service)
    max_base = max_principal_at_dscr(
        ebitda, existing_service, min_base, lambda principal: _service_12m(principal, body), amount
    )
    max_downside = max_principal_at_dscr(
        ebitda * 8500 // 10_000,
        existing_service,
        min_downside,
        lambda principal: _service_12m(principal, body, downside_rate),
        amount,
    )
    max_debt = min(max_base, max_downside)
    base_ok = base.value_bp is not None and base.value_bp >= min_base
    downside_ok = downside.value_bp is not None and downside.value_bp >= min_downside
    schedule = _schedule(amount, body)
    amortisation = []
    for month, payment, interest, principal in schedule:
        balance = max(0, amount - sum(row[3] for row in schedule[:month]))
        amortisation.append(
            AmortisationRow(
                month=month,
                due_on=_month_after(snap.as_of, month),
                payment={"minor": payment, "currency": currency},
                interest={"minor": interest, "currency": currency},
                principal={"minor": principal, "currency": currency},
                balance={"minor": balance, "currency": currency},
            )
        )
    fee = _round(Decimal(amount) * Decimal(body.debt.upfront_fee_bp) / Decimal(10_000))
    path = []
    for week in cash.weeks:
        payments = sum(row[1] for row in schedule if _month_after(snap.as_of, row[0]) <= week.end)
        path.append(
            CashPathPoint(
                week=week.week,
                closing_without=week.closing,
                closing_with={
                    "minor": week.closing.minor + amount - fee - payments,
                    "currency": currency,
                },
            )
        )
    cash_ok = min(point.closing_with.minor for point in path) >= buffer
    checks = [
        RuleCheck(
            rule_id="DE-03",
            description="Base-case debt-service cover meets the rulebook minimum",
            metric_id="decision.dscr_after_debt",
            threshold=bp_threshold(
                "minimum_base_DSCR", min_base / 10_000, Origin.RULEBOOK, ">=", base_ok
            ),
            passed=base_ok,
        ),
        RuleCheck(
            rule_id="DE-04",
            description="Downside debt-service cover remains at or above 1.0x",
            metric_id="decision.dscr_after_debt_downside",
            threshold=bp_threshold(
                "minimum_downside_DSCR", min_downside / 10_000, Origin.RULEBOOK, ">=", downside_ok
            ),
            passed=downside_ok,
        ),
        RuleCheck(
            rule_id="DE-02",
            description="Loan proceeds and repayments keep forecast cash above the buffer",
            metric_id="decision.cash_low_point_with_debt",
            threshold=money_threshold(
                "cash_buffer", buffer, currency, Origin.TENANT_POLICY, ">=", cash_ok
            ),
            passed=cash_ok,
        ),
    ]
    figures = [
        money_figure(
            "decision.debt_service_next_12m",
            "New debt service in the next 12 months",
            service,
            currency,
            source_refs=[ENGINE_VERSION],
        ),
        _bp(
            "decision.dscr_after_debt",
            "Debt-service cover after borrowing",
            base.value_bp,
            inputs=[
                money_input("forward_ebitda", ebitda, currency, Origin.STUB),
                money_input("existing_debt_service", existing_service, currency, Origin.LEDGER),
            ],
        ),
        _bp(
            "decision.dscr_after_debt_downside",
            "Debt-service cover after borrowing in the downside case",
            downside.value_bp,
            note="EBITDA reduced 15%; Pakistan rate sensitivity is +300 bp.",
        ),
        money_figure(
            "decision.max_debt_downside",
            "Largest debt amount that passes downside coverage",
            max_debt,
            currency,
            source_refs=[ENGINE_VERSION],
        ),
        money_figure(
            "decision.cash_low_point_with_debt",
            "Lowest forecast cash with the loan",
            min(point.closing_with.minor for point in path),
            currency,
        ),
    ]
    return (
        DecisionOption(
            option_id="A_debt",
            label=f"Borrow {amount} {currency} over {body.debt.term_months} months",
            eligible=base_ok and downside_ok and cash_ok,
            figures=figures,
            rule_checks=checks,
            amortisation=amortisation,
            cash_path=path,
        ),
        checks,
        gaps,
        max_debt,
    )


def compare_debt_equity(
    body: DebtEquityRequest, snap: LedgerSnapshot, *, mode: str, generated_at: datetime
) -> DecisionResponse:
    """Compare the supplied terms with the tenant's fixture-backed cash forecast."""
    if body.amount.currency != snap.currency:
        raise ValueError(f"amount must be in {snap.currency}")
    cash = forecast_cash(snap)
    business = business_figures(snap)
    buffer = snap.cash_buffer_minor
    amount, currency = body.amount.minor, snap.currency
    debt, debt_checks, gaps, max_debt = _debt_option(
        body,
        snap,
        cash,
        business.ebitda_next_12m_minor,
        business.existing_service_12m_minor,
        buffer,
    )
    capacity = (
        max(0, min(week.closing.minor for week in cash.weeks) - buffer) if buffer is not None else 0
    )
    internal_ok = buffer is not None and amount <= capacity
    internal_check = RuleCheck(
        rule_id="DE-02",
        description="Internal funding leaves every forecast week at or above the buffer",
        metric_id="decision.internal_capacity",
        threshold=money_threshold(
            "internal_capacity", capacity, currency, Origin.TENANT_POLICY, ">=", internal_ok
        ),
        passed=internal_ok if buffer is not None else None,
    )
    internal_path = [
        CashPathPoint(
            week=week.week,
            closing_without=week.closing,
            closing_with={"minor": week.closing.minor - amount, "currency": currency},
        )
        for week in cash.weeks
    ]
    internal = DecisionOption(
        option_id="C_internal",
        label="Use internal cash",
        eligible=internal_ok if buffer is not None else None,
        figures=[
            money_figure(
                "decision.internal_capacity", "Cash available above the buffer", capacity, currency
            ),
            money_figure(
                "decision.internal_shortfall",
                "Funding still needed after internal cash",
                max(0, amount - capacity),
                currency,
            ),
        ],
        rule_checks=[internal_check],
        cash_path=internal_path,
    )

    equity_gaps: list[InsufficientData] = []
    pre_money = (
        body.equity.pre_money_valuation.minor
        if body.equity and body.equity.pre_money_valuation
        else None
    )
    stake = body.equity.stake_offered_bp if body.equity else None
    if pre_money is None and stake is not None and stake < 10_000:
        pre_money = amount * (10_000 - stake) // stake
    if pre_money is not None:
        dilution_bp = _round(Decimal(amount) * Decimal(10_000) / Decimal(pre_money + amount))
        dilution_ok = dilution_bp <= rulebook.value_bp("T-DEC-DIL-01")
        equity_checks = [
            RuleCheck(
                rule_id="DE-06",
                description="Dilution above 25% needs an owner decision on control terms",
                metric_id="decision.dilution",
                threshold=bp_threshold(
                    "dilution_control_flag",
                    rulebook.value_bp("T-DEC-DIL-01") / 10_000,
                    Origin.RULEBOOK,
                    "<=",
                    dilution_ok,
                ),
                passed=dilution_ok,
                hard=False,
            )
        ]
        equity = DecisionOption(
            option_id="B_equity",
            label=f"Raise {amount} {currency} in equity",
            eligible=True,
            figures=[
                money_figure(
                    "decision.pre_money_valuation",
                    "Pre-money valuation",
                    pre_money,
                    currency,
                    inputs=[money_input("pre_money_valuation", pre_money, currency, Origin.USER)],
                ),
                _bp("decision.dilution", "Share of the business given up", dilution_bp),
            ],
            rule_checks=equity_checks,
            cash_path=[
                CashPathPoint(
                    week=week.week,
                    closing_without=week.closing,
                    closing_with={"minor": week.closing.minor + amount, "currency": currency},
                )
                for week in cash.weeks
            ],
        )
    else:
        equity_gaps.append(
            InsufficientData(
                need="Investor valuation or proposed stake",
                why="Equity cannot be compared without showing the dilution and control trade-off.",
                blocking=True,
                metric_ids=["decision.dilution"],
            )
        )
        equity_check = RuleCheck(
            rule_id="DE-06",
            description="Investor valuation or proposed stake is available",
            metric_id="decision.dilution",
            threshold=bp_threshold("dilution_control_flag", 0.25, Origin.RULEBOOK, "<=", None),
            passed=None,
            hard=False,
        )
        equity = DecisionOption(
            option_id="B_equity",
            label="Raise equity",
            eligible=None,
            figures=[
                _unknown(
                    "decision.dilution",
                    "Share of the business given up",
                    "investor valuation or proposed stake",
                )
            ],
            rule_checks=[equity_check],
        )

    defer = DecisionOption(
        option_id="E_defer",
        label="Defer or stage the investment",
        eligible=True,
        figures=[
            money_figure("decision.funding_requirement", "Funding requirement", amount, currency)
        ],
        rule_checks=[],
    )
    if internal_ok:
        recommendation = DecisionRecommendation(
            outcome="recommend",
            option_id="C_internal",
            rule_trace=[internal_check],
            reason_codes=["internal_cash_keeps_buffer", "no_fixed_repayment_or_dilution"],
        )
    elif debt.eligible:
        recommendation = DecisionRecommendation(
            outcome="recommend",
            option_id="A_debt",
            rule_trace=debt_checks,
            reason_codes=["base_and_downside_coverage_pass", "cash_stays_above_buffer"],
        )
    elif equity.eligible:
        recommendation = DecisionRecommendation(
            outcome="recommend",
            option_id="B_equity",
            rule_trace=equity.rule_checks,
            reason_codes=["debt_does_not_pass_coverage", "equity_has_no_fixed_repayment"],
        )
    elif max_debt and max_debt > 0:
        recommendation = DecisionRecommendation(
            outcome="no_clear_winner",
            option_id=None,
            rule_trace=debt_checks,
            reason_codes=["debt_requires_smaller_size_or_mixed_funding"],
        )
    else:
        recommendation = DecisionRecommendation(
            outcome="insufficient_data",
            option_id=None,
            rule_trace=[*debt_checks, *equity.rule_checks, internal_check],
            reason_codes=["terms_or_valuation_required"],
        )
    return DecisionResponse(
        api_version="v1",
        mode=mode,
        tenant_id=snap.tenant_id,
        generated_at=generated_at,
        decision="debt_equity",
        run_id=stable_id(
            "dec", ENGINE_VERSION, snap.tenant_id, snap.as_of.isoformat(), str(amount)
        ),
        currency=currency,
        as_of=snap.as_of,
        inputs=[
            money_input("amount", amount, currency, Origin.USER),
            money_input("cash_buffer", buffer, currency, Origin.TENANT_POLICY)
            if buffer is not None
            else FigureInput(name="cash_buffer", unit=Unit.MINOR, origin=Origin.TENANT_POLICY),
        ],
        figures=[
            cash.lowest_closing,
            cash.buffer,
            money_figure(
                "decision.existing_debt_service",
                "Existing debt service over the next 12 months",
                business.existing_service_12m_minor,
                currency,
                source_refs=[business.existing_service_basis],
            ),
            _bp(
                "solvency.dscr_forward",
                "Current forward debt-service cover",
                None
                if business.ebitda_next_12m_minor is None
                else dscr_forward(
                    business.ebitda_next_12m_minor, business.existing_service_12m_minor
                ).value_bp,
                note="Forward EBITDA is currently a labelled operating-cash-flow proxy.",
            ),
        ],
        options=[debt, equity, internal, defer],
        recommendation=recommendation,
        insufficient_data=[*gaps, *equity_gaps],
    )
