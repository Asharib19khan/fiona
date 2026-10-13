"""Month-by-month inventory, profit and cash model for a launch, vectorised over runs.

One function serves every case: the deterministic base case is a single run with neutral
shocks, the low/base/high cases are single runs with stated shocks, and the Monte Carlo is
many runs with sampled shocks. Keeping one model means the cases can never disagree about
how the business works.

Timeline: month 0 is the order before launch (launch costs and the initial purchase);
months 1..H are trading months. Stock ordered at the end of month m arrives at the start of
month m + 1 + lead_months. Cash from sales and payments to suppliers can be delayed by
receivable and payable days, so the cash array runs a few months past the horizon to
collect what is owed. Stock still on hand at the horizon is cleared at the recovery rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from engine.forecast.launch_lab.economics import Economics

DAYS_PER_MONTH = 30.0


def lead_months_from_days(days: float) -> int:
    """Whole months of supplier lead time, rounding half up (45 days -> 2 months)."""
    if days < 0:
        raise ValueError("lead time cannot be negative")
    return math.floor(days / DAYS_PER_MONTH + 0.5)


def service_z(service_level: float) -> float:
    return NormalDist().inv_cdf(service_level)


@dataclass(frozen=True)
class OrderPlan:
    initial_order: int  # units purchased before launch
    lead_months: int
    moq: int = 1
    reorder: bool = True
    review_months: int = 1
    first_arrival_month: int = 1  # a delivery delay pushes the first stock later
    storage_capacity: float | None = None  # max sellable units on hand plus on order
    safety_z: float = 1.2816  # service level 90%
    noise_sigma: float = 0.15  # month-to-month demand noise the planner protects against

    def __post_init__(self) -> None:
        if self.initial_order < 0 or self.moq < 1 or self.lead_months < 0 or self.review_months < 1:
            raise ValueError("invalid order plan")
        if self.first_arrival_month < 1:
            raise ValueError("first arrival is month 1 at the earliest")


def initial_order_quantity(
    planned: np.ndarray,
    *,
    lead_months: int,
    wastage_rate: float,
    moq: int,
    cover_months: int | None = None,
    safety_z: float = 0.0,
    noise_sigma: float = 0.0,
) -> int:
    """Units to buy before launch so stock lasts until the first reorder can arrive.

    The first reorder is placed at the end of month 1 and arrives in month 2 + lead, so by
    default the initial order covers months 1..1 + lead. A pilot passes a shorter
    `cover_months` and no safety stock.
    """
    months = cover_months if cover_months is not None else 1 + lead_months
    window = planned[: max(1, min(len(planned), months))]
    need = float(window.sum()) + safety_z * noise_sigma * math.sqrt(float((window**2).sum()))
    units = math.ceil(need / (1.0 - wastage_rate) - 1e-9) if need > 0 else 0
    return max(units, moq) if units > 0 else 0


@dataclass(frozen=True)
class Shocks:
    """Per-run departures from the plan. Multipliers of 1 and additions of 0 are neutral."""

    demand_multiplier: np.ndarray  # (N,) level of demand relative to plan
    monthly_noise: np.ndarray  # (N, H) month-to-month variation around that level
    cost_multiplier: np.ndarray  # (N,) supplier price relative to quote
    extra_discount: np.ndarray  # (N,) discount added to the planned average discount
    return_multiplier: np.ndarray  # (N,) return rate relative to plan
    fx_multiplier: np.ndarray  # (N,) exchange rate relative to plan, on the imported share

    @property
    def runs(self) -> int:
        return int(self.demand_multiplier.shape[0])

    @staticmethod
    def neutral(horizon: int, runs: int = 1) -> Shocks:
        ones = np.ones(runs)
        return Shocks(
            ones, np.ones((runs, horizon)), ones.copy(), np.zeros(runs), ones.copy(), ones.copy()
        )

    @staticmethod
    def fixed(
        horizon: int,
        *,
        demand: float = 1.0,
        cost: float = 1.0,
        extra_discount: float = 0.0,
        returns: float = 1.0,
        fx: float = 1.0,
    ) -> Shocks:
        one = np.ones(1)
        return Shocks(
            one * demand,
            np.ones((1, horizon)),
            one * cost,
            one * extra_discount,
            one * returns,
            one * fx,
        )


def sample_shocks(
    *,
    runs: int,
    horizon: int,
    seed: int,
    demand_sigma: float,
    noise_sigma: float,
    cost_triangular: tuple[float, float, float],
    max_extra_discount: float,
    return_spread: float,
    fx_sigma: float = 0.0,
) -> Shocks:
    """Seeded draws, so the same request always gives the same distribution.

    The demand level is log-normal with median 1, so the base case is the median outcome.
    Monthly noise is log-normal with mean 1. The supplier-cost change is triangular, skewed
    up when the policy says so. These distributions are modelling assumptions, not
    calibrated probabilities, and results say so.
    """
    rng = np.random.default_rng(seed)
    demand = np.exp(rng.normal(0.0, demand_sigma, runs))
    noise = (
        np.exp(rng.normal(-0.5 * noise_sigma**2, noise_sigma, (runs, horizon)))
        if noise_sigma > 0
        else np.ones((runs, horizon))
    )
    lo, mode, hi = cost_triangular
    cost = 1.0 + (rng.triangular(lo, mode, hi, runs) if hi > lo else np.full(runs, mode))
    discount = (
        rng.triangular(0.0, 0.0, max_extra_discount, runs)
        if max_extra_discount > 0
        else np.zeros(runs)
    )
    returns = rng.uniform(1.0 - return_spread, 1.0 + return_spread, runs)
    fx = np.exp(rng.normal(0.0, fx_sigma, runs)) if fx_sigma > 0 else np.ones(runs)
    return Shocks(demand, noise, cost, discount, returns, fx)


@dataclass(frozen=True)
class SimResult:
    months: int
    demand: np.ndarray  # (N, H) units customers wanted
    sold: np.ndarray  # (N, H) units shipped
    lost: np.ndarray  # (N, H) demand missed for lack of stock
    revenue: np.ndarray  # (N, H) net of discounts and refunds
    cogs: np.ndarray
    fees: np.ndarray
    other_variable: np.ndarray
    holding: np.ndarray
    fixed: np.ndarray  # (H,)
    marketing: np.ndarray  # (H,)
    contribution: np.ndarray  # (N, H) product operating contribution per month
    purchases: np.ndarray  # (N, H + 1) units ordered; column 0 is the initial order
    stock_end: np.ndarray  # (N, H) sellable units on hand at month end
    cash_flow: np.ndarray  # (N, T) month 0 .. T-1, including collections after the horizon
    ending_units: np.ndarray  # (N,) unsold units at the horizon, sellable plus stranded
    writedown: np.ndarray  # (N,) cost not recovered on those units
    recovery: np.ndarray  # (N,) cash recovered on those units
    launch_costs: float
    profit: np.ndarray  # (N,) horizon profit from the product, before allocated overhead
    overhead: np.ndarray  # (N,) allocated shared overhead
    peak_cash: np.ndarray  # (N,) most cash tied up at any point (>= 0)
    payback_month: np.ndarray  # (N,) month from which cumulative cash stays >= 0; inf if never
    npv: np.ndarray  # (N,)

    @property
    def profit_after_overhead(self) -> np.ndarray:
        return self.profit - self.overhead

    @property
    def cumulative_cash(self) -> np.ndarray:
        return np.cumsum(self.cash_flow, axis=1)


def simulate(
    econ: Economics,
    plan: OrderPlan,
    planned: np.ndarray,
    shocks: Shocks,
    *,
    realized_base: np.ndarray | None = None,
    monthly_discount_rate: float = 0.0,
) -> SimResult:
    """Run the launch month by month.

    `planned` is the demand the owner orders against. `realized_base` is the demand that
    actually turns up before shocks (defaults to the plan); a what-if like "demand is 25%
    lower" changes the realised demand but not the plan, as it would in real life.
    """
    planned = np.asarray(planned, dtype=float)
    if planned.ndim != 1 or (planned < 0).any():
        raise ValueError("planned demand must be a non-negative 1-D array")
    realized_base = planned if realized_base is None else np.asarray(realized_base, dtype=float)
    H = planned.shape[0]
    N = shocks.runs
    if shocks.monthly_noise.shape != (N, H) or realized_base.shape != (H,):
        raise ValueError("shocks and demand arrays must match the horizon")

    delay_r = econ.receivable_days / DAYS_PER_MONTH
    delay_p = econ.payable_days / DAYS_PER_MONTH
    T = H + 2 + math.ceil(max(delay_r, delay_p))
    cash = np.zeros((N, T))

    def add_cash(month: int, amount: np.ndarray, delay: float) -> None:
        k = math.floor(delay)
        frac = delay - k
        cash[:, month + k] += amount * (1.0 - frac)
        if frac > 0:
            cash[:, month + k + 1] += amount * frac

    w = econ.wastage_rate
    purchase_price = (
        econ.unit_cost
        * shocks.cost_multiplier
        * (1.0 + econ.imported_cost_share * (shocks.fx_multiplier - 1.0))
    )
    landed = (
        purchase_price * (1.0 + econ.duty_rate + econ.non_recoverable_tax_rate)
        + econ.freight_per_unit
        + econ.packaging_per_unit
    )
    landed_s = landed / (1.0 - w)
    net_price = econ.price * (1.0 - np.clip(econ.discount_rate + shocks.extra_discount, 0.0, 0.95))
    r = np.clip(econ.return_rate * shocks.return_multiplier, 0.0, 0.95)
    other_var = econ.variable_labour_per_unit + econ.other_variable_per_unit

    demand = realized_base[None, :] * shocks.demand_multiplier[:, None] * shocks.monthly_noise
    sold = np.zeros((N, H))
    lost = np.zeros((N, H))
    revenue = np.zeros((N, H))
    cogs = np.zeros((N, H))
    fees = np.zeros((N, H))
    other = np.zeros((N, H))
    holding = np.zeros((N, H))
    stock_end = np.zeros((N, H))
    purchases = np.zeros((N, H + 1))
    arrivals = np.zeros((N, H + 2))  # purchased units arriving at the start of each month
    fixed = np.full(H, econ.monthly_fixed)
    marketing = np.full(H, econ.marketing_monthly)

    first_arrival = min(plan.first_arrival_month, H)
    purchases[:, 0] = plan.initial_order
    arrivals[:, first_arrival] += plan.initial_order
    cash[:, 0] -= econ.launch_costs
    add_cash(0, -plan.initial_order * landed, delay_p)

    stock = np.zeros(N)
    stranded = np.zeros(N)
    cumulative_planned = np.cumsum(planned)
    for m in range(1, H + 1):
        h = m - 1
        received = arrivals[:, m] * (1.0 - w)
        stranded += received * econ.unsellable_share
        stock += received * (1.0 - econ.unsellable_share)
        start = stock.copy()

        sold[:, h] = np.minimum(stock, demand[:, h])
        lost[:, h] = demand[:, h] - sold[:, h]
        restocked = sold[:, h] * r * (1.0 - econ.return_loss_rate)
        stock = stock - sold[:, h] + restocked
        stock_end[:, h] = stock

        revenue[:, h] = sold[:, h] * net_price * (1.0 - r)
        fees[:, h] = sold[:, h] * net_price * econ.fee_rate
        cogs[:, h] = (sold[:, h] - restocked) * landed_s
        other[:, h] = sold[:, h] * other_var
        holding[:, h] = econ.storage_per_unit_month * (start + stock) / 2.0

        add_cash(m, revenue[:, h] - fees[:, h], delay_r)
        cash[:, m] -= other[:, h] + holding[:, h] + fixed[h] + marketing[h]

        arrival = m + 1 + plan.lead_months
        if plan.reorder and m < H and arrival <= H:
            # Scale the rest of the plan by how demand has run so far, within limits.
            observed = demand[:, :m].sum(axis=1)
            expected = cumulative_planned[m - 1]
            adapt = np.clip(observed / expected, 0.5, 2.0) if expected > 0 else np.ones(N)
            window = planned[m : min(H, arrival + plan.review_months - 1)]
            target = adapt * (
                window.sum()
                + plan.safety_z * plan.noise_sigma * math.sqrt(float((window**2).sum()))
            )
            position = stock + arrivals[:, m + 1 :].sum(axis=1) * (1.0 - w)
            need = target - position
            if plan.storage_capacity is not None:
                need = np.minimum(need, plan.storage_capacity - position)
            qty = np.where(need > 1e-9, np.ceil(need / (1.0 - w) - 1e-9), 0.0)
            qty = np.where(qty > 0, np.maximum(qty, plan.moq), 0.0)
            if plan.storage_capacity is not None:
                qty = np.where(position + qty * (1.0 - w) <= plan.storage_capacity + 1e-9, qty, 0.0)
            purchases[:, m] = qty
            arrivals[:, arrival] += qty
            add_cash(m, -qty * landed, delay_p)

    ending_units = stock + stranded
    ending_value = ending_units * landed_s
    recovery = ending_value * econ.unsold_recovery_rate
    writedown = ending_value - recovery
    cash[:, H] += recovery

    contribution = revenue - fees - cogs - other - holding - fixed[None, :] - marketing[None, :]
    profit = contribution.sum(axis=1) - econ.launch_costs - writedown
    overhead = econ.overhead_rate * revenue.sum(axis=1)

    cumulative = np.cumsum(cash, axis=1)
    peak_cash = np.maximum(0.0, -cumulative.min(axis=1))
    # Payback is sustained recovery: the month after cumulative cash is last below zero,
    # so a seasonal restock that dips cash negative again pushes payback out.
    negative = cumulative < -1e-6
    last_negative = np.where(negative.any(axis=1), T - 1 - np.argmax(negative[:, ::-1], axis=1), -1)
    payback = np.where(negative[:, -1], np.inf, (last_negative + 1).astype(float))
    discount = (1.0 + monthly_discount_rate) ** -np.arange(T)
    npv = cash @ discount

    return SimResult(
        months=H,
        demand=demand,
        sold=sold,
        lost=lost,
        revenue=revenue,
        cogs=cogs,
        fees=fees,
        other_variable=other,
        holding=holding,
        fixed=fixed,
        marketing=marketing,
        contribution=contribution,
        purchases=purchases,
        stock_end=stock_end,
        cash_flow=cash,
        ending_units=ending_units,
        writedown=writedown,
        recovery=recovery,
        launch_costs=econ.launch_costs,
        profit=profit,
        overhead=overhead,
        peak_cash=peak_cash,
        payback_month=payback,
        npv=npv,
    )
