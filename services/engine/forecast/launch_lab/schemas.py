"""Payloads for `POST /v1/launch-lab/simulate`.

The request takes whatever the owner knows; everything missing is filled from the ledger,
labelled market data or stated assumptions, and every input comes back with its origin.
Rates are `_bp` integers and money is `{minor, currency}` throughout.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from engine.forecast._contracts import Figure, FigureInput, Finding, Money, Threshold
from engine.forecast.figures import Envelope, RuleCheck

Bp = int  # basis points of 1; ranges are checked by validators

Label = Literal["LAUNCH", "PILOT_FIRST", "REVISE", "HOLD", "NOT_RECOMMENDED"]
EvidenceClass = Literal["own_history", "comparable_history", "user_estimate", "none"]


class ProductSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str
    description: str | None = None
    target_customers: str | None = None
    target_market: str | None = None
    region: str | None = Field(None, description="e.g. PK-KHI; defaults to the tenant's country.")
    sales_channels: list[str] = Field(default_factory=list)
    comparable_skus: list[str] = Field(default_factory=list)


class CompetitorPrice(BaseModel):
    name: str
    price: Money
    observed_on: date | None = None
    source: str | None = None


class OwnerConstraints(BaseModel):
    min_contribution_margin_bp: Bp | None = Field(None, ge=0, lt=10_000)
    breakeven_horizon_months: int | None = Field(None, ge=1, le=60)
    launch_min_prob_breakeven_bp: Bp | None = Field(None, ge=0, le=10_000)
    max_loss_probability_bp: Bp | None = Field(None, ge=0, le=10_000)
    max_investment: Money | None = None
    min_cash_reserve: Money | None = None
    target_profit: Money | None = None


class WhatIf(BaseModel):
    name: str
    unit_cost_change_bp: Bp = 0
    demand_change_bp: Bp = Field(0, ge=-10_000)
    price_change_bp: Bp = Field(0, gt=-10_000)
    apply_elasticity: bool = True
    marketing_multiplier_bp: Bp = Field(10_000, ge=0)
    extra_discount_bp: Bp = Field(0, ge=0, lt=10_000)
    unsold_share_bp: Bp = Field(0, ge=0, le=10_000)
    delivery_delay_days: int = Field(0, ge=0, le=365)
    fx_change_bp: Bp = 0
    receivable_days: int | None = Field(None, ge=0, le=365)
    return_rate_bp: Bp | None = Field(None, ge=0, lt=10_000)
    initial_order_units: int | None = Field(None, ge=0)


_RATE_FIELDS = (
    "duty_rate_bp",
    "non_recoverable_tax_rate_bp",
    "payment_fee_rate_bp",
    "marketplace_fee_rate_bp",
    "commission_rate_bp",
    "return_rate_bp",
    "return_loss_rate_bp",
    "discount_rate_bp",
    "wastage_rate_bp",
    "imported_cost_share_bp",
    "unsold_recovery_rate_bp",
    "allocated_overhead_rate_bp",
)
_MONEY_FIELDS = (
    "unit_cost",
    "price",
    "freight_per_unit",
    "packaging_per_unit",
    "variable_labour_per_unit",
    "other_variable_per_unit",
    "launch_costs",
    "monthly_fixed_costs",
    "marketing_monthly",
    "storage_cost_per_unit_month",
    "available_capital",
)


class LaunchLabRequest(BaseModel):
    tenant_id: str
    currency: str
    product: ProductSpec

    unit_cost: Money | None = None
    price: Money | None = None
    freight_per_unit: Money | None = None
    packaging_per_unit: Money | None = None
    variable_labour_per_unit: Money | None = None
    other_variable_per_unit: Money | None = None
    launch_costs: Money | None = None
    monthly_fixed_costs: Money | None = None
    marketing_monthly: Money | None = None
    storage_cost_per_unit_month: Money | None = None
    available_capital: Money | None = None

    duty_rate_bp: Bp | None = None
    non_recoverable_tax_rate_bp: Bp | None = None
    payment_fee_rate_bp: Bp | None = None
    marketplace_fee_rate_bp: Bp | None = None
    commission_rate_bp: Bp | None = None
    return_rate_bp: Bp | None = None
    return_loss_rate_bp: Bp | None = None
    discount_rate_bp: Bp | None = None
    wastage_rate_bp: Bp | None = None
    imported_cost_share_bp: Bp | None = None
    unsold_recovery_rate_bp: Bp | None = None
    allocated_overhead_rate_bp: Bp | None = None

    expected_monthly_units: int | None = Field(None, ge=0)
    initial_order_units: int | None = Field(None, ge=0)
    moq: int | None = Field(None, ge=1)
    lead_time_days: int | None = Field(None, ge=0, le=365)
    receivable_days: int | None = Field(None, ge=0, le=365)
    payable_days: int | None = Field(None, ge=0, le=365)
    storage_capacity_units: int | None = Field(None, ge=0)
    launch_month: date | None = None
    horizon_months: int = Field(12, ge=1, le=36)

    competitor_prices: list[CompetitorPrice] = Field(default_factory=list)
    constraints: OwnerConstraints = Field(default_factory=OwnerConstraints)
    what_ifs: list[WhatIf] | None = Field(None, description="None: a standard set of what-ifs.")
    simulation_runs: int | None = Field(None, ge=200, le=50_000)
    seed: int | None = None
    as_of: date | None = None

    @model_validator(mode="after")
    def _consistent(self):
        currency = self.currency.upper()
        moneys = [getattr(self, f) for f in _MONEY_FIELDS]
        moneys += [c.price for c in self.competitor_prices]
        moneys += [
            self.constraints.max_investment,
            self.constraints.min_cash_reserve,
            self.constraints.target_profit,
        ]
        for m in moneys:
            if m is None:
                continue
            if m.currency != currency:
                raise ValueError(f"all amounts must be in {currency}, got {m.currency}")
        for name in _MONEY_FIELDS:
            m = getattr(self, name)
            if m is not None and m.minor < 0:
                raise ValueError(f"{name} cannot be negative")
        for name in _RATE_FIELDS:
            v = getattr(self, name)
            if v is not None and not 0 <= v <= 10_000:
                raise ValueError(f"{name} must be 0..10000 basis points")
        for name in ("return_rate_bp", "discount_rate_bp", "wastage_rate_bp"):
            v = getattr(self, name)
            if v is not None and v >= 10_000:
                raise ValueError(f"{name} must be below 10000")
        fees = sum(
            getattr(self, f) or 0
            for f in ("payment_fee_rate_bp", "marketplace_fee_rate_bp", "commission_rate_bp")
        )
        if fees >= 10_000:
            raise ValueError("channel fees together must be below 100%")
        if self.price is not None and self.price.minor == 0:
            raise ValueError("price must be positive")
        return self


# ---- response ------------------------------------------------------------------------------


class LaunchInput(FigureInput):
    """An input to the model with its origin and the reasoning behind it."""

    basis: str = Field(description="How the value was obtained, in one sentence.")
    as_of: date | None = None
    needs_verification: bool = False


class DataGap(BaseModel):
    field: str
    blocking: bool
    impact: str
    question: str = Field(description="The focused follow-up question that would close the gap.")


class Recommendation(BaseModel):
    label: Label
    plan: Literal["proposed", "pilot", "none"]
    rule_trace: list[RuleCheck]
    reason_codes: list[str]
    levers_that_fix: list[str] = Field(default_factory=list)


class MonthRow(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    demand_units: int
    sold_units: int
    lost_units: int
    purchased_units: int
    ending_stock_units: int
    revenue: Money
    cogs: Money
    gross_profit: Money
    contribution: Money
    cash_flow: Money
    cumulative_cash: Money


class ScenarioResult(BaseModel):
    name: Literal["low", "base", "high"]
    assumptions: list[LaunchInput]
    figures: list[Figure]
    months: list[MonthRow]


class HistogramBin(BaseModel):
    lower: Money
    upper: Money
    count: int


class Simulation(BaseModel):
    runs: int
    seed: int
    demand_evidence: EvidenceClass
    interpretation: Literal["model_based_not_calibrated"] = "model_based_not_calibrated"
    figures: list[Figure]
    profit_histogram: list[HistogramBin]


class SensitivityRow(BaseModel):
    driver: str
    swing_bp: Bp
    profit_low: Money
    profit_high: Money
    spread: Money
    rank: int


class UnviableThreshold(BaseModel):
    driver: str
    current: Figure
    threshold: Figure = Field(description="Value at which horizon profit reaches zero.")
    headroom_bp: Bp | None


class PriceOutcome(BaseModel):
    elasticity_scenario: str
    units: int
    profit: Money


class PricePoint(BaseModel):
    price: Money
    contribution_margin_bp: Bp | None
    outcomes: list[PriceOutcome]


class PriceRange(BaseModel):
    low: Money
    high: Money


class CompetitorRange(BaseModel):
    low: Money
    high: Money
    median: Money
    count: int
    origin: Literal["market_observed", "user_provided"]


class Pricing(BaseModel):
    figures: list[Figure] = Field(
        description="Current price, break-even price, price for the minimum margin."
    )
    competitor_range: CompetitorRange | None
    recommended_range: PriceRange | None
    elasticity_origin: Literal["ledger_derived", "assumption_unverified"]
    grid: list[PricePoint]
    note_codes: list[str] = Field(default_factory=list)


class InventoryPlan(BaseModel):
    figures: list[Figure] = Field(
        description="Standard and pilot initial order, safety stock, reorder point, capital and storage caps."
    )
    flags: list[str] = Field(default_factory=list)


class PlanSummary(BaseModel):
    plan: Literal["proposed", "pilot"]
    initial_order_units: int
    figures: list[Figure]


class Lever(BaseModel):
    lever_id: str
    change: FigureInput
    feasibility: Literal["high", "medium", "low"]
    urgency: Literal["before_order", "before_launch", "after_launch"]
    figures: list[Figure] = Field(
        description="Change in profit, peak cash, P(loss) and break-even units."
    )
    fixes_label: bool
    rank: int


class WhatIfResult(BaseModel):
    what_if: WhatIf
    figures: list[Figure]
    label: Label | None = None


class Explain(BaseModel):
    """Pointers into this response, so an agent can answer 'why?' from the numbers."""

    strongest_evidence: list[str] = Field(description="Names of the best-supported inputs.")
    main_risks: list[str] = Field(
        description="Drivers with the largest downside, by sensitivity rank."
    )
    safest_test: Literal["pilot", "proposed"]
    best_lever: str | None
    max_amount_at_risk: Figure


class LaunchLabResponse(Envelope):
    run_id: str
    inputs_hash: str
    engine_version: str
    currency: str
    as_of: date
    product: ProductSpec
    recommendation: Recommendation
    headline: list[Figure]
    inputs: list[LaunchInput]
    data_gaps: list[DataGap]
    policy: list[Threshold]
    unit_economics: list[Figure]
    cost_lines: list[Figure]
    scenarios: list[ScenarioResult]
    simulation: Simulation | None
    sensitivity: list[SensitivityRow]
    unviable_thresholds: list[UnviableThreshold]
    pricing: Pricing
    inventory_plan: InventoryPlan
    plans: list[PlanSummary]
    levers: list[Lever]
    what_ifs: list[WhatIfResult]
    explain: Explain
    findings: list[Finding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
