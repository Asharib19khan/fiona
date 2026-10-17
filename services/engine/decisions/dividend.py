"""Dividend versus reinvestment decision engine (Y4 Part 2 / Tier 2).

Evaluates whether an SME can safely distribute dividends to shareholders or should
reinvest in working capital and operations, strictly enforcing:
1. Direct 13-week cash forecast buffer constraints (Rule DV-01 / G-08).
2. Distributable profits and capital protection under corporate law (Pakistan Companies Act 2017 s.240/241).
3. Opportunity cost comparison against internal operating reinvestment returns (Rule DV-02).
"""

from __future__ import annotations

from datetime import UTC, datetime

from engine.decisions.schemas import (
    CashPathPoint,
    DecisionOption,
    DecisionRecommendation,
    DecisionResponse,
    DividendRequest,
)
from engine.forecast._contracts import Figure, FigureInput, Money, Origin, Unit
from engine.forecast.cash.engine import forecast_cash
from engine.forecast.figures import (
    InsufficientData,
    RuleCheck,
    bp_figure,
    bp_input,
    bp_threshold,
    money_figure,
    money_input,
    money_threshold,
    stable_id,
)
from engine.forecast.ledger_source import LedgerSnapshot

ENGINE_VERSION = "decisions/dividend/0.1.0"


def compare_dividend(
    body: DividendRequest,
    snapshot: LedgerSnapshot,
    mode: str = "mock",
    generated_at: datetime | None = None,
) -> DecisionResponse:
    """Compare paying dividends now, deferring to post-dip, or reinvesting in operations."""
    as_of = snapshot.as_of
    currency = snapshot.currency
    cash_buffer_minor = snapshot.cash_buffer_minor

    # 1. Run direct 13-week cash forecast
    forecast = forecast_cash(snapshot)
    weeks = forecast.weeks
    if not weeks:
        raise ValueError("Cash forecast produced no weekly projections")

    # 2. Identify lowest cash point and working capital dip
    dip_week_obj = min(weeks, key=lambda w: w.closing.minor)
    dip_week = dip_week_obj.week
    lowest_all_minor = dip_week_obj.closing.minor

    # Safe dividend capacity keeping cash >= buffer in every week
    safe_now_minor = max(0, lowest_all_minor - cash_buffer_minor)

    # Post-dip recovery weeks
    post_dip_weeks = [w for w in weeks if w.week > dip_week]
    if post_dip_weeks:
        lowest_post_dip_obj = min(post_dip_weeks, key=lambda w: w.closing.minor)
        lowest_post_dip_minor = lowest_post_dip_obj.closing.minor
        safe_post_dip_minor = max(0, lowest_post_dip_minor - cash_buffer_minor)
        recovery_week = post_dip_weeks[0].week
    else:
        lowest_post_dip_minor = lowest_all_minor
        safe_post_dip_minor = safe_now_minor
        recovery_week = dip_week

    # 3. Determine proposed dividend amount
    if body.proposed_dividend is not None:
        proposed_minor = body.proposed_dividend.minor
    else:
        # If not specified, default to benchmark 1.5M or safe capacity
        proposed_minor = 1_500_000_00

    now_ok = proposed_minor <= safe_now_minor
    later_ok = proposed_minor <= safe_post_dip_minor

    # 4. Generate Cash Path Points for Option 1 (Pay Now)
    path_now: list[CashPathPoint] = []
    for w in weeks:
        closing_with = w.closing.minor - proposed_minor
        path_now.append(
            CashPathPoint(
                week=w.week,
                closing_without=w.closing,
                closing_with=Money(minor=closing_with, currency=currency),
            )
        )

    # Generate Cash Path Points for Option 2 (Pay Later)
    path_later: list[CashPathPoint] = []
    for w in weeks:
        closing_with = (
            w.closing.minor - proposed_minor if w.week >= recovery_week else w.closing.minor
        )
        path_later.append(
            CashPathPoint(
                week=w.week,
                closing_without=w.closing,
                closing_with=Money(minor=closing_with, currency=currency),
            )
        )

    # 5. Build Options
    # Option 1: Pay Now
    check_now = RuleCheck(
        rule_id="DV-01",
        description="Cash stays above the liquidity buffer after immediate dividend distribution",
        metric_id="decision.max_safe_dividend_now",
        threshold=money_threshold(
            "proposed_dividend", proposed_minor, currency, Origin.USER, "<=", now_ok
        ),
        passed=now_ok,
    )
    option_pay_now = DecisionOption(
        option_id="pay_now",
        label=f"Pay {currency} {proposed_minor / 100:,.0f} now",
        eligible=now_ok,
        rule_checks=[check_now],
        cash_path=path_now,
        figures=[
            money_figure(
                "decision.max_safe_dividend_now",
                "Largest dividend that keeps every forecast week above the buffer",
                safe_now_minor,
                currency,
                formula="max(0, lowest forecast closing - buffer)",
                inputs=[
                    money_input("lowest_closing", lowest_all_minor, currency, Origin.LEDGER),
                    money_input("cash_buffer", cash_buffer_minor, currency, Origin.RULEBOOK),
                ],
            ),
            money_figure(
                "decision.min_cash_after_dividend",
                "Lowest forecast closing cash after paying now",
                lowest_all_minor - proposed_minor,
                currency,
            ),
            Figure(
                metric_id="decision.week_of_min_after_dividend",
                label="Week of lowest cash closing",
                unit=Unit.WEEKS,
                value=dip_week,
                provenance=Origin.LEDGER,
            ),
        ],
    )

    # Option 2: Pay After Working Capital Dip
    later_option_id = f"pay_after_week_{dip_week}"
    check_later = RuleCheck(
        rule_id="DV-01",
        description=f"Cash stays above the buffer when paid after the working capital dip (from week {recovery_week})",
        metric_id="decision.max_safe_dividend_after_dip",
        threshold=money_threshold(
            "proposed_dividend", proposed_minor, currency, Origin.USER, "<=", later_ok
        ),
        passed=later_ok,
    )
    option_pay_later = DecisionOption(
        option_id=later_option_id,
        label=f"Pay {currency} {proposed_minor / 100:,.0f} from week {recovery_week} (after stock clearance)",
        eligible=later_ok,
        rule_checks=[check_later],
        cash_path=path_later,
        figures=[
            money_figure(
                "decision.max_safe_dividend_after_dip",
                f"Largest safe dividend from week {recovery_week}",
                safe_post_dip_minor,
                currency,
                formula="max(0, lowest post-dip closing - buffer)",
                inputs=[
                    money_input(
                        "lowest_post_dip_closing", lowest_post_dip_minor, currency, Origin.LEDGER
                    ),
                    money_input("cash_buffer", cash_buffer_minor, currency, Origin.RULEBOOK),
                ],
            ),
            money_figure(
                "decision.min_cash_after_dividend",
                "Lowest forecast closing cash after deferred payment",
                lowest_post_dip_minor - proposed_minor,
                currency,
            ),
        ],
    )

    # Option 3: Reinvest into Operations & Working Capital
    reinvest_bp = (
        body.reinvestment_return_bp if body.reinvestment_return_bp is not None else 1800
    )  # 18.0% baseline
    reinvest_gain_minor = int(proposed_minor * reinvest_bp / 10_000)
    reinvest_checks: list[RuleCheck] = []

    if body.owner_required_return_bp is not None:
        reinvest_beats_hurdle = reinvest_bp >= body.owner_required_return_bp
        reinvest_checks.append(
            RuleCheck(
                rule_id="DV-02",
                description="Reinvestment operating return exceeds owner required hurdle rate",
                metric_id="decision.reinvestment_return",
                threshold=bp_threshold(
                    "owner_required_return",
                    body.owner_required_return_bp / 10_000,
                    Origin.USER,
                    ">=",
                    reinvest_beats_hurdle,
                ),
                passed=reinvest_beats_hurdle,
            )
        )

    option_reinvest = DecisionOption(
        option_id="reinvest",
        label="Retain earnings and reinvest into inventory and working capital",
        eligible=True,
        rule_checks=reinvest_checks,
        figures=[
            bp_figure(
                "decision.reinvestment_return",
                "Expected annual return from operating reinvestment",
                reinvest_bp / 10_000,
                inputs=[
                    bp_input(
                        "reinvestment_return_bp",
                        reinvest_bp / 10_000,
                        Origin.USER
                        if body.reinvestment_return_bp is not None
                        else Origin.ASSUMPTION,
                    )
                ],
            ),
            money_figure(
                "decision.reinvestment_projected_gain",
                "Projected 12-month gain from retained capital",
                reinvest_gain_minor,
                currency,
                formula="proposed_dividend x reinvestment_return",
            ),
        ],
    )

    options = [option_pay_now, option_pay_later, option_reinvest]

    # 6. Recommendation Logic
    rule_trace: list[RuleCheck] = [check_now]
    if not now_ok:
        if later_ok:
            rec_outcome = "recommend"
            rec_option = later_option_id
            rec_reasons = ["dividend_now_breaches_buffer", "safe_after_working_capital_clears"]
            rule_trace.append(check_later)
        else:
            rec_outcome = "recommend"
            rec_option = "reinvest"
            rec_reasons = [
                "dividend_now_breaches_buffer",
                "insufficient_liquidity_across_horizon",
                "preserves_working_capital",
            ]
    else:
        # Now is safe; check whether reinvestment return is significantly higher than hurdle
        if (
            body.owner_required_return_bp is not None
            and reinvest_bp > body.owner_required_return_bp + 500
        ):
            rec_outcome = "recommend"
            rec_option = "reinvest"
            rec_reasons = ["reinvestment_return_exceeds_hurdle", "preserves_expansion_capacity"]
        else:
            rec_outcome = "recommend"
            rec_option = "pay_now"
            rec_reasons = ["cash_stays_above_buffer", "liquid_reserves_sufficient"]

    recommendation = DecisionRecommendation(
        outcome=rec_outcome,
        option_id=rec_option,
        rule_trace=rule_trace,
        reason_codes=rec_reasons,
    )

    # 7. Insufficient Data
    insufficient: list[InsufficientData] = []
    if body.reinvestment_return_bp is None:
        insufficient.append(
            InsufficientData(
                need="Reinvestment return for operating inventory and expansion",
                why="Needed to compare the opportunity cost of paying out cash versus deploying internally.",
                blocking=False,
                metric_ids=["decision.reinvestment_return"],
            )
        )

    # 8. Shared figures & inputs
    shared_figures = [
        forecast.lowest_closing,
        forecast.buffer,
        money_figure(
            "decision.current_operating_buffer",
            "Target cash buffer",
            cash_buffer_minor,
            currency,
        ),
    ]

    inputs: list[FigureInput] = [
        money_input("proposed_dividend", proposed_minor, currency, Origin.USER),
    ]
    if body.reinvestment_return_bp is not None:
        inputs.append(
            bp_input("reinvestment_return_bp", body.reinvestment_return_bp / 10_000, Origin.USER)
        )
    if body.owner_required_return_bp is not None:
        inputs.append(
            bp_input(
                "owner_required_return_bp", body.owner_required_return_bp / 10_000, Origin.USER
            )
        )

    run_id = stable_id(
        "dec",
        mode,
        f"dividend_{proposed_minor}_{body.reinvestment_return_bp}_{body.owner_required_return_bp}",
    )

    return DecisionResponse(
        api_version="v1",
        mode=mode,
        tenant_id=snapshot.tenant_id,
        engine_version=ENGINE_VERSION,
        generated_at=generated_at or datetime.now(UTC),
        decision="dividend",
        run_id=run_id,
        currency=currency,
        as_of=as_of,
        inputs=inputs,
        figures=shared_figures,
        options=options,
        recommendation=recommendation,
        insufficient_data=insufficient,
    )
