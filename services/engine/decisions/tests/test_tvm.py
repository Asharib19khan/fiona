import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.decisions.tvm import IrrStatus, annual_rate, irr, monthly_rate, npv, payback_period


def test_npv_matches_hand_calculation():
    # -1000 + 600/1.1 + 600/1.21 = 41.3223...
    assert npv(0.10, [-1000, 600, 600]) == pytest.approx(41.32231405, abs=1e-8)


def test_npv_at_zero_rate_is_the_plain_sum():
    assert npv(0.0, [-50, 20, 20, 20]) == pytest.approx(10.0)


def test_npv_rejects_rate_at_or_below_minus_100_percent():
    with pytest.raises(ValueError):
        npv(-1.0, [1, 2])


def test_irr_single_period():
    result = irr([-100, 110])
    assert result.status is IrrStatus.OK
    assert result.rate == pytest.approx(0.10, abs=1e-9)


def test_irr_two_periods_matches_closed_form():
    # 60x^2 + 50x - 100 = 0 with x = 1/(1+r)
    x = (-50 + math.sqrt(50**2 + 4 * 60 * 100)) / 120
    result = irr([-100, 50, 60])
    assert result.rate == pytest.approx(1 / x - 1, abs=1e-9)


def test_irr_refuses_when_flows_never_change_sign():
    assert irr([100, 50]).status is IrrStatus.NO_SIGN_CHANGE
    assert irr([-100, -50]).rate is None


def test_irr_refuses_multiple_sign_changes():
    # Classic mine problem: two IRRs (25% and 400%); we do not pick one.
    result = irr([-1600, 10000, -10000])
    assert result.status is IrrStatus.MULTIPLE_SIGN_CHANGES
    assert not result.valid


def test_irr_handles_loss_making_projects():
    result = irr([-100, 30, 30])
    assert result.valid and result.rate < 0
    assert npv(result.rate, [-100, 30, 30]) == pytest.approx(0.0, abs=1e-6)


@given(
    outlay=st.floats(min_value=1, max_value=1e9),
    inflows=st.lists(st.floats(min_value=0, max_value=1e9), min_size=1, max_size=24),
)
def test_irr_zeroes_npv_for_conventional_flows(outlay, inflows):
    flows = [-outlay, *inflows]
    result = irr(flows)
    if sum(inflows) == 0:
        assert result.status is IrrStatus.NO_SIGN_CHANGE
        return
    if result.valid:
        scale = outlay + sum(inflows)
        assert abs(npv(result.rate, flows)) <= 1e-6 * scale


def test_payback_interpolates_inside_the_crossing_period():
    # cumulative: -100, -70, -30, +20 -> 2 + 30/50
    assert payback_period([-100, 30, 40, 50]) == pytest.approx(2.6)


def test_payback_none_when_never_recovered():
    assert payback_period([-100, 10, 10]) is None


def test_discounted_payback_is_later_than_simple():
    flows = [-100, 30, 40, 50, 60]
    assert payback_period(flows, rate=0.10) > payback_period(flows)


def test_monthly_and_annual_rates_round_trip():
    assert annual_rate(monthly_rate(0.15)) == pytest.approx(0.15)
    assert monthly_rate(0.12682503) == pytest.approx(0.01, abs=1e-8)


def test_irr_survives_long_schedules():
    """120 monthly payments: the bracket near -100% must not underflow."""
    flows = [-1_000_000.0] + [12_000.0] * 120
    result = irr(flows)
    assert result.valid
    assert abs(npv(result.rate, flows)) <= 1e-8 * sum(abs(f) for f in flows)
