"""Per-unit economics of a proposed product, with the formula behind every line.

All amounts are floats in minor units of one currency; rates are fractions (0.03 = 3%).
Demand is counted in gross units shipped; returned units are refunded, and a share of them
cannot be resold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Economics:
    price: float  # list price per unit
    unit_cost: float  # purchase or manufacturing cost per unit
    discount_rate: float = 0.0  # average discount off list price
    imported_cost_share: float = 0.0  # share of unit cost exposed to the exchange rate
    duty_rate: float = 0.0  # customs duty, as a share of unit cost
    non_recoverable_tax_rate: float = 0.0  # input tax that cannot be reclaimed, share of unit cost
    freight_per_unit: float = 0.0
    packaging_per_unit: float = 0.0
    variable_labour_per_unit: float = 0.0
    other_variable_per_unit: float = 0.0
    payment_fee_rate: float = 0.0  # share of net price
    marketplace_fee_rate: float = 0.0  # share of net price
    commission_rate: float = 0.0  # share of net price
    return_rate: float = 0.0  # share of shipped units returned for a refund
    return_loss_rate: float = 0.0  # share of returned units that cannot be resold
    wastage_rate: float = 0.0  # share of purchased units lost or damaged before sale
    storage_per_unit_month: float = 0.0
    launch_costs: float = 0.0  # one-off, paid before launch
    monthly_fixed: float = 0.0  # incremental fixed cost per month
    marketing_monthly: float = 0.0
    overhead_rate: float = 0.0  # shared overhead allocated as a share of net revenue
    receivable_days: float = 0.0  # days customers take to pay
    payable_days: float = 0.0  # days before the supplier is paid
    unsold_recovery_rate: float = 0.5  # share of cost recovered for stock left at the horizon
    unsellable_share: float = 0.0  # what-if only: share of received stock that never sells

    def __post_init__(self) -> None:
        money_fields = (
            "price",
            "unit_cost",
            "freight_per_unit",
            "packaging_per_unit",
            "variable_labour_per_unit",
            "other_variable_per_unit",
            "storage_per_unit_month",
            "launch_costs",
            "monthly_fixed",
            "marketing_monthly",
            "receivable_days",
            "payable_days",
        )
        for name in money_fields:
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite, non-negative number, got {value!r}")
        rate_fields = (
            "discount_rate",
            "imported_cost_share",
            "return_rate",
            "return_loss_rate",
            "wastage_rate",
            "overhead_rate",
            "unsold_recovery_rate",
            "unsellable_share",
            "payment_fee_rate",
            "marketplace_fee_rate",
            "commission_rate",
        )
        for name in rate_fields:
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {value!r}")
        for name in ("duty_rate", "non_recoverable_tax_rate"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.wastage_rate >= 1.0 or self.discount_rate >= 1.0 or self.return_rate >= 1.0:
            raise ValueError("wastage, discount and return rates must be below 100%")
        if self.fee_rate >= 1.0:
            raise ValueError(
                "payment, marketplace and commission rates together must be below 100%"
            )

    @property
    def fee_rate(self) -> float:
        return self.payment_fee_rate + self.marketplace_fee_rate + self.commission_rate

    @property
    def net_price(self) -> float:
        return self.price * (1.0 - self.discount_rate)

    def landed_cost(self, cost_multiplier: float = 1.0, fx_multiplier: float = 1.0) -> float:
        """Cost of one purchased unit delivered to the shelf."""
        purchase = (
            self.unit_cost
            * cost_multiplier
            * (1.0 + self.imported_cost_share * (fx_multiplier - 1.0))
        )
        return (
            purchase * (1.0 + self.duty_rate + self.non_recoverable_tax_rate)
            + self.freight_per_unit
            + self.packaging_per_unit
        )

    def landed_cost_per_sellable(
        self, cost_multiplier: float = 1.0, fx_multiplier: float = 1.0
    ) -> float:
        """Landed cost spread over the units that survive wastage."""
        return self.landed_cost(cost_multiplier, fx_multiplier) / (1.0 - self.wastage_rate)

    def with_changes(self, **changes: float) -> Economics:
        return replace(self, **changes)


@dataclass(frozen=True)
class CostLine:
    name: str
    per_unit: float
    formula: str


@dataclass(frozen=True)
class UnitEconomics:
    list_price: float
    net_price: float
    revenue_per_unit: float  # net of discounts and refunds, per unit shipped
    landed_cost: float
    landed_cost_per_sellable: float
    variable_cost_per_unit: float
    contribution_per_unit: float
    contribution_margin: float | None  # share of revenue per unit; None when revenue is zero
    gross_margin: float | None
    break_even_price: float | None  # list price at which contribution per unit is zero
    lines: tuple[CostLine, ...]

    def price_for_margin(self, econ: Economics, margin: float) -> float | None:
        return price_for_margin(econ, margin)


def _per_unit_variable_cost(econ: Economics) -> tuple[float, float, float, float]:
    """Returns (cost of goods, fees, other variable, revenue) per gross unit shipped."""
    landed_s = econ.landed_cost_per_sellable()
    kept_share = 1.0 - econ.return_rate * (1.0 - econ.return_loss_rate)
    cogs = landed_s * kept_share
    fees = econ.net_price * econ.fee_rate
    other = econ.variable_labour_per_unit + econ.other_variable_per_unit
    revenue = econ.net_price * (1.0 - econ.return_rate)
    return cogs, fees, other, revenue


def unit_economics(econ: Economics) -> UnitEconomics:
    cogs, fees, other, revenue = _per_unit_variable_cost(econ)
    variable = cogs + fees + other
    contribution = revenue - variable
    lines = (
        CostLine("purchase_cost", econ.unit_cost, "unit_cost"),
        CostLine(
            "duty_and_non_recoverable_tax",
            econ.unit_cost * (econ.duty_rate + econ.non_recoverable_tax_rate),
            "unit_cost x (duty_rate + non_recoverable_tax_rate)",
        ),
        CostLine("freight", econ.freight_per_unit, "freight_per_unit"),
        CostLine("packaging", econ.packaging_per_unit, "packaging_per_unit"),
        CostLine(
            "wastage_allowance",
            econ.landed_cost_per_sellable() - econ.landed_cost(),
            "landed_cost / (1 - wastage_rate) - landed_cost",
        ),
        CostLine(
            "returns_restocked_credit",
            cogs - econ.landed_cost_per_sellable(),
            "-landed_cost_per_sellable x return_rate x (1 - return_loss_rate)",
        ),
        CostLine(
            "channel_fees",
            fees,
            "net_price x (payment_fee_rate + marketplace_fee_rate + commission_rate)",
        ),
        CostLine(
            "variable_labour_and_other", other, "variable_labour_per_unit + other_variable_per_unit"
        ),
    )
    return UnitEconomics(
        list_price=econ.price,
        net_price=econ.net_price,
        revenue_per_unit=revenue,
        landed_cost=econ.landed_cost(),
        landed_cost_per_sellable=econ.landed_cost_per_sellable(),
        variable_cost_per_unit=variable,
        contribution_per_unit=contribution,
        contribution_margin=contribution / revenue if revenue > 0 else None,
        gross_margin=(revenue - cogs) / revenue if revenue > 0 else None,
        break_even_price=price_for_margin(econ, 0.0),
        lines=lines,
    )


def price_for_margin(econ: Economics, margin: float) -> float | None:
    """List price at which contribution is `margin` of revenue, with all rates held fixed.

    Solves P(1-d)(1-r)(1-m) - P(1-d)f - C = 0 for P, where C is the price-independent cost
    per unit. None when no price can reach the margin (fees and refunds eat it all).
    """
    if not 0.0 <= margin < 1.0:
        raise ValueError("margin must be in [0, 1)")
    cogs, _, other, _ = _per_unit_variable_cost(econ)
    denominator = (1.0 - econ.discount_rate) * (
        (1.0 - econ.return_rate) * (1.0 - margin) - econ.fee_rate
    )
    if denominator <= 0:
        return None
    return (cogs + other) / denominator


def monthly_break_even_units(econ: Economics) -> float | None:
    """Units a month needed to cover recurring fixed and marketing costs; None if each unit loses money."""
    contribution = unit_economics(econ).contribution_per_unit
    if contribution <= 0:
        return None
    return (econ.monthly_fixed + econ.marketing_monthly) / contribution


def horizon_break_even_units(econ: Economics, months: int) -> float | None:
    """Units over `months` needed to recover launch costs plus recurring costs."""
    contribution = unit_economics(econ).contribution_per_unit
    if contribution <= 0:
        return None
    return (
        econ.launch_costs + months * (econ.monthly_fixed + econ.marketing_monthly)
    ) / contribution
