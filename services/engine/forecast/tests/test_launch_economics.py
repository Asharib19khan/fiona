import pytest

from engine.forecast.launch_lab.economics import (
    Economics,
    horizon_break_even_units,
    monthly_break_even_units,
    price_for_margin,
    unit_economics,
)


def _shawl() -> Economics:
    return Economics(
        price=5000,
        unit_cost=2000,
        discount_rate=0.10,
        duty_rate=0.10,
        freight_per_unit=100,
        packaging_per_unit=50,
        wastage_rate=0.05,
        return_rate=0.04,
        return_loss_rate=0.5,
        payment_fee_rate=0.02,
        commission_rate=0.03,
        variable_labour_per_unit=30,
        monthly_fixed=20000,
        marketing_monthly=30000,
        launch_costs=100000,
    )


def test_unit_economics_matches_hand_calculation():
    ue = unit_economics(_shawl())
    # net 4500; landed 2000*1.1 + 150 = 2350; per sellable 2350/0.95
    assert ue.net_price == pytest.approx(4500)
    assert ue.landed_cost == pytest.approx(2350)
    landed_s = 2350 / 0.95
    cogs = landed_s * (1 - 0.04 * 0.5)
    revenue = 4500 * 0.96
    assert ue.revenue_per_unit == pytest.approx(revenue)
    assert ue.contribution_per_unit == pytest.approx(revenue - cogs - 4500 * 0.05 - 30)
    assert ue.contribution_margin == pytest.approx(ue.contribution_per_unit / revenue)


def test_cost_lines_add_up_to_variable_cost():
    ue = unit_economics(_shawl())
    assert sum(line.per_unit for line in ue.lines) == pytest.approx(ue.variable_cost_per_unit)


def test_break_even_price_gives_zero_contribution():
    econ = _shawl()
    p = unit_economics(econ).break_even_price
    assert p == pytest.approx(((2350 / 0.95) * 0.98 + 30) / (0.9 * (0.96 - 0.05)))
    assert unit_economics(econ.with_changes(price=p)).contribution_per_unit == pytest.approx(
        0, abs=1e-6
    )


def test_price_for_margin_hits_the_margin():
    econ = _shawl()
    p = price_for_margin(econ, 0.30)
    assert unit_economics(econ.with_changes(price=p)).contribution_margin == pytest.approx(0.30)


def test_no_price_reaches_margin_when_fees_eat_revenue():
    # fees 95% < 96% kept after refunds: break-even exists but is very high; a 10% margin cannot.
    econ = _shawl().with_changes(marketplace_fee_rate=0.90)
    assert price_for_margin(econ, 0.10) is None
    assert unit_economics(econ).break_even_price > 200000
    # fees 97% > 96%: every sale loses money whatever the price.
    assert unit_economics(_shawl().with_changes(marketplace_fee_rate=0.92)).break_even_price is None


def test_break_even_volumes():
    econ = _shawl()
    c = unit_economics(econ).contribution_per_unit
    assert monthly_break_even_units(econ) == pytest.approx(50000 / c)
    assert horizon_break_even_units(econ, 6) == pytest.approx((100000 + 6 * 50000) / c)


def test_break_even_volume_undefined_for_negative_contribution():
    econ = _shawl().with_changes(price=1000)
    assert unit_economics(econ).contribution_per_unit < 0
    assert monthly_break_even_units(econ) is None


@pytest.mark.parametrize(
    "bad",
    [
        {"price": -1},
        {"unit_cost": float("nan")},
        {"return_rate": 1.0},
        {"discount_rate": 1.2},
        {"wastage_rate": 1.0},
        {"payment_fee_rate": 0.6, "marketplace_fee_rate": 0.5},
        {"duty_rate": -0.1},
    ],
)
def test_invalid_inputs_are_rejected(bad):
    with pytest.raises(ValueError):
        Economics(**{"price": 100, "unit_cost": 50, **bad})
