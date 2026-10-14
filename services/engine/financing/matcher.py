"""Financing-option matcher (task Y10).

For each catalogue option in the tenant's country: test eligibility with the rulebook grammar,
price it at the low, mid and high ends of its cited ranges (effective annual cost = IRR of the
borrower's own cash flows, fees included), test debt-service cover after borrowing in the base
and downside cases with engine.analysis.coverage, and rank. Anything the catalogue leaves null
is reported as insufficient data, never guessed.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from engine.analysis import rulebook as rb
from engine.analysis.coverage import Coverage, dscr_forward, max_principal_at_dscr
from engine.decisions.tvm import annual_rate, irr
from engine.financing.business import BusinessFigures
from engine.financing.catalogue import (
    catalogue_as_of,
    field_verification,
    load_catalogue,
    options_for,
    reference_rate,
)
from engine.financing.conditions import evaluate, lookup_path
from engine.financing.schemas import (
    CatalogueRef,
    FinancingMatchRequest,
    FinancingMatchResponse,
    FinancingOption,
)
from engine.forecast._contracts import Figure, FigureInput, Money, Origin, Threshold, Unit
from engine.forecast.figures import (
    InsufficientData,
    RuleCheck,
    money_figure,
    money_input,
    value_figure,
    value_input,
)

ENGINE_VERSION = "financing/0.1.0"
VERIFICATION_ORIGIN = {
    "primary": Origin.MARKET,
    "secondary": Origin.MARKET,
    "assumption": Origin.ASSUMPTION,
    "unverified": Origin.ASSUMPTION,
}
DEBT_TYPES = {
    "term_loan",
    "running_finance",
    "invoice_discounting",
    "equipment_lease",
    "refinance_scheme",
    "microfinance",
}


@dataclass(frozen=True)
class Pricing:
    rate_bp: int | None  # nominal annual
    fee_bp: int
    fee_known: bool
    inputs: tuple[FigureInput, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class Schedule:
    flows: list[float]  # month 0..n, borrower's view
    first_payment: float
    service_12m: float  # debt service counted for DSCR in the first 12 months
    payments_first_3m: float


def _mid(lo: int | None, hi: int | None) -> int | None:
    if lo is None or hi is None:
        return None
    return (lo + hi) // 2


def _pick(rng: dict | None, end: str) -> int | None:
    if not isinstance(rng, dict):
        return None
    lo, hi = rng.get("low"), rng.get("high")
    return {"low": lo, "high": hi, "mid": _mid(lo, hi)}[end]


def price(option: dict[str, Any], end: str, cur: str, *, rate_shock_bp: int = 0) -> Pricing:
    p = option.get("pricing") or {}
    inputs: list[FigureInput] = []
    missing: list[str] = []
    rate: int | None = None
    kind = p.get("rate_type")
    if kind == "floating":
        ref = reference_rate(p.get("reference"))
        spread = _pick(p.get("spread_bp"), end)
        if ref is None or ref.get("value_bp") is None:
            missing.append("a cited reference lending rate")
        if spread is None:
            missing.append("a quoted spread (term sheet)")
        if not missing:
            rate = ref["value_bp"] + spread + rate_shock_bp
            inputs.append(
                FigureInput(
                    name=f"reference_rate:{p['reference']}",
                    value=ref["value_bp"],
                    unit=Unit.BP,
                    origin=VERIFICATION_ORIGIN.get(
                        ref.get("verification", "unverified"), Origin.ASSUMPTION
                    ),
                    ref=ref.get("source_id"),
                )
            )
            inputs.append(
                FigureInput(
                    name=f"spread_{end}",
                    value=spread,
                    unit=Unit.BP,
                    origin=VERIFICATION_ORIGIN[field_verification(option, p.get("spread_bp"))],
                    ref=option["option_id"],
                )
            )
    elif kind == "fixed":
        rng = p.get("fixed_rate_bp") or {}
        rate = _pick(rng, end)
        if rate is None and end != "mid" and rng.get("high") is not None and rng.get("low") is None:
            rate = rng["high"]  # "up to X": only the ceiling is cited
        if rate is None and rng.get("high") is not None:
            rate = rng["high"]
        if rate is None:
            missing.append("a quoted rate (term sheet)")
        else:
            rate += rate_shock_bp if p.get("reference") else 0
            inputs.append(
                FigureInput(
                    name=f"fixed_rate_{end}",
                    value=rate,
                    unit=Unit.BP,
                    origin=VERIFICATION_ORIGIN[field_verification(option, rng)],
                    ref=option["option_id"],
                )
            )
    fee = _pick(p.get("fees_bp"), end)
    fee_known = fee is not None
    if fee_known:
        inputs.append(
            FigureInput(
                name=f"fees_{end}",
                value=fee,
                unit=Unit.BP,
                origin=VERIFICATION_ORIGIN[field_verification(option, p.get("fees_bp"))],
                ref=option["option_id"],
            )
        )
    return Pricing(rate, fee or 0, fee_known, tuple(inputs), tuple(missing))


def schedule(
    option: dict[str, Any], amount: float, rate_bp: int, fee_bp: int, tenor: int
) -> Schedule:
    """Borrower's monthly cash flows. Nominal annual rate, monthly accrual."""
    rep = option.get("repayment") or {}
    style = rep.get("style")
    k = max(1, int(rep.get("frequency_months") or 1))
    grace = int(((rep.get("grace_months") or {}).get("low")) or 0)
    i = rate_bp / 10_000 / 12
    fee_basis = (option.get("pricing") or {}).get("fee_basis", "upfront")
    flows = [0.0] * (tenor + 1)
    fee = amount * fee_bp / 10_000
    flows[0] += amount
    if fee_basis == "annual":
        for t in range(0, tenor, 12):
            flows[t] -= fee
    elif fee_basis == "per_invoice":
        for t in range(0, tenor, k):
            flows[t] -= fee
    else:
        flows[0] -= fee

    balance = amount
    interest_only_12m = 0.0
    if style in ("annuity", "equal_principal"):
        for t in range(1, min(grace, tenor) + 1):
            flows[t] -= balance * i
        payments = max(1, (tenor - grace) // k)
        period_rate = (1 + i) ** k - 1
        annuity = (
            amount * period_rate / (1 - (1 + period_rate) ** -payments)
            if period_rate > 0
            else amount / payments
        )
        for n in range(1, payments + 1):
            t = grace + n * k
            if t > tenor:
                break
            interest = balance * period_rate
            principal = (annuity - interest) if style == "annuity" else amount / payments
            principal = min(principal, balance) if n < payments else balance
            flows[t] -= interest + principal
            balance -= principal
    elif style == "revolving":
        for t in range(1, tenor + 1):
            flows[t] -= amount * i
            interest_only_12m += amount * i if t <= 12 else 0
        flows[tenor] -= amount
    elif style == "bullet":
        flows[tenor] -= amount * (1 + i * tenor)
    payments_list = [-f for f in flows[1:] if f < 0]
    first = payments_list[0] if payments_list else 0.0
    service = interest_only_12m if style == "revolving" else sum(-f for f in flows[1:13] if f < 0)
    return Schedule(flows, first, service, sum(-f for f in flows[1:4] if f < 0))


def _tenor(option: dict[str, Any], preferred: int | None) -> int:
    t = option.get("tenor_months") or {}
    lo, hi = t.get("min"), t.get("max")
    chosen = preferred or hi or lo or 12
    if lo is not None:
        chosen = max(chosen, lo)
    if hi is not None:
        chosen = min(chosen, hi)
    return int(chosen)


def _eac(flows: list[float]) -> float | None:
    r = irr(flows)
    return annual_rate(r.rate) if r.valid and r.rate > -0.99 else None


def _coverage_figure(
    metric_id: str, label: str, cov: Coverage | None, inputs: list[FigureInput], threshold_id: str
) -> Figure:
    if cov is None or cov.value_bp is None:
        return Figure(
            metric_id=metric_id,
            label=label,
            unit=Unit.BP,
            status="insufficient_data",
            missing=["forecast EBITDA (engine.analysis)"]
            if cov is None
            else [cov.reason or "debt service"],
        )
    limit = rb.value_bp(threshold_id)
    return Figure(
        metric_id=metric_id,
        label=label,
        value=cov.value_bp,
        unit=Unit.BP,
        formula="ebitda_next_12m / (existing + new debt service, next 12 months)",
        inputs=inputs,
        thresholds=[
            Threshold(
                name=threshold_id,
                value=limit,
                unit=Unit.BP,
                origin=Origin.RULEBOOK,
                comparison=">=",
                passed=cov.value_bp >= limit,
            )
        ],
        source_refs=["engine.analysis.coverage.dscr_forward"],
    )


def match_financing(
    req: FinancingMatchRequest,
    biz: BusinessFigures,
    *,
    tenant_id: str,
    as_of: date,
    mode: str,
    generated_at: datetime,
) -> FinancingMatchResponse:
    cur = biz.currency
    if req.amount.currency != cur:
        raise ValueError(f"amount must be in {cur}")
    amount = req.amount.minor
    cat = load_catalogue()
    down = rb.threshold("T-DEC-DOWN-01")
    shock = (down.get("country_overrides") or {}).get(biz.country or "", {}).get(
        "downside", {}
    ).get("rate_change_bp") or down["scenarios"]["downside"]["rate_change_bp"]
    revenue_change = down["scenarios"]["downside"]["revenue_change_bp"]
    ebitda = biz.ebitda_next_12m_minor
    ebitda_down = round(ebitda * (1 + revenue_change / 10_000)) if ebitda is not None else None

    stub_inputs = [
        money_input(
            "ebitda_next_12m",
            ebitda or 0,
            cur,
            Origin.STUB,
            ref="bank statement: operating cash flow before debt service, annualised",
        ),
        money_input(
            "existing_debt_service_12m",
            biz.existing_service_12m_minor,
            cur,
            Origin.LEDGER,
            ref=biz.existing_service_basis,
        ),
    ]
    down_inputs = [
        *stub_inputs,
        value_input(
            "downside_revenue_change", revenue_change, Unit.BP, Origin.RULEBOOK, ref="T-DEC-DOWN-01"
        ),
        value_input("downside_rate_shock", shock, Unit.BP, Origin.RULEBOOK, ref="T-DEC-DOWN-01"),
    ]

    profile = req.profile.model_dump()
    if profile.get("has_b2b_receivables") is None:
        profile["has_b2b_receivables"] = biz.has_b2b_receivables
    profile["country"] = biz.country
    inputs_tree = {
        "request": {
            "purpose": req.purpose,
            "amount_minor": amount,
            "tenor_months": req.preferred_tenor_months,
            "is_new_borrower_of_bank": req.is_new_borrower_of_bank,
        },
        "profile": profile,
    }
    inputs = lookup_path(inputs_tree)

    results: list[tuple[FinancingOption, tuple]] = []
    gaps: dict[str, InsufficientData] = {}
    for opt in options_for(biz.country or "", cat):
        oid, otype = opt["option_id"], opt["type"]
        tenor = _tenor(opt, req.preferred_tenor_months)
        is_debt = otype in DEBT_TYPES
        mid = price(opt, "mid", cur)
        figures: list[Figure] = []
        checks: list[RuleCheck] = []
        hard_false = hard_none = dscr_fail = False
        missing_inputs: set[str] = set()

        # Cost at the three ends of the cited ranges
        eac: dict[str, float | None] = {}
        sched_mid = None
        for end in ("low", "mid", "high"):
            pr = price(opt, end, cur)
            if pr.rate_bp is None or not is_debt:
                eac[end] = None
                continue
            sch = schedule(opt, amount, pr.rate_bp, pr.fee_bp, tenor)
            eac[end] = _eac(sch.flows)
            if end == "mid":
                sched_mid = sch
            figures.append(
                Figure(
                    metric_id=f"financing.effective_annual_cost.{end}",
                    label=f"Effective annual cost ({end} end of the cited range)",
                    value=round(eac[end] * 10_000),
                    unit=Unit.BP,
                    formula="annualise(IRR of the borrower's monthly cash flows, fees included)",
                    inputs=[
                        *list(pr.inputs),
                        value_input("tenor_months", tenor, Unit.MONTHS, Origin.ESTIMATE),
                    ],
                    source_refs=list(opt.get("source_ids", [])),
                    note=None if pr.fee_known else "fees not cited: cost shown before fees",
                )
                if eac[end] is not None
                else Figure(
                    metric_id=f"financing.effective_annual_cost.{end}",
                    label="Effective annual cost",
                    unit=Unit.BP,
                    status="not_applicable",
                    note="no unique IRR for these cash flows",
                )
            )
        cost_unknown = False
        if opt["pricing"].get("rate_type") == "discount":
            if req.supplier_discount:
                d = req.supplier_discount
                ear = (1 / (1 - d.discount_bp / 10_000)) ** (365 / (d.net_days - d.within_days)) - 1
                eac = {"low": ear, "mid": ear, "high": ear}
                figures.append(
                    Figure(
                        metric_id="financing.effective_annual_cost.mid",
                        label="Cost of the early-payment discount given up",
                        value=round(ear * 10_000),
                        unit=Unit.BP,
                        formula="(1 / (1 - d))^(365 / (N - n)) - 1 (T-DEC-EPD-01)",
                        inputs=[value_input("discount", d.discount_bp, Unit.BP, Origin.USER)],
                        source_refs=opt.get("source_ids", []),
                    )
                )
            else:
                eac = {"low": 0.0, "mid": 0.0, "high": 0.0}
                figures.append(
                    Figure(
                        metric_id="financing.effective_annual_cost.mid",
                        label="Explicit cost of longer supplier terms",
                        value=0,
                        unit=Unit.BP,
                        note="no early-payment discount offered, so no explicit cost",
                        source_refs=opt.get("source_ids", []),
                    )
                )
        elif opt["pricing"].get("rate_type") == "equity":
            tr = opt["pricing"].get("target_return_bp") or {}
            m = _mid(tr.get("low"), tr.get("high"))
            if m is None:
                cost_unknown = True
                figures.append(
                    Figure(
                        metric_id="financing.effective_annual_cost.mid",
                        label="Return the investor expects",
                        unit=Unit.BP,
                        status="insufficient_data",
                        missing=["the investor's terms or a cited equity premium"],
                    )
                )
            else:
                eac = {"low": tr["low"] / 10_000, "mid": m / 10_000, "high": tr["high"] / 10_000}
                figures.append(
                    Figure(
                        metric_id="financing.effective_annual_cost.mid",
                        label="Return the investor expects (cost of equity)",
                        value=m,
                        unit=Unit.BP,
                        inputs=[
                            FigureInput(
                                name="target_return_mid",
                                value=m,
                                unit=Unit.BP,
                                origin=VERIFICATION_ORIGIN[field_verification(opt, tr)],
                                ref=oid,
                            )
                        ],
                        source_refs=opt.get("source_ids", []),
                    )
                )
        elif eac.get("mid") is None:
            cost_unknown = True
            need = ", ".join(mid.missing) or "a quoted rate"
            figures.append(
                Figure(
                    metric_id="financing.effective_annual_cost.mid",
                    label="Effective annual cost",
                    unit=Unit.BP,
                    status="insufficient_data",
                    missing=[need],
                )
            )
            gaps.setdefault(
                oid,
                InsufficientData(
                    need=f"{opt['name']}: {need}",
                    why="The catalogue cites no cost for it, so it is not ranked.",
                    blocking=False,
                    metric_ids=["financing.effective_annual_cost"],
                ),
            )

        # Dilution
        dilution_bp = None
        if opt.get("dilution"):
            if req.pre_money_valuation is not None:
                dilution_bp = round(amount * 10_000 / (req.pre_money_valuation.minor + amount))
                figures.append(
                    value_figure(
                        "financing.dilution",
                        "Share of the business given up",
                        dilution_bp,
                        Unit.BP,
                        formula="amount / (pre_money_valuation + amount)",
                        inputs=[
                            money_input(
                                "pre_money_valuation",
                                req.pre_money_valuation.minor,
                                cur,
                                Origin.USER,
                            )
                        ],
                    )
                )
            else:
                figures.append(
                    Figure(
                        metric_id="financing.dilution",
                        label="Share of the business given up",
                        unit=Unit.BP,
                        status="insufficient_data",
                        missing=["a pre-money valuation"],
                    )
                )

        # Debt-service cover after borrowing
        cov_base = cov_down = None
        if is_debt and sched_mid is not None:
            service_mid = round(sched_mid.service_12m)
            if ebitda is not None:
                cov_base = dscr_forward(ebitda, biz.existing_service_12m_minor, service_mid)
                shocked = price(
                    opt,
                    "mid",
                    cur,
                    rate_shock_bp=shock if opt["pricing"].get("rate_type") == "floating" else 0,
                )
                sch_down = schedule(opt, amount, shocked.rate_bp, shocked.fee_bp, tenor)
                cov_down = dscr_forward(
                    ebitda_down, biz.existing_service_12m_minor, round(sch_down.service_12m)
                )
            figures.append(
                _coverage_figure(
                    "financing.dscr_after",
                    "Debt-service cover after borrowing",
                    cov_base,
                    [
                        *stub_inputs,
                        money_input("new_debt_service_12m", service_mid, cur, Origin.ESTIMATE),
                    ],
                    "T-SOL-DSCR-01",
                )
            )
            figures.append(
                _coverage_figure(
                    "financing.dscr_after_downside",
                    "Debt-service cover after borrowing, downside case",
                    cov_down,
                    down_inputs,
                    "T-SOL-DSCR-02",
                )
            )
            figures.append(
                money_figure(
                    "financing.instalment",
                    "Typical payment (mid rate)",
                    sched_mid.first_payment,
                    cur,
                )
            )
            figures.append(
                money_figure(
                    "financing.total_cost",
                    "Total cost over the term (mid rate)",
                    -sum(sched_mid.flows),
                    cur,
                )
            )
            for cov, tid in ((cov_base, "T-SOL-DSCR-01"), (cov_down, "T-SOL-DSCR-02")):
                if cov is not None and cov.value_bp is not None and cov.value_bp < rb.value_bp(tid):
                    dscr_fail = True
            if biz.cash_lowest_closing_minor is not None:
                low_after = (
                    biz.cash_lowest_closing_minor + sched_mid.flows[0] - sched_mid.payments_first_3m
                )
                figures.append(
                    money_figure(
                        "financing.cash_low_point_after",
                        "Lowest cash in the next 13 weeks after borrowing (approx.)",
                        low_after,
                        cur,
                        formula="Y1 lowest closing + net proceeds - payments in the first 3 months",
                        inputs=[
                            money_input(
                                "lowest_closing_13w",
                                biz.cash_lowest_closing_minor,
                                cur,
                                Origin.FIGURE,
                                ref=biz.forecast_run_id,
                            )
                        ],
                        note="Adds the proceeds to the forecast low point; treat as indicative.",
                    )
                )

        # Eligibility --------------------------------------------------------------------------
        if req.purpose not in opt.get("purposes", []):
            hard_false = True
            checks.append(
                RuleCheck(
                    rule_id=f"{oid}:purpose",
                    description=f"Suits the purpose ({', '.join(opt.get('purposes', []))})",
                    metric_id="request.purpose",
                    threshold=Threshold(
                        name="purpose_matches",
                        value=1,
                        unit=Unit.COUNT,
                        origin=Origin.RULEBOOK,
                        comparison=">=",
                        passed=False,
                    ),
                    passed=False,
                )
            )
        max_amount = None
        amt = opt.get("amount") or {}
        limits = [amt["max_minor"]] if amt.get("max_minor") is not None else []
        rule = amt.get("max_rule")
        if (
            isinstance(rule, dict)
            and rule.get("of") == "is.revenue"
            and biz.revenue_annual_minor is not None
        ):
            limits.append(round(biz.revenue_annual_minor * rule["multiple_bp"] / 10_000))
        if limits and amount > min(limits):
            hard_false = True
            max_amount = min(limits)
            checks.append(
                RuleCheck(
                    rule_id=f"{oid}:amount",
                    description="Amount within the product's limit",
                    metric_id="request.amount_minor",
                    threshold=Threshold(
                        name="max_amount",
                        money=Money(minor=max_amount, currency=cur),
                        unit=Unit.MINOR,
                        origin=Origin.RULEBOOK,
                        comparison="<=",
                        passed=False,
                    ),
                    passed=False,
                )
            )

        def metric(name: str, cov_base=cov_base, dilution_bp=dilution_bp) -> Any:
            if name == "solvency.dscr_forward":
                return cov_base.value_bp if cov_base is not None else None
            if name == "decision.dilution":
                return dilution_bp
            if name == "is.revenue":
                return biz.revenue_annual_minor
            return None

        for e in opt.get("eligibility", []):
            ev = evaluate(e["condition"], inputs=inputs, metrics=metric, thresholds=rb.threshold)
            is_dscr = "solvency.dscr_forward" in str(e["condition"])
            hard = e.get("kind") == "hard"
            if hard and ev.result is False and not is_dscr:
                hard_false = True
            if hard and ev.result is None:
                hard_none = True
                missing_inputs |= ev.missing
            checks.append(
                RuleCheck(
                    rule_id=e["id"],
                    description=e.get("explain", e["id"]),
                    metric_id=next(iter(ev.used), e["id"]) if ev.used else e["id"],
                    threshold=Threshold(
                        name=e["id"],
                        value=1,
                        unit=Unit.COUNT,
                        origin=Origin.RULEBOOK,
                        comparison=">=",
                        passed=ev.result,
                    ),
                    passed=ev.result,
                    hard=hard,
                )
            )
        for name in sorted(missing_inputs):
            gaps.setdefault(
                name,
                InsufficientData(
                    need=name.replace("_", " "),
                    why="An eligibility rule needs it.",
                    blocking=False,
                    metric_ids=[name],
                ),
            )

        if (
            is_debt
            and dscr_fail
            and ebitda is not None
            and sched_mid is not None
            and not hard_false
        ):
            pr = price(opt, "mid", cur)
            ceiling = max_principal_at_dscr(
                ebitda,
                biz.existing_service_12m_minor,
                rb.value_bp("T-SOL-DSCR-01"),
                lambda p, opt=opt, pr=pr, tenor=tenor: round(
                    schedule(opt, p, pr.rate_bp, pr.fee_bp, tenor).service_12m
                ),
                amount,
            )
            down_pr = price(
                opt,
                "mid",
                cur,
                rate_shock_bp=shock if opt["pricing"].get("rate_type") == "floating" else 0,
            )
            ceiling_down = max_principal_at_dscr(
                ebitda_down,
                biz.existing_service_12m_minor,
                rb.value_bp("T-SOL-DSCR-02"),
                lambda p, opt=opt, down_pr=down_pr, tenor=tenor: round(
                    schedule(opt, p, down_pr.rate_bp, down_pr.fee_bp, tenor).service_12m
                ),
                amount,
            )
            max_amount = min(ceiling, ceiling_down)

        if hard_false:
            outcome, eligible = "ineligible", False
        elif hard_none:
            outcome, eligible = "needs_information", None
        elif cost_unknown or opt.get("verification") == "unverified":
            outcome, eligible = "cost_unknown", True
        elif dscr_fail:
            outcome, eligible = "possible_at_smaller_size", True
        else:
            outcome, eligible = "recommended", True

        ttf = opt.get("time_to_funds_days") or {}
        if ttf.get("low") is not None and ttf.get("high") is not None:
            figures.append(
                value_figure(
                    "financing.time_to_funds_days",
                    "Days until the money arrives (mid of range)",
                    (ttf["low"] + ttf["high"]) / 2,
                    Unit.DAYS,
                    inputs=[
                        value_input(
                            "low",
                            ttf["low"],
                            Unit.DAYS,
                            VERIFICATION_ORIGIN[field_verification(opt, ttf)],
                        ),
                        value_input(
                            "high",
                            ttf["high"],
                            Unit.DAYS,
                            VERIFICATION_ORIGIN[field_verification(opt, ttf)],
                        ),
                    ],
                )
            )
        ttf_mid = (
            (ttf["low"] + ttf["high"]) / 2
            if ttf.get("low") is not None and ttf.get("high") is not None
            else math.inf
        )
        cost_key = eac.get("mid") if eac.get("mid") is not None else math.inf
        order = {
            "recommended": 0,
            "possible_at_smaller_size": 1,
            "cost_unknown": 2,
            "needs_information": 3,
            "ineligible": 4,
        }[outcome]
        sort_key = (order, cost_key, ttf_mid, 1 if opt.get("dilution") else 0, oid)
        verification = opt.get("verification", "unverified")
        results.append(
            (
                FinancingOption(
                    option_id=oid,
                    name=opt["name"],
                    kind=otype,
                    illustrative=bool(opt.get("illustrative")),
                    source_ref=f"rulebook/financing.yaml#{oid} ({', '.join(opt.get('source_ids', []))}; as of {opt.get('as_of')})",
                    eligible=eligible,
                    eligibility=checks,
                    verification=verification,
                    figures=figures,
                    outcome=outcome,
                    max_amount=Money(minor=max_amount, currency=cur)
                    if max_amount is not None
                    else None,
                ),
                sort_key,
            )
        )

    results.sort(key=lambda r: r[1])
    ranked: list[FinancingOption] = []
    rank = 0
    best_cost = min((r[1][1] for r in results if r[1][0] <= 1), default=math.inf)
    for opt, key in results:
        reasons: list[str] = []
        if key[0] <= 2:
            rank += 1
        if key[0] <= 1 and key[1] == best_cost:
            reasons.append("lowest_effective_cost")
        if key[0] == 1:
            reasons.append("cover_too_thin_at_full_amount")
        if key[0] == 2:
            reasons.append("cost_not_cited_needs_quote")
        if key[3] == 1:
            reasons.append("gives_up_ownership")
        ranked.append(
            opt.model_copy(update={"rank": rank if key[0] <= 2 else None, "rank_reasons": reasons})
        )

    base_cov = (
        dscr_forward(ebitda, biz.existing_service_12m_minor, 0) if ebitda is not None else None
    )
    business = [
        money_figure(
            "is.revenue_annualised",
            "Sales, annualised",
            biz.revenue_annual_minor or 0,
            cur,
            inputs=[value_input("history_days", biz.history_days, Unit.DAYS, Origin.LEDGER)],
        ),
        money_figure(
            "business.ebitda_next_12m",
            "Operating profit before interest, next 12 months (stub)",
            ebitda or 0,
            cur,
            inputs=stub_inputs[:1],
            note="Operating cash flow proxy until engine.analysis provides forecast EBITDA.",
        ),
        money_figure(
            "business.existing_debt_service_12m",
            "Existing loan payments, next 12 months",
            biz.existing_service_12m_minor,
            cur,
            inputs=stub_inputs[1:],
        ),
        _coverage_figure(
            "solvency.dscr_forward",
            "Debt-service cover today",
            base_cov,
            stub_inputs,
            "T-SOL-DSCR-01",
        ),
    ]
    if biz.cash_lowest_closing_minor is not None:
        business.append(
            money_figure(
                "cash.lowest_closing",
                f"Lowest forecast cash (week {biz.cash_lowest_week})",
                biz.cash_lowest_closing_minor,
                cur,
                source_refs=[biz.forecast_run_id] if biz.forecast_run_id else [],
            )
        )
    for key in ("PK", "PK_3M", "CN"):
        ref = reference_rate(key, cat)
        if ref and ref.get("value_bp") is not None and key.startswith(biz.country or "?"):
            business.append(
                value_figure(
                    f"market.reference_lending_rate.{key}",
                    ref["name"],
                    ref["value_bp"],
                    Unit.BP,
                    inputs=[
                        value_input(
                            "rate",
                            ref["value_bp"],
                            Unit.BP,
                            VERIFICATION_ORIGIN.get(ref.get("verification"), Origin.ASSUMPTION),
                            ref=ref.get("source_id"),
                        )
                    ],
                )
            )
    run_id = (
        "fin_"
        + hashlib.sha256(
            f"{tenant_id}|{as_of}|{req.model_dump_json()}|{cat['catalogue_version']}|{ENGINE_VERSION}".encode()
        ).hexdigest()[:20]
    )
    return FinancingMatchResponse(
        mode=mode,
        tenant_id=tenant_id,
        generated_at=generated_at,
        run_id=run_id,
        currency=cur,
        as_of=as_of,
        amount=req.amount,
        purpose=req.purpose,
        catalogue=CatalogueRef(version=str(cat["catalogue_version"]), as_of=catalogue_as_of(cat)),
        business_figures=business,
        options=ranked,
        insufficient_data=list(gaps.values()),
    )
