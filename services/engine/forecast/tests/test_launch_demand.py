from datetime import date

import numpy as np
import pytest

from engine.forecast.launch_lab.demand import (
    DemandProfile,
    add_months,
    calendar_month,
    normalise_season,
    seasonal_index_from_history,
)


def test_add_months_crosses_year_end():
    assert add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert calendar_month(date(2026, 11, 1), 3) == 1


def test_normalise_season_has_mean_one():
    season = normalise_season({m: float(m) for m in range(1, 13)})
    assert np.mean(list(season.values())) == pytest.approx(1.0)


def test_normalise_season_rejects_missing_months():
    with pytest.raises(ValueError):
        normalise_season({1: 1.0})


def test_profile_applies_season_ramp_and_price():
    season = normalise_season({m: (3.0 if m in (11, 12, 1) else 1.0) for m in range(1, 13)})
    profile = DemandProfile(
        level=100,
        ref_price=1000,
        launch_month=date(2026, 11, 1),
        horizon_months=4,
        season=season,
        ramp=(0.5, 1.0),
    )
    base = profile.monthly()
    assert base[0] == pytest.approx(100 * season[11] * 0.5)
    assert base[2] == pytest.approx(100 * season[1])
    assert base[3] == pytest.approx(100 * season[2])
    dearer = profile.monthly(price=1100, elasticity=-1.2)
    np.testing.assert_allclose(dearer, base * 1.1**-1.2)
    assert profile.month_labels() == ["2026-11", "2026-12", "2027-01", "2027-02"]


def test_growth_compounds_monthly():
    profile = DemandProfile(
        level=100, ref_price=1, launch_month=date(2026, 1, 1), horizon_months=12, annual_growth=0.12
    )
    assert profile.monthly()[-1] == pytest.approx(100 * 1.12)


def test_seasonal_index_needs_a_full_year():
    history = {add_months(date(2025, 1, 1), i): 10.0 for i in range(11)}
    assert seasonal_index_from_history(history) is None
    history[date(2025, 12, 1)] = 30.0
    index = seasonal_index_from_history(history)
    assert index[12] == pytest.approx(30.0 / np.mean([10.0] * 11 + [30.0]))


@pytest.mark.parametrize(
    "kwargs", [{"level": -1}, {"ref_price": 0}, {"horizon_months": 0}, {"annual_growth": -1}]
)
def test_invalid_profiles_are_rejected(kwargs):
    base = {"level": 1, "ref_price": 1, "launch_month": date(2026, 1, 1), "horizon_months": 3}
    with pytest.raises(ValueError):
        DemandProfile(**{**base, **kwargs})
