from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from engine.decisions.debt_equity import _schedule, _service_12m, compare_debt_equity
from engine.decisions.schemas import DebtEquityRequest
from engine.forecast.ledger_source import load_fixture_snapshot


def request(
    *,
    amount_minor: int = 20_000_000,
    annual_rate_bp: int = 1_900,
    term_months: int = 24,
    grace_months: int = 0,
    repayment: str = "annuity",
    include_debt: bool = True,
    include_equity: bool = False,
) -> DebtEquityRequest:
    payload = {
        "amount": {"minor": amount_minor, "currency": "PKR"},
        "purpose": "working_capital_seasonal",
    }
    if include_debt:
        payload["debt"] = {
            "annual_rate_bp": annual_rate_bp,
            "term_months": term_months,
            "grace_months": grace_months,
            "repayment": repayment,
        }
    if include_equity:
        payload["equity"] = {"pre_money_valuation": {"minor": amount_minor * 9, "currency": "PKR"}}
    return DebtEquityRequest.model_validate(payload)


def test_annuity_schedule_reconciles_principal_and_reduces_balance():
    body = request(amount_minor=1_000_000, annual_rate_bp=1_200, term_months=12)

    schedule = _schedule(body.amount.minor, body)

    assert len(schedule) == 12
    assert sum(principal for _, _, _, principal in schedule) == body.amount.minor
    assert all(payment == interest + principal for _, payment, interest, principal in schedule)
    assert all(principal >= 0 and interest >= 0 for _, _, interest, principal in schedule)
    assert schedule[-1][3] > 0


def test_bullet_loan_has_interest_only_service_in_first_year():
    body = request(
        amount_minor=1_200_000,
        annual_rate_bp=1_200,
        term_months=24,
        repayment="bullet",
    )

    schedule = _schedule(body.amount.minor, body)

    assert all(principal == 0 for _, _, _, principal in schedule[:12])
    assert schedule[-1][3] == body.amount.minor
    assert _service_12m(body.amount.minor, body) == sum(
        payment for _, payment, _, _ in schedule[:12]
    )


def test_missing_terms_are_reported_without_guessing_a_loan_or_valuation():
    result = compare_debt_equity(
        request(include_debt=False),
        load_fixture_snapshot("ten_karachi_apparel"),
        mode="mock",
        generated_at=datetime(2026, 10, 16, tzinfo=UTC),
    )

    debt = next(option for option in result.options if option.option_id == "A_debt")
    equity = next(option for option in result.options if option.option_id == "B_equity")
    assert debt.eligible is None
    assert debt.rule_checks[0].rule_id == "DE-00"
    assert equity.eligible is None
    assert {gap.need for gap in result.insufficient_data} == {
        "Indicative debt terms",
        "Investor valuation or proposed stake",
    }


def test_result_is_deterministic_and_keeps_money_as_integers():
    body = request(include_equity=True)
    snapshot = load_fixture_snapshot("ten_karachi_apparel")
    generated_at = datetime(2026, 10, 16, tzinfo=UTC)

    first = compare_debt_equity(body, snapshot, mode="mock", generated_at=generated_at)
    second = compare_debt_equity(body, snapshot, mode="mock", generated_at=generated_at)

    assert first == second
    debt = next(option for option in first.options if option.option_id == "A_debt")
    assert debt.amortisation is not None
    assert sum(row.principal.minor for row in debt.amortisation) == body.amount.minor
    assert all(
        isinstance(figure.money.minor, int)
        for option in first.options
        for figure in option.figures
        if figure.money is not None
    )


@st.composite
def debt_cases(draw):
    repayment = draw(st.sampled_from(["annuity", "equal_principal", "bullet"]))
    term_months = draw(st.integers(min_value=1, max_value=60))
    grace_months = 0 if repayment == "bullet" else draw(st.integers(0, term_months - 1))
    return request(
        amount_minor=draw(st.integers(min_value=1, max_value=1_000_000_000)),
        annual_rate_bp=draw(st.integers(min_value=0, max_value=20_000)),
        term_months=term_months,
        grace_months=grace_months,
        repayment=repayment,
    )


@given(debt_cases())
def test_property_schedule_is_non_negative_and_reconciles_exactly(body):
    schedule = _schedule(body.amount.minor, body)

    assert len(schedule) == body.debt.term_months
    assert sum(principal for _, _, _, principal in schedule) == body.amount.minor
    assert all(payment == interest + principal for _, payment, interest, principal in schedule)
    assert all(
        payment >= 0 and interest >= 0 and principal >= 0
        for _, payment, interest, principal in schedule
    )
    assert 0 <= _service_12m(body.amount.minor, body) <= sum(row[1] for row in schedule)
