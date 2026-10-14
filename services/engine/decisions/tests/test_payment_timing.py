from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from hypothesis import given
from hypothesis import strategies as st

from engine.decisions.payment_timing import OpenBill, WeekBalance, optimise_payment_timing
from engine.decisions.schemas import EarlyPaymentTerms

CURRENCY = "PKR"
AS_OF = date(2026, 10, 14)


def terms(discount_bp: int, within_days: int, net_days: int) -> EarlyPaymentTerms:
    return EarlyPaymentTerms(
        discount_bp=discount_bp,
        within_days=within_days,
        net_days=net_days,
        origin="bill_text",
    )


def bill(
    bill_id: str = "bill_1",
    amount_minor: int = 100_000,
    issue_date: date = date(2026, 10, 15),
    due_date: date = date(2026, 11, 14),
    bill_terms: EarlyPaymentTerms | None = None,
) -> OpenBill:
    return OpenBill(
        bill_id=bill_id,
        supplier_id=f"sup_{bill_id}",
        supplier_name=f"Supplier {bill_id}",
        amount_minor=amount_minor,
        issue_date=issue_date,
        due_date=due_date,
        terms=bill_terms,
    )


def weeks(start: date = date(2026, 10, 15), closings: list[int] | None = None) -> list[WeekBalance]:
    closings = closings or [1_000_000] * 13
    return [
        WeekBalance(
            week=index + 1,
            start=start + timedelta(days=7 * index),
            end=start + timedelta(days=7 * index + 6),
            closing_minor=closing,
        )
        for index, closing in enumerate(closings)
    ]


def figure_value(result, metric_id: str) -> int:
    return next(figure.value for figure in result.figures if figure.metric_id == metric_id)


def figure_money(result, metric_id: str) -> int:
    return next(figure.money.minor for figure in result.figures if figure.metric_id == metric_id)


def check(result, rule_id: str):
    return next(rule_check for rule_check in result.rule_checks if rule_check.rule_id == rule_id)


def expected_annualised_bp(discount_bp: int, within_days: int, net_days: int) -> int:
    with localcontext() as ctx:
        ctx.prec = 50
        discount = Decimal(discount_bp) / Decimal(10_000)
        base = Decimal(1) / (Decimal(1) - discount)
        exponent = Decimal(365) / Decimal(net_days - within_days)
        annualised = (base.ln() * exponent).exp() - Decimal(1)
        return int((annualised * Decimal(10_000)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def test_annualised_discount_uses_compounded_formula():
    result_2_10 = optimise_payment_timing(
        [bill(bill_terms=terms(200, 10, 30))],
        weeks(),
        buffer_minor=0,
        cost_of_money_annual_bp=0,
        as_of=AS_OF,
        currency=CURRENCY,
    )[0]
    assert figure_value(result_2_10, "payments.annualised_discount_return") == 4459

    result_1_10 = optimise_payment_timing(
        [bill(bill_terms=terms(100, 10, 45), due_date=date(2026, 11, 29))],
        weeks(),
        buffer_minor=0,
        cost_of_money_annual_bp=0,
        as_of=AS_OF,
        currency=CURRENCY,
    )[0]
    assert figure_value(
        result_1_10, "payments.annualised_discount_return"
    ) == expected_annualised_bp(100, 10, 45)


def test_worthwhile_discount_with_ample_cash_is_paid_early():
    result = optimise_payment_timing(
        [bill(amount_minor=123_451, bill_terms=terms(250, 10, 30))],
        weeks(closings=[1_000_000] * 13),
        buffer_minor=100_000,
        cost_of_money_annual_bp=1_000,
        as_of=AS_OF,
        currency=CURRENCY,
    )[0]

    assert result.action == "pay_early"
    assert result.pay_on == date(2026, 10, 25)
    assert figure_money(result, "payments.saving_if_early") == 3_086
    assert check(result, "PT-01").passed is True
    assert check(result, "PT-02").passed is True


def test_worthwhile_discount_that_breaches_buffer_is_paid_on_due():
    result = optimise_payment_timing(
        [bill(amount_minor=900_000, bill_terms=terms(200, 10, 30))],
        weeks(closings=[1_000_000] * 13),
        buffer_minor=200_000,
        cost_of_money_annual_bp=1_000,
        as_of=AS_OF,
        currency=CURRENCY,
    )[0]

    assert result.action == "pay_on_due"
    assert check(result, "PT-01").passed is True
    assert check(result, "PT-02").passed is False


def test_discount_below_cost_of_money_is_paid_on_due():
    result = optimise_payment_timing(
        [bill(bill_terms=terms(100, 10, 45), due_date=date(2026, 11, 29))],
        weeks(),
        buffer_minor=0,
        cost_of_money_annual_bp=2_000,
        as_of=AS_OF,
        currency=CURRENCY,
    )[0]

    assert result.action == "pay_on_due"
    assert check(result, "PT-01").passed is False


def test_two_bills_that_fit_alone_do_not_jointly_breach_buffer():
    first = bill(
        "bill_a",
        amount_minor=600_000,
        issue_date=date(2026, 10, 15),
        due_date=date(2026, 11, 14),
        bill_terms=terms(300, 10, 30),
    )
    second = bill(
        "bill_b",
        amount_minor=600_000,
        issue_date=date(2026, 10, 15),
        due_date=date(2026, 11, 14),
        bill_terms=terms(200, 10, 30),
    )

    results = optimise_payment_timing(
        [second, first],
        weeks(closings=[1_000_000] * 13),
        buffer_minor=200_000,
        cost_of_money_annual_bp=1_000,
        as_of=AS_OF,
        currency=CURRENCY,
    )

    by_id = {result.bill_id: result for result in results}
    assert [result.bill_id for result in results] == ["bill_b", "bill_a"]
    assert by_id["bill_a"].action == "pay_early"
    assert by_id["bill_b"].action == "pay_on_due"
    assert check(by_id["bill_b"], "PT-02").passed is False


def test_passed_window_or_no_terms_are_paid_on_due():
    already_passed = bill(
        "bill_old",
        issue_date=date(2026, 9, 1),
        due_date=date(2026, 10, 31),
        bill_terms=terms(200, 10, 30),
    )
    no_terms = bill("bill_none", bill_terms=None)

    results = optimise_payment_timing(
        [already_passed, no_terms],
        weeks(),
        buffer_minor=0,
        cost_of_money_annual_bp=0,
        as_of=AS_OF,
        currency=CURRENCY,
    )

    assert [result.action for result in results] == ["pay_on_due", "pay_on_due"]
    assert all(
        result.pay_on == source.due_date
        for result, source in zip(results, [already_passed, no_terms], strict=True)
    )


def test_baseline_due_week_below_zero_cannot_pay_on_due():
    result = optimise_payment_timing(
        [bill(due_date=date(2026, 10, 20))],
        weeks(closings=[-1, 1_000_000, 1_000_000]),
        buffer_minor=0,
        cost_of_money_annual_bp=0,
        as_of=AS_OF,
        currency=CURRENCY,
    )[0]

    assert result.action == "cannot_pay_on_due"
    assert result.pay_on == date(2026, 10, 20)
    assert result.rule_checks[0].passed is False


@st.composite
def random_case(draw):
    start = date(2026, 10, 15)
    week_count = draw(st.integers(min_value=3, max_value=13))
    buffer_minor = draw(st.integers(min_value=0, max_value=20_000))
    closings = draw(
        st.lists(
            st.integers(min_value=buffer_minor + 50_000, max_value=300_000),
            min_size=week_count,
            max_size=week_count,
        )
    )
    source_weeks = weeks(start, closings)
    bill_count = draw(st.integers(min_value=0, max_value=5))
    source_bills = []
    for index in range(bill_count):
        issue_offset = draw(st.integers(min_value=0, max_value=10))
        within_days = draw(st.integers(min_value=1, max_value=12))
        max_due_offset = 7 * week_count + 20
        net_days = draw(st.integers(min_value=within_days + 1, max_value=max_due_offset))
        due_offset = draw(st.integers(min_value=net_days, max_value=max_due_offset))
        source_bills.append(
            bill(
                f"bill_{index}",
                amount_minor=draw(st.integers(min_value=1_000, max_value=80_000)),
                issue_date=start + timedelta(days=issue_offset),
                due_date=start + timedelta(days=due_offset),
                bill_terms=terms(
                    draw(st.integers(min_value=1, max_value=500)),
                    within_days,
                    net_days,
                ),
            )
        )
    return source_bills, source_weeks, buffer_minor


@given(random_case())
def test_property_outputs_are_safe_int_money_and_same_length(case):
    source_bills, source_weeks, buffer_minor = case
    results = optimise_payment_timing(
        source_bills,
        source_weeks,
        buffer_minor=buffer_minor,
        cost_of_money_annual_bp=0,
        as_of=AS_OF,
        currency=CURRENCY,
    )

    assert len(results) == len(source_bills)
    assert all(isinstance(result.amount.minor, int) for result in results)
    assert all(
        figure.money is None or isinstance(figure.money.minor, int)
        for result in results
        for figure in result.figures
    )

    adjusted = [week.closing_minor for week in sorted(source_weeks, key=lambda week: week.week)]
    touched_weeks = set()
    for result, source_bill in zip(results, source_bills, strict=True):
        if result.action != "pay_early":
            continue
        early_index = week_index(result.pay_on, source_weeks)
        due_index = week_index(source_bill.due_date, source_weeks)
        discount_minor = figure_money(result, "payments.saving_if_early")
        payment_now = source_bill.amount_minor - discount_minor
        end_reduction = due_index if due_index is not None else len(adjusted)
        for index in range(early_index, end_reduction):
            adjusted[index] -= payment_now
            touched_weeks.add(index)
        if due_index is not None:
            for index in range(due_index, len(adjusted)):
                adjusted[index] += discount_minor
                touched_weeks.add(index)

    assert all(adjusted[index] >= buffer_minor for index in touched_weeks)


def week_index(day: date, source_weeks: list[WeekBalance]) -> int | None:
    ordered_weeks = sorted(source_weeks, key=lambda week: week.week)
    return next(
        (index for index, week in enumerate(ordered_weeks) if week.start <= day <= week.end),
        None,
    )
