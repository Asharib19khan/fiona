"""Monthly demand profile for a product that has no sales history of its own.

demand[k] = level x season[calendar month] x ramp[k] x (1 + growth)^(k/12) x (price / ref_price)^elasticity

`level` is the average monthly demand at maturity, at `ref_price`. Each factor is a separate,
labelled input so the user can see why the forecast has the shape it has. This is an
assumption-based model, not a forecast trained on the product's own history, and results
say so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np


def add_months(start: date, months: int) -> date:
    index = start.year * 12 + (start.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def calendar_month(launch_month: date, k: int) -> int:
    """Calendar month (1..12) of horizon month k, where k = 1 is the launch month."""
    return add_months(launch_month, k - 1).month


def normalise_season(index: Mapping[int, float]) -> dict[int, float]:
    """Scale a 12-month seasonal index so its mean is exactly 1."""
    if set(index) != set(range(1, 13)):
        raise ValueError("seasonal index needs a value for each calendar month 1..12")
    values = np.array([index[m] for m in range(1, 13)], dtype=float)
    if (values < 0).any() or values.sum() <= 0:
        raise ValueError("seasonal index values must be non-negative and not all zero")
    values = values / values.mean()
    return {m: float(values[m - 1]) for m in range(1, 13)}


FLAT_SEASON: dict[int, float] = {m: 1.0 for m in range(1, 13)}


@dataclass(frozen=True)
class DemandProfile:
    level: float  # mature average monthly units at ref_price
    ref_price: float  # list price the level was estimated at
    launch_month: date
    horizon_months: int
    season: Mapping[int, float] = field(default_factory=lambda: dict(FLAT_SEASON))
    ramp: Sequence[float] = (1.0,)
    annual_growth: float = 0.0

    def __post_init__(self) -> None:
        if self.level < 0:
            raise ValueError("demand level cannot be negative")
        if self.ref_price <= 0:
            raise ValueError("reference price must be positive")
        if not 1 <= self.horizon_months <= 60:
            raise ValueError("horizon must be 1 to 60 months")
        if any(r < 0 for r in self.ramp):
            raise ValueError("ramp factors cannot be negative")
        if self.annual_growth <= -1:
            raise ValueError("annual growth must be above -100%")

    def ramp_factor(self, k: int) -> float:
        return self.ramp[k - 1] if k <= len(self.ramp) else self.ramp[-1] if self.ramp else 1.0

    def monthly(self, price: float | None = None, elasticity: float = 0.0) -> np.ndarray:
        """Expected units for months 1..horizon at `price` (defaults to the reference price)."""
        price_factor = 1.0 if price is None else (price / self.ref_price) ** elasticity
        out = np.empty(self.horizon_months)
        for k in range(1, self.horizon_months + 1):
            growth = (1.0 + self.annual_growth) ** (k / 12.0)
            out[k - 1] = (
                self.level
                * self.season[calendar_month(self.launch_month, k)]
                * self.ramp_factor(k)
                * growth
            )
        return out * price_factor

    def month_labels(self) -> list[str]:
        return [
            add_months(self.launch_month, k).strftime("%Y-%m") for k in range(self.horizon_months)
        ]


def seasonal_index_from_history(
    monthly_units: Mapping[date, float], min_months: int = 12
) -> dict[int, float] | None:
    """Average share of demand by calendar month, from at least a full year of history.

    Each calendar month's mean is divided by the overall mean. Returns None with less than
    `min_months` of history or if any calendar month is missing, rather than guessing.
    """
    if len(monthly_units) < min_months:
        return None
    by_month: dict[int, list[float]] = {}
    for month, units in monthly_units.items():
        by_month.setdefault(month.month, []).append(float(units))
    if set(by_month) != set(range(1, 13)):
        return None
    means = {m: float(np.mean(v)) for m, v in by_month.items()}
    if sum(means.values()) <= 0:
        return None
    return normalise_season(means)
