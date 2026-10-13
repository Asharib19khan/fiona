from hypothesis import given
from hypothesis import strategies as st

from engine.analysis.coverage import Status, dscr, dscr_forward, max_principal_at_dscr, ratio_bp


def test_rulebook_example_de_03():
    # finance_rules.yaml DE-03-T1: 710,000,000 / 622,896,000 = 1.13984x -> 11398 bp
    cov = dscr_forward(710_000_000, 261_612_000, 361_284_000)
    assert cov.value_bp == 11398
    assert cov.metric_id == "solvency.dscr_forward"


def test_rounding_is_half_away_from_zero():
    assert ratio_bp(1, 8) == 1250
    assert ratio_bp(1, 20000) == 1  # 0.5 bp rounds up
    assert ratio_bp(-1, 20000) == -1  # and away from zero when negative


def test_no_debt_service_is_not_computable_not_infinite():
    cov = dscr(5_000_000, 0, 0)
    assert cov.status is Status.NOT_COMPUTABLE and cov.value_bp is None


def test_negative_ebitda_gives_negative_coverage():
    assert dscr(-1_000_000, 500_000, 500_000).value_bp == -10000


def test_max_principal_annual_equal_principal_loan():
    # 5-year loan, equal principal, 15.42% interest on the opening balance in year 1
    def service(p: int) -> int:
        return p // 5 + p * 1542 // 10000

    ebitda, existing = 710_000_000, 261_612_000
    p = max_principal_at_dscr(ebitda, existing, 12500, service, 10_000_000_000)
    assert dscr_forward(ebitda, existing, service(p)).value_bp >= 12500
    assert dscr_forward(ebitda, existing, service(p + 1)).value_bp < 12500 or service(p + 1) == service(p)


def test_max_principal_zero_when_existing_debt_already_fails():
    assert max_principal_at_dscr(100, 100, 12500, lambda p: p, 1_000) == 0


@given(st.integers(-10**12, 10**12), st.integers(1, 10**12))
def test_ratio_bp_matches_exact_rounding(n, d):
    from fractions import Fraction

    exact = Fraction(n * 10000, d)
    floor = exact.numerator // exact.denominator
    frac = exact - floor
    expected = floor + (1 if frac >= Fraction(1, 2) else 0) if exact >= 0 else -(
        (-exact).numerator // (-exact).denominator + (1 if (-exact) - (-exact).numerator // (-exact).denominator >= Fraction(1, 2) else 0)
    )
    assert ratio_bp(n, d) == expected
