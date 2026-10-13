import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.forecast.launch_lab.economics import Economics
from engine.forecast.launch_lab.simulate import (
    OrderPlan,
    Shocks,
    initial_order_quantity,
    lead_months_from_days,
    sample_shocks,
    simulate,
)

SIMPLE = Economics(price=1000, unit_cost=600, launch_costs=10000, unsold_recovery_rate=0.5)
FLAT = np.array([100.0, 100.0, 100.0])


def _run(econ=SIMPLE, initial=300, reorder=False, planned=FLAT, lead=0, **kw):
    plan = OrderPlan(initial_order=initial, lead_months=lead, reorder=reorder, safety_z=0.0, **kw)
    return simulate(econ, plan, planned, Shocks.neutral(len(planned)))


def test_hand_calculated_launch():
    r = _run()
    assert r.sold[0].tolist() == [100, 100, 100]
    assert r.profit[0] == pytest.approx(3 * 100 * 400 - 10000)
    assert r.cash_flow[0, 0] == pytest.approx(-10000 - 300 * 600)
    assert r.peak_cash[0] == pytest.approx(190000)
    # cumulative cash: -190000, -90000, +10000 -> recovered from month 2
    assert r.payback_month[0] == 2


def test_stockout_records_lost_sales():
    r = _run(initial=150)
    assert r.sold[0].tolist() == [100, 50, 0]
    assert r.lost[0].tolist() == [0, 50, 100]


def test_leftover_stock_is_written_down_to_recovery_rate():
    r = _run(initial=400)
    assert r.ending_units[0] == pytest.approx(100)
    assert r.writedown[0] == pytest.approx(100 * 600 * 0.5)
    assert r.profit[0] == pytest.approx(120000 - 10000 - 30000)


def test_late_customer_payment_delays_cash_not_profit():
    on_time = _run()
    late = _run(econ=SIMPLE.with_changes(receivable_days=45))
    assert late.profit[0] == pytest.approx(on_time.profit[0])
    assert late.cash_flow.sum() == pytest.approx(on_time.cash_flow.sum())
    assert late.payback_month[0] > on_time.payback_month[0]
    assert late.cumulative_cash[0, 1] < on_time.cumulative_cash[0, 1]


def test_reorders_keep_flat_demand_in_stock_with_no_leftover():
    planned = np.full(6, 100.0)
    initial = initial_order_quantity(planned, lead_months=1, wastage_rate=0.0, moq=1)
    assert initial == 200
    r = _run(initial=initial, reorder=True, planned=planned, lead=1)
    assert r.lost.sum() == pytest.approx(0)
    assert r.ending_units[0] == pytest.approx(0)
    assert r.purchases[0].sum() == pytest.approx(600)


def test_moq_forces_bigger_orders():
    planned = np.full(6, 100.0)
    r = _run(initial=200, reorder=True, planned=planned, lead=1, moq=250)
    assert all(q == 0 or q >= 250 for q in r.purchases[0, 1:])


def test_storage_capacity_is_never_exceeded_by_reorders():
    planned = np.full(8, 100.0)
    r = _run(initial=100, reorder=True, planned=planned, lead=2, storage_capacity=150)
    assert r.stock_end.max() <= 150 + 1e-9


def test_delivery_delay_loses_the_first_months():
    r = _run(first_arrival_month=2)
    assert r.sold[0, 0] == 0 and r.lost[0, 0] == pytest.approx(100)


def test_unsellable_share_strands_stock():
    r = _run(econ=SIMPLE.with_changes(unsellable_share=0.15), initial=300)
    assert r.ending_units[0] == pytest.approx(45)


def test_lead_time_rounding():
    assert [lead_months_from_days(d) for d in (0, 14, 15, 30, 44, 45, 60)] == [0, 0, 1, 1, 1, 2, 2]


def test_monte_carlo_is_reproducible_and_centred():
    kwargs = dict(
        runs=4000,
        horizon=6,
        demand_sigma=0.35,
        noise_sigma=0.15,
        cost_triangular=(-0.05, 0.0, 0.10),
        max_extra_discount=0.1,
        return_spread=0.5,
    )
    a = sample_shocks(seed=7, **kwargs)
    b = sample_shocks(seed=7, **kwargs)
    np.testing.assert_array_equal(a.demand_multiplier, b.demand_multiplier)
    assert np.median(a.demand_multiplier) == pytest.approx(1.0, abs=0.03)
    assert a.monthly_noise.mean() == pytest.approx(1.0, abs=0.01)
    assert (a.cost_multiplier >= 0.95 - 1e-12).all() and (a.cost_multiplier <= 1.10 + 1e-12).all()


def test_monte_carlo_runs_vectorised():
    planned = np.full(12, 80.0)
    shocks = sample_shocks(
        runs=2000,
        horizon=12,
        seed=1,
        demand_sigma=0.4,
        noise_sigma=0.15,
        cost_triangular=(-0.05, 0.0, 0.1),
        max_extra_discount=0.1,
        return_spread=0.5,
    )
    plan = OrderPlan(initial_order=200, lead_months=1)
    r = simulate(SIMPLE, plan, planned, shocks)
    assert r.profit.shape == (2000,)
    assert r.profit.std() > 0


economics = st.builds(
    Economics,
    price=st.floats(1, 1e6),
    unit_cost=st.floats(0, 1e6),
    discount_rate=st.floats(0, 0.5),
    duty_rate=st.floats(0, 0.5),
    freight_per_unit=st.floats(0, 1e4),
    wastage_rate=st.floats(0, 0.3),
    return_rate=st.floats(0, 0.5),
    return_loss_rate=st.floats(0, 1),
    payment_fee_rate=st.floats(0, 0.1),
    storage_per_unit_month=st.floats(0, 100),
    launch_costs=st.floats(0, 1e7),
    monthly_fixed=st.floats(0, 1e6),
    receivable_days=st.floats(0, 90),
    payable_days=st.floats(0, 90),
    unsold_recovery_rate=st.floats(0, 1),
    unsellable_share=st.floats(0, 0.3),
)


@settings(max_examples=150, deadline=None)
@given(
    econ=economics,
    planned=st.lists(st.floats(0, 5000), min_size=1, max_size=18),
    initial=st.integers(0, 20000),
    lead=st.integers(0, 3),
    moq=st.integers(1, 500),
    demand=st.floats(0.2, 3.0),
)
def test_cash_settles_to_profit(econ, planned, initial, lead, moq, demand):
    """Once every receivable and payable settles, total cash equals accrual profit."""
    planned = np.array(planned)
    plan = OrderPlan(initial_order=initial, lead_months=lead, moq=moq)
    r = simulate(econ, plan, planned, Shocks.fixed(len(planned), demand=demand))
    scale = 1.0 + abs(r.cash_flow).sum()
    assert abs(r.cash_flow.sum() - r.profit[0]) <= 1e-9 * scale
    assert (r.sold <= r.demand + 1e-9).all()
    assert r.peak_cash[0] >= 0


def test_no_moq_reorder_into_the_off_season():
    """A big MOQ arriving after the peak would mostly be written off, so the planner skips it."""
    econ = Economics(price=4500, unit_cost=2400, unsold_recovery_rate=0.4)
    planned = np.array([60.0, 110.0, 130.0, 70.0, 15.0, 4.0])
    plan = OrderPlan(initial_order=330, lead_months=2, moq=300, safety_z=0.0)
    r = simulate(econ, plan, planned, Shocks.fixed(6, demand=1.6))
    assert r.purchases[0, 1:].sum() == 0


def test_reorders_size_to_demand_after_arrival():
    """An order can only serve months from its arrival, so it is not sized for earlier ones."""
    planned = np.array([100.0, 100.0, 100.0, 0.0, 0.0, 0.0])
    plan = OrderPlan(initial_order=100, lead_months=1, safety_z=0.0)
    r = simulate(SIMPLE, plan, planned, Shocks.neutral(6))
    assert r.purchases[0, 1] == pytest.approx(100)  # covers month 3 only
    assert r.ending_units[0] == pytest.approx(0)
