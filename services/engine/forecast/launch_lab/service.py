"""Launch Lab analysis: resolved inputs in, a fully explained LaunchLabResponse out.

Everything numeric comes from the deterministic model in `simulate`; the Monte Carlo only
adds a distribution on top. The label comes from transparent rules (LL-01 to LL-09) whose
thresholds come from the rulebook, the owner or labelled draft defaults.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime

import numpy as np

from engine.decisions.tvm import annual_rate, irr, monthly_rate
from engine.forecast._contracts import (
    Action,
    Evidence,
    Figure,
    Finding,
    Money,
    Origin,
    Period,
    Threshold,
    Unit,
)
from engine.forecast.figures import (
    RuleCheck,
    bp_figure,
    bp_input,
    bp_threshold,
    money_figure,
    money_threshold,
    stable_id,
    to_bp,
    value_figure,
    value_input,
)
from engine.forecast.launch_lab.demand import DemandProfile, add_months
from engine.forecast.launch_lab.economics import Economics, monthly_break_even_units, unit_economics
from engine.forecast.launch_lab.policy import LaunchPolicy, PolicySource
from engine.forecast.launch_lab.schemas import (
    CompetitorRange,
    DataGap,
    EvidenceClass,
    Explain,
    HistogramBin,
    InventoryPlan,
    LaunchInput,
    LaunchLabResponse,
    Lever,
    MonthRow,
    PlanSummary,
    PriceOutcome,
    PricePoint,
    PriceRange,
    Pricing,
    ProductSpec,
    Recommendation,
    ScenarioResult,
    SensitivityRow,
    Simulation,
    UnviableThreshold,
    WhatIf,
    WhatIfResult,
)
from engine.forecast.launch_lab.simulate import (
    OrderPlan,
    Shocks,
    SimResult,
    initial_order_quantity,
    lead_months_from_days,
    sample_shocks,
    service_z,
    simulate,
)
from engine.forecast.money import Money as _Money
from engine.forecast.money import round_minor

ENGINE_VERSION = "launch_lab/0.1.0"
LEVER_RUNS = 1000

POLICY_ORIGIN = {
    PolicySource.RULEBOOK: Origin.RULEBOOK,
    PolicySource.OWNER: Origin.OWNER,
    PolicySource.DRAFT_DEFAULT: Origin.DRAFT_DEFAULT,
}


@dataclass(frozen=True)
class ResolvedCase:
    """Every input the analysis needs, already resolved and labelled."""

    tenant_id: str
    currency: str
    as_of: date
    product: ProductSpec
    econ: Economics
    profile: DemandProfile
    evidence: EvidenceClass
    moq: int
    lead_days: int
    inputs: list[LaunchInput]
    gaps: list[DataGap] = field(default_factory=list)
    initial_order_override: int | None = None
    storage_capacity: int | None = None
    available_capital: float | None = None
    competitor_prices: list[tuple[float, str]] = field(default_factory=list)  # (minor, origin)
    elasticity_origin: str = "assumption_unverified"
    what_ifs: list[WhatIf] = field(default_factory=list)
    request_fingerprint: str = ""


DEFAULT_WHAT_IFS = [
    WhatIf(name="Supplier cost +10%", unit_cost_change_bp=1000),
    WhatIf(name="Demand 25% below plan", demand_change_bp=-2500),
    WhatIf(
        name="Competitor cuts price 10% and we match", price_change_bp=-1000, apply_elasticity=False
    ),
    WhatIf(name="Marketing doubles", marketing_multiplier_bp=20000),
    WhatIf(name="15% of stock never sells", unsold_share_bp=1500),
    WhatIf(name="Delivery 30 days late", delivery_delay_days=30),
    WhatIf(name="Customers pay 60 days late", receivable_days=60),
    WhatIf(name="Buy 1,000 units up front", initial_order_units=1000),
]


@dataclass
class _Run:
    econ: Economics
    planned: np.ndarray
    realized: np.ndarray
    plan: OrderPlan


@dataclass
class _Outcome:
    det: SimResult
    mc: SimResult


class _Analysis:
    def __init__(
        self,
        case: ResolvedCase,
        policy: LaunchPolicy,
        sources: dict[str, PolicySource],
        runs: int,
        seed: int,
    ):
        self.case = case
        self.policy = policy
        self.sources = sources
        self.runs = runs
        self.seed = seed
        self.cur = case.currency
        self.H = case.profile.horizon_months
        self.lead_months = lead_months_from_days(case.lead_days)
        self.z = service_z(policy.service_level)
        self.elasticity = policy.elasticity_scenarios.get("medium_sensitivity", -1.2)
        self.i_month = monthly_rate(policy.cost_of_capital_annual)
        self.sigma = getattr(policy.demand_sigma, case.evidence, policy.demand_sigma.user_estimate)
        self.planned = case.profile.monthly(price=case.econ.price, elasticity=self.elasticity)
        self.shocks = self._shocks(runs)
        self.lever_shocks = self._shocks(min(runs, LEVER_RUNS))

    # ---- model plumbing -------------------------------------------------------------------

    def _shocks(self, runs: int) -> Shocks:
        p = self.policy
        return sample_shocks(
            runs=runs,
            horizon=self.H,
            seed=self.seed,
            demand_sigma=self.sigma,
            noise_sigma=p.monthly_noise_sigma,
            cost_triangular=p.cost_shock,
            max_extra_discount=p.max_extra_discount,
            return_spread=p.return_rate_spread,
            fx_sigma=0.05 if self.case.econ.imported_cost_share > 0 else 0.0,
        )

    def standard_qty(self, planned: np.ndarray, econ: Economics) -> int:
        return initial_order_quantity(
            planned,
            lead_months=self.lead_months,
            wastage_rate=econ.wastage_rate,
            moq=self.case.moq,
            safety_z=self.z,
            noise_sigma=self.policy.monthly_noise_sigma,
        )

    def pilot_qty(self, planned: np.ndarray, econ: Economics) -> int:
        return initial_order_quantity(
            planned,
            lead_months=self.lead_months,
            wastage_rate=econ.wastage_rate,
            moq=self.case.moq,
            cover_months=self.policy.pilot_cover_months,
        )

    def make_run(
        self,
        *,
        econ: Economics | None = None,
        planned: np.ndarray | None = None,
        realized: np.ndarray | None = None,
        initial: int | None = None,
        first_arrival: int = 1,
    ) -> _Run:
        econ = econ or self.case.econ
        planned = self.planned if planned is None else planned
        realized = planned if realized is None else realized
        if initial is None:
            initial = (
                self.case.initial_order_override
                if self.case.initial_order_override is not None
                else self.standard_qty(planned, econ)
            )
        plan = OrderPlan(
            initial_order=initial,
            lead_months=self.lead_months,
            moq=self.case.moq,
            review_months=self.policy.review_months,
            first_arrival_month=first_arrival,
            storage_capacity=self.case.storage_capacity,
            safety_z=self.z,
            noise_sigma=self.policy.monthly_noise_sigma,
        )
        return _Run(econ, planned, realized, plan)

    def det(self, run: _Run, shocks: Shocks | None = None) -> SimResult:
        return simulate(
            run.econ,
            run.plan,
            run.planned,
            shocks or Shocks.neutral(self.H),
            realized_base=run.realized,
            monthly_discount_rate=self.i_month,
        )

    def outcome(self, run: _Run, shocks: Shocks | None = None) -> _Outcome:
        return _Outcome(self.det(run), self.det(run, shocks or self.shocks))

    # ---- formatting ------------------------------------------------------------------------

    def m(self, minor: float) -> Money:
        return _Money(minor=round_minor(minor), currency=self.cur)

    def months(self, r: SimResult, i: int = 0) -> list[MonthRow]:
        labels = self.case.profile.month_labels()
        cum = r.cumulative_cash[i]
        rows = []
        for h in range(self.H):
            gross = r.revenue[i, h] - r.cogs[i, h]
            rows.append(
                MonthRow(
                    month=labels[h],
                    demand_units=round_minor(r.demand[i, h]),
                    sold_units=round_minor(r.sold[i, h]),
                    lost_units=round_minor(r.lost[i, h]),
                    purchased_units=round_minor(
                        r.purchases[i, h + 1] + (r.purchases[i, 0] if h == 0 else 0)
                    ),
                    ending_stock_units=round_minor(r.stock_end[i, h]),
                    revenue=self.m(r.revenue[i, h]),
                    cogs=self.m(r.cogs[i, h]),
                    gross_profit=self.m(gross),
                    contribution=self.m(r.contribution[i, h]),
                    cash_flow=self.m(r.cash_flow[i, h + 1] + (r.cash_flow[i, 0] if h == 0 else 0)),
                    cumulative_cash=self.m(cum[h + 1]),
                )
            )
        return rows

    def payback_figure(
        self, r: SimResult, i: int = 0, metric: str = "launch.payback_month"
    ) -> Figure:
        pb = r.payback_month[i]
        if not math.isfinite(pb) or pb > self.H:
            return Figure(
                metric_id=metric,
                label="Month the cash invested is paid back",
                unit=Unit.MONTHS,
                status="not_applicable",
                note="not paid back within the horizon",
            )
        return value_figure(
            metric,
            "Month the cash invested is paid back",
            pb,
            Unit.MONTHS,
            formula="month after cumulative cash is last below zero",
        )

    def scenario_figures(self, r: SimResult, i: int = 0, prefix: str = "launch") -> list[Figure]:
        flows = list(r.cash_flow[i])
        rate = irr(flows)
        irr_fig = (
            bp_figure(
                f"{prefix}.irr_annual",
                "Internal rate of return (annualised)",
                annual_rate(rate.rate),
                formula="annualise(monthly IRR of cash flows)",
            )
            if rate.valid and rate.rate > -0.99
            else Figure(
                metric_id=f"{prefix}.irr_annual",
                label="Internal rate of return (annualised)",
                unit=Unit.BP,
                status="not_applicable",
                note=f"IRR not meaningful: {rate.status.value}",
            )
        )
        return [
            value_figure(f"{prefix}.units_sold", "Units sold", r.sold[i].sum(), Unit.UNITS),
            money_figure(
                f"{prefix}.revenue",
                "Revenue (net of discounts and refunds)",
                r.revenue[i].sum(),
                self.cur,
            ),
            money_figure(
                f"{prefix}.gross_profit", "Gross profit", (r.revenue[i] - r.cogs[i]).sum(), self.cur
            ),
            money_figure(
                f"{prefix}.operating_contribution",
                "Operating contribution before launch costs",
                r.contribution[i].sum(),
                self.cur,
            ),
            money_figure(
                f"{prefix}.horizon_profit",
                "Profit from the product over the horizon",
                r.profit[i],
                self.cur,
                formula="sum(contribution) - launch_costs - write-down of unsold stock",
            ),
            money_figure(
                f"{prefix}.profit_after_overhead",
                "Profit after allocated shared overhead",
                r.profit_after_overhead[i],
                self.cur,
            ),
            money_figure(
                f"{prefix}.peak_cash", "Most cash tied up at any point", r.peak_cash[i], self.cur
            ),
            self.payback_figure(r, i, f"{prefix}.payback_month"),
            money_figure(
                f"{prefix}.npv",
                "Net present value",
                r.npv[i],
                self.cur,
                inputs=[
                    bp_input(
                        "cost_of_capital_annual",
                        self.policy.cost_of_capital_annual,
                        POLICY_ORIGIN[self.sources["cost_of_capital_annual"]],
                    )
                ],
            ),
            irr_fig,
            value_figure(
                f"{prefix}.ending_units",
                "Units left at the end of the horizon",
                r.ending_units[i],
                Unit.UNITS,
            ),
            money_figure(
                f"{prefix}.unsold_writedown",
                "Cost written off on unsold stock",
                r.writedown[i],
                self.cur,
            ),
            value_figure(
                f"{prefix}.lost_units",
                "Sales missed for lack of stock",
                r.lost[i].sum(),
                Unit.UNITS,
            ),
        ]

    # ---- rules -----------------------------------------------------------------------------

    def rules(self, out: _Outcome, econ: Economics) -> list[RuleCheck]:
        p, src = self.policy, self.sources
        ue = unit_economics(econ)
        margin = ue.contribution_margin or 0.0
        det = out.det
        payback = det.payback_month[0]
        p_loss = float((out.mc.profit < 0).mean())
        p_pay = float((out.mc.payback_month <= p.breakeven_horizon_months).mean())
        be_units = monthly_break_even_units(econ)
        peak_high = float(np.quantile(out.mc.demand.max(axis=1), 0.9))
        checks = [
            RuleCheck(
                rule_id="LL-01",
                description="Each unit sold earns a positive contribution",
                metric_id="launch.contribution_per_unit",
                threshold=money_threshold(
                    "contribution_per_unit",
                    0,
                    self.cur,
                    Origin.DRAFT_DEFAULT,
                    ">",
                    ue.contribution_per_unit > 0,
                ),
                passed=ue.contribution_per_unit > 0,
            ),
            RuleCheck(
                rule_id="LL-02",
                description="Contribution margin meets the minimum",
                metric_id="launch.contribution_margin",
                threshold=bp_threshold(
                    "min_contribution_margin",
                    p.min_contribution_margin,
                    POLICY_ORIGIN[src["min_contribution_margin"]],
                    ">=",
                    margin >= p.min_contribution_margin,
                ),
                passed=margin >= p.min_contribution_margin,
            ),
            RuleCheck(
                rule_id="LL-03",
                description="Cash is paid back within the owner's horizon (base case)",
                metric_id="launch.payback_month",
                threshold=Threshold(
                    name="breakeven_horizon_months",
                    value=p.breakeven_horizon_months,
                    unit=Unit.MONTHS,
                    origin=POLICY_ORIGIN[src["breakeven_horizon_months"]],
                    comparison="<=",
                    passed=bool(payback <= p.breakeven_horizon_months),
                ),
                passed=bool(payback <= p.breakeven_horizon_months),
            ),
            RuleCheck(
                rule_id="LL-04",
                description="Chance of a loss over the horizon is within the limit",
                metric_id="launch.p_loss",
                threshold=bp_threshold(
                    "max_loss_probability",
                    p.max_loss_probability,
                    POLICY_ORIGIN[src["max_loss_probability"]],
                    "<=",
                    p_loss <= p.max_loss_probability,
                ),
                passed=p_loss <= p.max_loss_probability,
            ),
            RuleCheck(
                rule_id="LL-05",
                description="Monthly break-even volume is within plausible demand (p90 peak month)",
                metric_id="launch.monthly_break_even_units",
                threshold=Threshold(
                    name="p90_peak_month_demand",
                    value=round_minor(peak_high),
                    unit=Unit.UNITS,
                    origin=Origin.ESTIMATE,
                    comparison="<=",
                    passed=be_units is not None and be_units <= peak_high,
                ),
                passed=be_units is not None and be_units <= peak_high,
            ),
        ]
        if self.case.available_capital is not None:
            ok = det.peak_cash[0] <= self.case.available_capital
            checks.append(
                RuleCheck(
                    rule_id="LL-06",
                    description="Peak cash need fits the capital set aside",
                    metric_id="launch.peak_cash",
                    threshold=money_threshold(
                        "available_capital",
                        self.case.available_capital,
                        self.cur,
                        Origin.USER,
                        "<=",
                        ok,
                    ),
                    passed=ok,
                )
            )
        if p.max_investment_minor is not None:
            ok = det.peak_cash[0] <= p.max_investment_minor
            checks.append(
                RuleCheck(
                    rule_id="LL-07",
                    description="Peak cash need is within the owner's maximum investment",
                    metric_id="launch.peak_cash",
                    threshold=money_threshold(
                        "max_investment", p.max_investment_minor, self.cur, Origin.OWNER, "<=", ok
                    ),
                    passed=ok,
                )
            )
        checks.append(
            RuleCheck(
                rule_id="LL-08",
                description="Chance of paying back within the horizon supports a full launch",
                metric_id="launch.p_payback_within_horizon",
                threshold=bp_threshold(
                    "launch_min_prob_breakeven",
                    p.launch_min_prob_breakeven,
                    POLICY_ORIGIN[src["launch_min_prob_breakeven"]],
                    ">=",
                    p_pay >= p.launch_min_prob_breakeven,
                ),
                passed=p_pay >= p.launch_min_prob_breakeven,
                hard=False,
            )
        )
        strong = self.case.evidence == "own_history"
        checks.append(
            RuleCheck(
                rule_id="LL-09",
                description="Demand evidence comes from the product's own sales history",
                metric_id="launch.demand_evidence",
                threshold=Threshold(
                    name="evidence_class_is_own_history",
                    value=1,
                    unit=Unit.COUNT,
                    origin=Origin.DRAFT_DEFAULT,
                    comparison=">=",
                    passed=strong,
                ),
                passed=strong,
                hard=False,
            )
        )
        return checks

    @staticmethod
    def hard_pass(checks: list[RuleCheck]) -> bool:
        return all(c.passed for c in checks if c.hard)


def _bisect(f: Callable[[float], float], lo: float, hi: float, iters: int = 40) -> float | None:
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def _fingerprint(case: ResolvedCase, policy: LaunchPolicy, runs: int, seed: int) -> str:
    payload = {
        "case": case.request_fingerprint or repr(case.econ) + repr(case.profile),
        "policy": policy.model_dump(mode="json"),
        "runs": runs,
        "seed": seed,
        "engine": ENGINE_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def analyse(
    case: ResolvedCase,
    policy: LaunchPolicy,
    sources: dict[str, PolicySource],
    *,
    mode: str,
    generated_at: datetime,
    runs: int | None = None,
    seed: int | None = None,
) -> LaunchLabResponse:
    runs = runs or policy.simulation_runs
    seed = policy.seed if seed is None else seed
    a = _Analysis(case, policy, sources, runs, seed)
    cur, econ, H = case.currency, case.econ, a.H
    inputs_hash = _fingerprint(case, policy, runs, seed)
    run_id = "fc_" + inputs_hash[:20]

    # Unit economics ----------------------------------------------------------------------
    ue = unit_economics(econ)
    min_margin_price = None
    from engine.forecast.launch_lab.economics import price_for_margin

    min_margin_price = price_for_margin(econ, policy.min_contribution_margin)
    ue_figs = [
        money_figure(
            "launch.net_price",
            "Price after average discount",
            ue.net_price,
            cur,
            formula="price x (1 - discount_rate)",
        ),
        money_figure(
            "launch.landed_cost",
            "Landed cost per unit",
            ue.landed_cost,
            cur,
            formula="unit_cost x (1 + duty + non-recoverable tax) + freight + packaging",
        ),
        money_figure(
            "launch.variable_cost_per_unit",
            "Variable cost per unit sold",
            ue.variable_cost_per_unit,
            cur,
        ),
        money_figure(
            "launch.contribution_per_unit",
            "Contribution per unit sold",
            ue.contribution_per_unit,
            cur,
            formula="net_price x (1 - return_rate) - variable_cost_per_unit",
        ),
        bp_figure(
            "launch.contribution_margin",
            "Contribution margin",
            ue.contribution_margin or 0.0,
            formula="contribution_per_unit / revenue_per_unit",
        ),
        bp_figure("launch.gross_margin", "Gross margin", ue.gross_margin or 0.0),
    ]
    be_units = monthly_break_even_units(econ)
    ue_figs.append(
        value_figure(
            "launch.monthly_break_even_units",
            "Units a month to cover fixed and marketing costs",
            be_units,
            Unit.UNITS,
            formula="(monthly_fixed + marketing_monthly) / contribution_per_unit",
        )
        if be_units is not None
        else Figure(
            metric_id="launch.monthly_break_even_units",
            label="Units a month to cover fixed and marketing costs",
            unit=Unit.UNITS,
            status="not_applicable",
            note="each unit loses money",
        )
    )
    cost_lines = [
        money_figure(
            f"launch.cost_line.{line.name}",
            line.name.replace("_", " ").capitalize(),
            line.per_unit,
            cur,
            formula=line.formula,
        )
        for line in ue.lines
    ]

    # Plans and scenarios -----------------------------------------------------------------
    proposed_run = a.make_run()
    pilot_run = a.make_run(initial=a.pilot_qty(a.planned, econ))
    proposed = a.outcome(proposed_run)
    pilot = a.outcome(pilot_run)

    lowq = math.exp(-1.2816 * a.sigma)
    highq = math.exp(1.2816 * a.sigma)
    low_shock = Shocks.fixed(
        H,
        demand=lowq,
        cost=1 + policy.low_case_cost_change,
        extra_discount=policy.low_case_extra_discount,
        returns=policy.low_case_return_multiplier,
    )
    high_shock = Shocks.fixed(H, demand=highq)
    low = a.det(proposed_run, low_shock)
    base = proposed.det
    high = a.det(proposed_run, high_shock)

    def scen_assumptions(name: str) -> list[LaunchInput]:
        if name == "base":
            return [
                LaunchInput(
                    name="demand_multiplier",
                    value=10_000,
                    unit=Unit.BP,
                    origin=Origin.ESTIMATE,
                    basis="Median of the demand distribution: the most defensible estimate.",
                )
            ]
        if name == "low":
            return [
                LaunchInput(
                    name="demand_multiplier",
                    value=to_bp(lowq),
                    unit=Unit.BP,
                    origin=Origin.ESTIMATE,
                    basis=f"10th percentile of a log-normal demand level with sigma {a.sigma:.2f} ({case.evidence}).",
                ),
                LaunchInput(
                    name="unit_cost_change",
                    value=to_bp(policy.low_case_cost_change),
                    unit=Unit.BP,
                    origin=POLICY_ORIGIN[sources["low_case_cost_change"]],
                    basis="Supplier cost rises.",
                ),
                LaunchInput(
                    name="extra_discount",
                    value=to_bp(policy.low_case_extra_discount),
                    unit=Unit.BP,
                    origin=POLICY_ORIGIN[sources["low_case_extra_discount"]],
                    basis="Deeper discounting to move stock.",
                ),
                LaunchInput(
                    name="return_multiplier",
                    value=to_bp(policy.low_case_return_multiplier),
                    unit=Unit.BP,
                    origin=POLICY_ORIGIN[sources["low_case_return_multiplier"]],
                    basis="More returns than planned.",
                ),
            ]
        return [
            LaunchInput(
                name="demand_multiplier",
                value=to_bp(highq),
                unit=Unit.BP,
                origin=Origin.ESTIMATE,
                basis=f"90th percentile of a log-normal demand level with sigma {a.sigma:.2f}.",
            )
        ]

    scenarios = [
        ScenarioResult(
            name=n,
            assumptions=scen_assumptions(n),
            figures=a.scenario_figures(r),
            months=a.months(r),
        )
        for n, r in (("low", low), ("base", base), ("high", high))
    ]

    # Simulation summary ------------------------------------------------------------------
    mc = proposed.mc
    p_loss = float((mc.profit < 0).mean())
    p_pay = float((mc.payback_month <= policy.breakeven_horizon_months).mean())
    sim_inputs = [
        value_input("runs", runs, Unit.COUNT, Origin.ESTIMATE),
        value_input("seed", seed, Unit.COUNT, Origin.ESTIMATE),
    ]
    sim_figs = [
        bp_figure(
            "launch.p_loss",
            "Chance of a loss over the horizon (model-based)",
            p_loss,
            inputs=sim_inputs,
        ),
        bp_figure(
            "launch.p_payback_within_horizon",
            f"Chance of paying back within {policy.breakeven_horizon_months} months (model-based)",
            p_pay,
            inputs=sim_inputs,
        ),
        money_figure(
            "launch.expected_profit",
            "Average profit across simulated outcomes",
            mc.profit.mean(),
            cur,
            inputs=sim_inputs,
        ),
        money_figure(
            "launch.profit_p10",
            "Profit, pessimistic (10th percentile)",
            np.quantile(mc.profit, 0.1),
            cur,
        ),
        money_figure("launch.profit_p50", "Profit, median", np.quantile(mc.profit, 0.5), cur),
        money_figure(
            "launch.profit_p90",
            "Profit, optimistic (90th percentile)",
            np.quantile(mc.profit, 0.9),
            cur,
        ),
        money_figure(
            "launch.peak_cash_p90",
            "Peak cash need, 90th percentile",
            np.quantile(mc.peak_cash, 0.9),
            cur,
        ),
    ]
    if policy.target_profit_minor is not None:
        sim_figs.append(
            bp_figure(
                "launch.p_target_profit",
                "Chance of reaching your target profit (model-based)",
                float((mc.profit >= policy.target_profit_minor).mean()),
                inputs=sim_inputs,
            )
        )
    counts, edges = np.histogram(mc.profit, bins=12)
    simulation = Simulation(
        runs=runs,
        seed=seed,
        demand_evidence=case.evidence,
        figures=sim_figs,
        profit_histogram=[
            HistogramBin(lower=a.m(edges[i]), upper=a.m(edges[i + 1]), count=int(counts[i]))
            for i in range(len(counts))
        ],
    )

    # Rules and label ---------------------------------------------------------------------
    checks = a.rules(proposed, econ)
    pilot_checks = a.rules(pilot, econ)

    # Levers ------------------------------------------------------------------------------
    base_profit, base_peak = base.profit[0], base.peak_cash[0]
    base_ploss_small = float((a.det(proposed_run, a.lever_shocks).profit < 0).mean())

    def lever(
        lever_id: str, change, run: _Run, feasibility: str, urgency: str
    ) -> tuple[Lever, bool]:
        out = _Outcome(a.det(run), a.det(run, a.lever_shocks))
        passes = a.hard_pass(a.rules(out, run.econ))
        be_new = monthly_break_even_units(run.econ)
        figs = [
            money_figure(
                "launch.lever.delta_profit",
                "Change in horizon profit",
                out.det.profit[0] - base_profit,
                cur,
            ),
            money_figure(
                "launch.lever.delta_peak_cash",
                "Change in peak cash need",
                out.det.peak_cash[0] - base_peak,
                cur,
            ),
            value_figure(
                "launch.lever.delta_p_loss",
                "Change in chance of a loss",
                to_bp(float((out.mc.profit < 0).mean()) - base_ploss_small),
                Unit.BP,
            ),
        ]
        if be_new is not None and be_units is not None:
            figs.append(
                value_figure(
                    "launch.lever.delta_break_even_units",
                    "Change in monthly break-even units",
                    be_new - be_units,
                    Unit.UNITS,
                )
            )
        return Lever(
            lever_id=lever_id,
            change=change,
            feasibility=feasibility,
            urgency=urgency,
            figures=figs,
            fixes_label=passes,
            rank=0,
        ), passes

    candidates = []
    for pct in (0.05, 0.10):
        e2 = econ.with_changes(unit_cost=econ.unit_cost * (1 - pct))
        candidates.append(
            lever(
                f"negotiate_supplier_{int(pct * 100)}pct",
                bp_input("unit_cost_change", -pct, Origin.ESTIMATE),
                a.make_run(econ=e2),
                "medium",
                "before_order",
            )
        )
    for pct in (0.05, 0.10, -0.05):
        e2 = econ.with_changes(price=econ.price * (1 + pct))
        planned2 = case.profile.monthly(price=e2.price, elasticity=a.elasticity)
        candidates.append(
            lever(
                f"price_{'up' if pct > 0 else 'down'}_{int(abs(pct) * 100)}pct",
                bp_input("price_change", pct, Origin.ESTIMATE),
                a.make_run(econ=e2, planned=planned2),
                "medium",
                "before_launch",
            )
        )
    candidates.append(
        lever(
            "pilot_order_first",
            value_input(
                "initial_order_units", pilot_run.plan.initial_order, Unit.UNITS, Origin.ESTIMATE
            ),
            pilot_run,
            "high",
            "before_order",
        )
    )
    if econ.freight_per_unit + econ.packaging_per_unit > 0:
        e2 = econ.with_changes(
            freight_per_unit=econ.freight_per_unit * 0.8,
            packaging_per_unit=econ.packaging_per_unit * 0.8,
        )
        candidates.append(
            lever(
                "cut_freight_packaging_20pct",
                bp_input("freight_packaging_change", -0.2, Origin.ESTIMATE),
                a.make_run(econ=e2),
                "medium",
                "before_order",
            )
        )
    weight = {"high": 1.0, "medium": 0.7, "low": 0.4}

    def score(lv: Lever) -> float:
        return lv.figures[0].money.minor * weight[lv.feasibility] - 0.25 * lv.figures[1].money.minor

    useful = [
        lv for lv, _ in candidates if lv.figures[0].money.minor > 0 or lv.figures[1].money.minor < 0
    ]
    useful.sort(key=score, reverse=True)
    levers = [lv.model_copy(update={"rank": i + 1}) for i, lv in enumerate(useful)]

    # Label -------------------------------------------------------------------------------
    blocking = [g for g in case.gaps if g.blocking]
    reasons: list[str] = []
    # Levers 'fix' the label only when the proposal currently fails a hard rule.
    fixes = [] if a.hard_pass(checks) else [lv.lever_id for lv, ok in candidates if ok]
    if blocking:
        label, plan_choice = "HOLD", "none"
        reasons.append("blocking_inputs_missing")
    elif a.hard_pass(checks):
        if all(c.passed for c in checks):
            label, plan_choice = "LAUNCH", "proposed"
        else:
            label, plan_choice = "PILOT_FIRST", "pilot"
            reasons += [f"soft_rule_failed:{c.rule_id}" for c in checks if not c.passed]
    elif a.hard_pass(pilot_checks):
        label, plan_choice = "PILOT_FIRST", "pilot"
        reasons += [f"proposed_fails:{c.rule_id}" for c in checks if c.hard and not c.passed]
        reasons.append("pilot_order_passes_hard_rules")
    elif fixes:
        label, plan_choice = "REVISE", "none"
        reasons += [f"hard_rule_failed:{c.rule_id}" for c in checks if c.hard and not c.passed]
    else:
        label, plan_choice = "NOT_RECOMMENDED", "none"
        reasons += [f"hard_rule_failed:{c.rule_id}" for c in checks if c.hard and not c.passed]
        reasons.append("no_single_lever_fixes")
    recommendation = Recommendation(
        label=label,
        plan=plan_choice,
        rule_trace=checks,
        reason_codes=reasons,
        levers_that_fix=fixes,
    )

    # Sensitivity and unviable thresholds -------------------------------------------------
    swing = policy.sensitivity_swing

    def profit_of(run: _Run) -> float:
        return float(a.det(run).profit[0])

    drivers: dict[str, Callable[[float], _Run]] = {
        "demand": lambda k: a.make_run(
            realized=a.planned * k, initial=proposed_run.plan.initial_order
        ),
        "selling_price": lambda k: a.make_run(
            econ=econ.with_changes(price=econ.price * k), initial=proposed_run.plan.initial_order
        ),
        "unit_cost": lambda k: a.make_run(
            econ=econ.with_changes(unit_cost=econ.unit_cost * k),
            initial=proposed_run.plan.initial_order,
        ),
        "marketing": lambda k: a.make_run(
            econ=econ.with_changes(marketing_monthly=econ.marketing_monthly * k),
            initial=proposed_run.plan.initial_order,
        ),
        "return_rate": lambda k: a.make_run(
            econ=econ.with_changes(return_rate=min(0.95, econ.return_rate * k)),
            initial=proposed_run.plan.initial_order,
        ),
    }
    sens = []
    for name, build in drivers.items():
        lo_p, hi_p = profit_of(build(1 - swing)), profit_of(build(1 + swing))
        sens.append((name, lo_p, hi_p))
    sens.sort(key=lambda t: abs(t[2] - t[1]), reverse=True)
    sensitivity = [
        SensitivityRow(
            driver=n,
            swing_bp=to_bp(swing),
            profit_low=a.m(lo_p),
            profit_high=a.m(hi_p),
            spread=a.m(abs(hi_p - lo_p)),
            rank=i + 1,
        )
        for i, (n, lo_p, hi_p) in enumerate(sens)
    ]

    unviable = []
    for name, current_fig, metric, scale in (
        (
            "demand",
            value_figure("launch.demand_multiplier", "Demand as planned", 10_000, Unit.BP),
            "launch.break_even_demand_multiplier",
            None,
        ),
        (
            "unit_cost",
            money_figure("launch.unit_cost", "Unit cost", econ.unit_cost, cur),
            "launch.break_even_unit_cost",
            econ.unit_cost,
        ),
        (
            "selling_price",
            money_figure("launch.price", "Selling price", econ.price, cur),
            "launch.break_even_selling_price",
            econ.price,
        ),
    ):
        k = _bisect(
            lambda k, b=drivers[name]: profit_of(b(k)),
            0.0 if name != "selling_price" else 0.05,
            10.0,
        )
        if k is None:
            thr = Figure(
                metric_id=metric,
                label="Value at which horizon profit is zero",
                unit=current_fig.unit,
                status="not_applicable",
                note="profit does not cross zero in the searched range",
            )
        elif scale is None:
            thr = value_figure(
                metric, "Demand multiplier at which horizon profit is zero", to_bp(k), Unit.BP
            )
        else:
            thr = money_figure(metric, "Value at which horizon profit is zero", scale * k, cur)
        unviable.append(
            UnviableThreshold(
                driver=name,
                current=current_fig,
                threshold=thr,
                headroom_bp=None if k is None else to_bp(abs(k - 1)),
            )
        )

    # Pricing -----------------------------------------------------------------------------
    grid_prices = sorted(
        {round(econ.price * f / 5000) * 5000 for f in (0.8, 0.9, 1.0, 1.1, 1.2, 1.3)}
    )
    grid = []
    medium_profit: dict[float, float] = {}
    high_sens_profit: dict[float, float] = {}
    for price in grid_prices:
        e2 = econ.with_changes(price=float(price))
        outcomes = []
        for scen, el in policy.elasticity_scenarios.items():
            planned2 = case.profile.monthly(price=float(price), elasticity=el)
            r = a.det(a.make_run(econ=e2, planned=planned2, initial=a.standard_qty(planned2, e2)))
            outcomes.append(
                PriceOutcome(
                    elasticity_scenario=scen,
                    units=round_minor(r.sold[0].sum()),
                    profit=a.m(r.profit[0]),
                )
            )
            if scen == "medium_sensitivity":
                medium_profit[price] = r.profit[0]
            if scen == "high_sensitivity":
                high_sens_profit[price] = r.profit[0]
        margin = unit_economics(e2).contribution_margin
        grid.append(
            PricePoint(
                price=a.m(price),
                contribution_margin_bp=to_bp(margin) if margin is not None else None,
                outcomes=outcomes,
            )
        )
    best = max(medium_profit.values()) if medium_profit else 0
    ok_prices = [
        p
        for p in grid_prices
        if (unit_economics(econ.with_changes(price=float(p))).contribution_margin or 0)
        >= policy.min_contribution_margin
        and medium_profit[p] >= 0.9 * best
        and high_sens_profit.get(p, 0) > 0
    ]
    comp = sorted(case.competitor_prices)
    competitor_range = None
    if comp:
        vals = [c[0] for c in comp]
        origin = (
            "market_observed" if all(c[1] == "market_observed" for c in comp) else "user_provided"
        )
        competitor_range = CompetitorRange(
            low=a.m(min(vals)),
            high=a.m(max(vals)),
            median=a.m(float(np.median(vals))),
            count=len(vals),
            origin=origin,
        )
    pricing = Pricing(
        figures=[
            money_figure("launch.price", "Proposed selling price", econ.price, cur),
            money_figure(
                "launch.break_even_price",
                "Price at which each unit just breaks even",
                ue.break_even_price,
                cur,
            )
            if ue.break_even_price is not None
            else Figure(
                metric_id="launch.break_even_price",
                label="Break-even price",
                unit=Unit.MINOR,
                status="not_applicable",
                note="fees and refunds exceed revenue at any price",
            ),
            money_figure(
                "launch.price_for_min_margin",
                "Price that reaches your minimum margin",
                min_margin_price,
                cur,
            )
            if min_margin_price is not None
            else Figure(
                metric_id="launch.price_for_min_margin",
                label="Price for minimum margin",
                unit=Unit.MINOR,
                status="not_applicable",
                note="no price reaches the minimum margin",
            ),
        ],
        competitor_range=competitor_range,
        recommended_range=PriceRange(low=a.m(min(ok_prices)), high=a.m(max(ok_prices)))
        if ok_prices
        else None,
        elasticity_origin=case.elasticity_origin,
        grid=grid,
        note_codes=["elasticity_from_scenarios_not_estimated"]
        if case.elasticity_origin != "ledger_derived"
        else [],
    )

    # Inventory plan and plan summaries ---------------------------------------------------
    landed = econ.landed_cost()
    cap_units = (
        math.floor(case.available_capital / landed)
        if case.available_capital and landed > 0
        else None
    )
    inv_figs = [
        value_figure(
            "launch.initial_order_standard",
            "Initial order to last until the first reorder arrives",
            a.standard_qty(a.planned, econ),
            Unit.UNITS,
        ),
        value_figure(
            "launch.initial_order_pilot",
            f"Pilot order ({policy.pilot_cover_months} month of base demand)",
            pilot_run.plan.initial_order,
            Unit.UNITS,
        ),
        value_figure(
            "launch.lead_months",
            "Supplier lead time",
            a.lead_months,
            Unit.MONTHS,
            inputs=[value_input("lead_time_days", case.lead_days, Unit.DAYS, Origin.USER)],
        ),
        value_figure("launch.moq", "Minimum order quantity", case.moq, Unit.UNITS),
    ]
    flags = []
    if cap_units is not None:
        inv_figs.append(
            value_figure(
                "launch.capital_cap_units",
                "Units the capital set aside can buy",
                cap_units,
                Unit.UNITS,
            )
        )
        if proposed_run.plan.initial_order > cap_units:
            flags.append("initial_order_exceeds_capital")
    if (
        case.storage_capacity is not None
        and proposed_run.plan.initial_order > case.storage_capacity
    ):
        flags.append("initial_order_exceeds_storage")
    if case.moq > a.standard_qty(a.planned, econ) and case.moq > 0:
        flags.append("moq_above_demand_need")

    plans = [
        PlanSummary(
            plan="proposed",
            initial_order_units=proposed_run.plan.initial_order,
            figures=a.scenario_figures(base),
        ),
        PlanSummary(
            plan="pilot",
            initial_order_units=pilot_run.plan.initial_order,
            figures=a.scenario_figures(pilot.det, prefix="launch.pilot"),
        ),
    ]

    # What-ifs ----------------------------------------------------------------------------
    what_ifs = []
    for w in case.what_ifs or DEFAULT_WHAT_IFS:
        e2 = econ.with_changes(
            unit_cost=econ.unit_cost * (1 + w.unit_cost_change_bp / 10_000),
            price=econ.price * (1 + w.price_change_bp / 10_000),
            marketing_monthly=econ.marketing_monthly * w.marketing_multiplier_bp / 10_000,
            discount_rate=min(0.95, econ.discount_rate + w.extra_discount_bp / 10_000),
            unsellable_share=w.unsold_share_bp / 10_000,
            receivable_days=float(w.receivable_days)
            if w.receivable_days is not None
            else econ.receivable_days,
            return_rate=w.return_rate_bp / 10_000
            if w.return_rate_bp is not None
            else econ.return_rate,
        )
        if w.fx_change_bp:
            e2 = replace(
                e2,
                unit_cost=e2.unit_cost * (1 + econ.imported_cost_share * w.fx_change_bp / 10_000),
            )
        planned2 = (
            case.profile.monthly(price=e2.price, elasticity=a.elasticity)
            if (w.price_change_bp and w.apply_elasticity)
            else a.planned
        )
        realized2 = planned2 * (1 + w.demand_change_bp / 10_000)
        initial2 = (
            w.initial_order_units
            if w.initial_order_units is not None
            else proposed_run.plan.initial_order
        )
        run2 = a.make_run(
            econ=e2,
            planned=planned2,
            realized=realized2,
            initial=initial2,
            first_arrival=1 + lead_months_from_days(w.delivery_delay_days),
        )
        out2 = _Outcome(a.det(run2), a.det(run2, a.lever_shocks))
        what_ifs.append(
            WhatIfResult(
                what_if=w,
                figures=[
                    money_figure(
                        "launch.whatif.horizon_profit",
                        "Profit over the horizon",
                        out2.det.profit[0],
                        cur,
                    ),
                    money_figure(
                        "launch.whatif.delta_profit",
                        "Change against the base case",
                        out2.det.profit[0] - base_profit,
                        cur,
                    ),
                    money_figure(
                        "launch.whatif.peak_cash", "Peak cash need", out2.det.peak_cash[0], cur
                    ),
                    bp_figure(
                        "launch.whatif.p_loss",
                        "Chance of a loss (model-based)",
                        float((out2.mc.profit < 0).mean()),
                        inputs=[
                            value_input("runs", min(runs, LEVER_RUNS), Unit.COUNT, Origin.ESTIMATE)
                        ],
                    ),
                ],
            )
        )

    # Headline, explain and findings ------------------------------------------------------
    by_id = {f.metric_id: f for f in ue_figs + sim_figs + scenarios[1].figures}
    headline = [
        by_id[k]
        for k in (
            "launch.contribution_per_unit",
            "launch.contribution_margin",
            "launch.monthly_break_even_units",
            "launch.horizon_profit",
            "launch.peak_cash",
            "launch.payback_month",
            "launch.p_payback_within_horizon",
            "launch.p_loss",
        )
    ]
    pilot_worst = float(np.quantile(pilot.mc.profit, 0.1))
    max_at_risk = money_figure(
        "launch.max_amount_at_risk",
        "Most you could lose in a bad case (pilot, 10th percentile)",
        max(0.0, -pilot_worst),
        cur,
        formula="max(0, -p10 of pilot profit)",
        inputs=[value_input("runs", runs, Unit.COUNT, Origin.ESTIMATE)],
    )
    strongest = [
        i.name
        for i in case.inputs
        if i.origin in (Origin.USER, Origin.LEDGER, Origin.MARKET) and not i.needs_verification
    ]
    explain = Explain(
        strongest_evidence=strongest[:5],
        main_risks=[s.driver for s in sensitivity[:3]],
        safest_test="pilot",
        best_lever=levers[0].lever_id if levers else None,
        max_amount_at_risk=max_at_risk,
    )

    findings = _findings(a, case, run_id, generated_at, ue, base, checks, be_units, label)

    policy_thresholds = [
        bp_threshold(
            "min_contribution_margin",
            policy.min_contribution_margin,
            POLICY_ORIGIN[sources["min_contribution_margin"]],
            ">=",
        ),
        Threshold(
            name="breakeven_horizon_months",
            value=policy.breakeven_horizon_months,
            unit=Unit.MONTHS,
            origin=POLICY_ORIGIN[sources["breakeven_horizon_months"]],
            comparison="<=",
        ),
        bp_threshold(
            "launch_min_prob_breakeven",
            policy.launch_min_prob_breakeven,
            POLICY_ORIGIN[sources["launch_min_prob_breakeven"]],
            ">=",
        ),
        bp_threshold(
            "max_loss_probability",
            policy.max_loss_probability,
            POLICY_ORIGIN[sources["max_loss_probability"]],
            "<=",
        ),
        bp_threshold(
            "cost_of_capital_annual",
            policy.cost_of_capital_annual,
            POLICY_ORIGIN[sources["cost_of_capital_annual"]],
            ">=",
        ),
        bp_threshold(
            "unsold_recovery_rate",
            econ.unsold_recovery_rate,
            POLICY_ORIGIN[sources["unsold_recovery_rate"]],
            ">=",
        ),
    ]

    limitations = [
        "This product has no sales history of its own; demand is modelled from comparable products and stated assumptions, not trained on the product's own data.",
        "Probabilities come from a simulation of the stated assumptions. They are not calibrated real-world probabilities.",
        "Demand response to marketing spend is not modelled; use a what-if with a demand change to explore it.",
    ]
    if case.elasticity_origin != "ledger_derived":
        limitations.append(
            "Price elasticity could not be estimated from the ledger, so pricing uses three explicit elasticity scenarios."
        )

    return LaunchLabResponse(
        mode=mode,
        tenant_id=case.tenant_id,
        generated_at=generated_at,
        run_id=run_id,
        inputs_hash=inputs_hash,
        engine_version=ENGINE_VERSION,
        currency=cur,
        as_of=case.as_of,
        product=case.product,
        recommendation=recommendation,
        headline=headline,
        inputs=case.inputs,
        data_gaps=case.gaps,
        policy=policy_thresholds,
        unit_economics=ue_figs,
        cost_lines=cost_lines,
        scenarios=scenarios,
        simulation=simulation,
        sensitivity=sensitivity,
        unviable_thresholds=unviable,
        pricing=pricing,
        inventory_plan=InventoryPlan(figures=inv_figs, flags=flags),
        plans=plans,
        levers=levers,
        what_ifs=what_ifs,
        explain=explain,
        findings=findings,
        limitations=limitations,
    )


def _findings(
    a: _Analysis,
    case: ResolvedCase,
    run_id: str,
    generated_at: datetime,
    ue,
    base: SimResult,
    checks: list[RuleCheck],
    be_units: float | None,
    label: str,
) -> list[Finding]:
    period = Period(start=case.profile.launch_month, end=add_months(case.profile.launch_month, a.H))
    ev = [Evidence(kind="forecast_run", ref=run_id)]
    act = [Action(label="Open Launch Lab", route=f"/launch-lab?run={run_id}")]
    out = []

    def finding(
        kind: str, severity: str, title: str, stake: float, figures: list[Figure]
    ) -> Finding:
        return Finding(
            id=stable_id("fnd", kind, case.tenant_id, case.product.name, run_id),
            source="launch_lab",
            severity=severity,
            title=title,
            money_at_stake=a.m(max(0.0, stake)),
            evidence=ev,
            actions=act,
            type=kind,
            period=period,
            created_at=generated_at,
            dedupe_key=f"{kind}:{case.tenant_id}:{case.product.name.lower()}",
            figures=figures,
        )

    if ue.contribution_per_unit <= 0:
        out.append(
            finding(
                "launch_negative_contribution",
                "high",
                f"{case.product.name} loses money on every unit at this price",
                -ue.contribution_per_unit * float(base.sold[0].sum()),
                [],
            )
        )
    failed = {c.rule_id for c in checks if c.hard and not c.passed}
    if "LL-05" in failed and be_units is not None:
        out.append(
            finding(
                "launch_break_even_above_demand",
                "high",
                f"{case.product.name} needs {round_minor(be_units)} sales a month to break even, more than plausible demand",
                base.peak_cash[0],
                [],
            )
        )
    if "LL-06" in failed or "LL-07" in failed:
        out.append(
            finding(
                "launch_cash_requirement_exceeds_limit",
                "high",
                f"Launching {case.product.name} as planned needs more cash than you set aside",
                base.peak_cash[0] - (case.available_capital or 0),
                [],
            )
        )
    if base.writedown[0] > 0.1 * max(1.0, base.revenue[0].sum()):
        out.append(
            finding(
                "launch_unsold_inventory_risk",
                "medium",
                f"Unsold {case.product.name} stock could cost you at the end of the season",
                base.writedown[0],
                [],
            )
        )
    return out
