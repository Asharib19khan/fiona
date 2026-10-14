"""Payment-timing optimiser for supplier bills with early-payment discounts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext

from pydantic import BaseModel, Field

from engine.decisions.schemas import BillTiming, EarlyPaymentTerms
from engine.forecast._contracts import Money, Origin
from engine.forecast.figures import (
    RuleCheck,
    bp_figure,
    bp_threshold,
    money_figure,
    money_threshold,
)

DISCOUNT_FORMULA = "(1 / (1 - discount))^(365 / (net_days - discount_days)) - 1"


class OpenBill(BaseModel):
    bill_id: str
    supplier_id: str
    supplier_name: str
    amount_minor: int = Field(gt=0)
    issue_date: date
    due_date: date
    terms: EarlyPaymentTerms | None = None


class WeekBalance(BaseModel):
    week: int = Field(ge=1)
    start: date
    end: date
    closing_minor: int


@dataclass(frozen=True)
class _Candidate:
    index: int
    bill: OpenBill
    early_day: date
    early_week_index: int
    due_week_index: int | None
    annualised_return_bp: int
    discount_minor: int


def optimise_payment_timing(
    bills: list[OpenBill],
    weeks: list[WeekBalance],
    *,
    buffer_minor: int,
    cost_of_money_annual_bp: int,
    as_of: date,
    currency: str,
) -> list[BillTiming]:
    """Choose early payment only when return beats funding cost and cash stays safe."""
    ordered_weeks = sorted(weeks, key=lambda week: week.week)
    cash_path = [week.closing_minor for week in ordered_weeks]
    results: list[BillTiming | None] = [None] * len(bills)
    candidates: list[_Candidate] = []

    for index, bill in enumerate(bills):
        baseline_due_week = _week_index_for(bill.due_date, ordered_weeks)
        candidate = _candidate_for(index, bill, ordered_weeks, as_of)
        if candidate is None:
            if _baseline_due_week_below_zero(baseline_due_week, ordered_weeks):
                results[index] = _cannot_pay_on_due(
                    bill, baseline_due_week, ordered_weeks, currency
                )
            else:
                results[index] = _bill_timing(bill, "pay_on_due", bill.due_date, currency)
            continue
        candidates.append(candidate)

    for candidate in sorted(
        candidates, key=lambda item: (-item.annualised_return_bp, item.bill.bill_id)
    ):
        bill = candidate.bill
        closing_if_early = _adjusted_path_for(candidate, cash_path)
        low_closing = min(closing_if_early[candidate.early_week_index :])
        worth_it = candidate.annualised_return_bp > cost_of_money_annual_bp
        cash_safe = low_closing >= buffer_minor
        checks = _rule_checks(
            annualised_return_bp=candidate.annualised_return_bp,
            cost_of_money_annual_bp=cost_of_money_annual_bp,
            low_closing_minor=low_closing,
            buffer_minor=buffer_minor,
            currency=currency,
            worth_it=worth_it,
            cash_safe=cash_safe,
        )
        figures = _figures(
            annualised_return_bp=candidate.annualised_return_bp,
            discount_minor=candidate.discount_minor,
            low_closing_minor=low_closing,
            currency=currency,
        )

        if worth_it and cash_safe:
            action = "pay_early"
            pay_on = candidate.early_day
            cash_path = closing_if_early
        elif _baseline_due_week_below_zero(candidate.due_week_index, ordered_weeks):
            action = "cannot_pay_on_due"
            pay_on = bill.due_date
            checks.append(
                _baseline_due_week_rule(candidate.due_week_index, ordered_weeks, currency)
            )
        else:
            action = "pay_on_due"
            pay_on = bill.due_date

        results[candidate.index] = _bill_timing(
            bill,
            action,
            pay_on,
            currency,
            figures=figures,
            rule_checks=checks,
        )

    return [result for result in results if result is not None]


def _candidate_for(
    index: int, bill: OpenBill, weeks: list[WeekBalance], as_of: date
) -> _Candidate | None:
    terms = bill.terms
    if terms is None or terms.net_days <= terms.within_days:
        return None

    early_day = bill.issue_date + timedelta(days=terms.within_days)
    if early_day <= as_of:
        return None

    early_week_index = _week_index_for(early_day, weeks)
    if early_week_index is None:
        return None

    due_week_index = _week_index_for(bill.due_date, weeks)
    if due_week_index is not None and due_week_index < early_week_index:
        return None

    annualised_return_bp = _annualised_discount_return_bp(
        terms.discount_bp, terms.within_days, terms.net_days
    )
    if annualised_return_bp is None:
        return None

    return _Candidate(
        index=index,
        bill=bill,
        early_day=early_day,
        early_week_index=early_week_index,
        due_week_index=due_week_index,
        annualised_return_bp=annualised_return_bp,
        discount_minor=_discount_minor(bill.amount_minor, terms.discount_bp),
    )


def _annualised_discount_return_bp(discount_bp: int, within_days: int, net_days: int) -> int | None:
    if discount_bp >= 10_000 or net_days <= within_days:
        return None

    try:
        with localcontext() as ctx:
            ctx.prec = 50
            discount = Decimal(discount_bp) / Decimal(10_000)
            base = Decimal(1) / (Decimal(1) - discount)
            exponent = Decimal(365) / Decimal(net_days - within_days)
            annualised = (base.ln() * exponent).exp() - Decimal(1)
            bp = annualised * Decimal(10_000)
            return int(bp.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except DecimalException:
        return None


def _discount_minor(amount_minor: int, discount_bp: int) -> int:
    amount = Decimal(amount_minor) * Decimal(discount_bp) / Decimal(10_000)
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _adjusted_path_for(candidate: _Candidate, cash_path: list[int]) -> list[int]:
    adjusted = cash_path.copy()
    payment_now_minor = candidate.bill.amount_minor - candidate.discount_minor
    due_index = candidate.due_week_index

    end_reduction = due_index if due_index is not None else len(adjusted)
    for week_index in range(candidate.early_week_index, end_reduction):
        adjusted[week_index] -= payment_now_minor

    if due_index is not None:
        for week_index in range(due_index, len(adjusted)):
            adjusted[week_index] += candidate.discount_minor

    return adjusted


def _figures(
    *,
    annualised_return_bp: int,
    discount_minor: int,
    low_closing_minor: int,
    currency: str,
):
    return [
        bp_figure(
            "payments.annualised_discount_return",
            "Discount as an annual return",
            Decimal(annualised_return_bp) / Decimal(10_000),
            formula=DISCOUNT_FORMULA,
        ),
        money_figure(
            "payments.saving_if_early",
            "Saving if paid early",
            discount_minor,
            currency,
        ),
        money_figure(
            "payments.closing_if_paid_early",
            "Lowest forecast cash if paid early",
            low_closing_minor,
            currency,
        ),
    ]


def _rule_checks(
    *,
    annualised_return_bp: int,
    cost_of_money_annual_bp: int,
    low_closing_minor: int,
    buffer_minor: int,
    currency: str,
    worth_it: bool,
    cash_safe: bool,
) -> list[RuleCheck]:
    return [
        RuleCheck(
            rule_id="PT-01",
            description="The discount earns more than the cost of money",
            metric_id="payments.annualised_discount_return",
            threshold=bp_threshold(
                "cost_of_money",
                Decimal(cost_of_money_annual_bp) / Decimal(10_000),
                Origin.RULEBOOK,
                ">",
                worth_it,
            ),
            passed=worth_it,
        ),
        RuleCheck(
            rule_id="PT-02",
            description="Paying early keeps cash above the buffer in every affected week",
            metric_id="payments.closing_if_paid_early",
            threshold=money_threshold(
                "cash_buffer",
                buffer_minor,
                currency,
                Origin.TENANT_POLICY,
                ">=",
                cash_safe,
            ),
            passed=cash_safe,
        ),
    ]


def _cannot_pay_on_due(
    bill: OpenBill, due_week_index: int | None, weeks: list[WeekBalance], currency: str
) -> BillTiming:
    return _bill_timing(
        bill,
        "cannot_pay_on_due",
        bill.due_date,
        currency,
        rule_checks=[_baseline_due_week_rule(due_week_index, weeks, currency)],
    )


def _baseline_due_week_rule(
    due_week_index: int | None, weeks: list[WeekBalance], currency: str
) -> RuleCheck:
    due_week_label = (
        f"week {weeks[due_week_index].week}" if due_week_index is not None else "the due-date week"
    )
    return RuleCheck(
        rule_id="PT-02",
        description=f"Baseline cash is below zero in {due_week_label}",
        metric_id="payments.closing_if_paid_early",
        threshold=money_threshold(
            "cash_floor",
            0,
            currency,
            Origin.TENANT_POLICY,
            ">=",
            False,
        ),
        passed=False,
    )


def _bill_timing(
    bill: OpenBill,
    action: str,
    pay_on: date,
    currency: str,
    *,
    figures=None,
    rule_checks=None,
) -> BillTiming:
    return BillTiming(
        bill_id=bill.bill_id,
        supplier_id=bill.supplier_id,
        supplier_name=bill.supplier_name,
        amount=Money(minor=bill.amount_minor, currency=currency),
        issue_date=bill.issue_date,
        due_date=bill.due_date,
        terms=bill.terms,
        action=action,
        pay_on=pay_on,
        figures=figures or [],
        rule_checks=rule_checks or [],
    )


def _week_index_for(day: date, weeks: list[WeekBalance]) -> int | None:
    return next((index for index, week in enumerate(weeks) if week.start <= day <= week.end), None)


def _baseline_due_week_below_zero(due_week_index: int | None, weeks: list[WeekBalance]) -> bool:
    return due_week_index is not None and weeks[due_week_index].closing_minor < 0
