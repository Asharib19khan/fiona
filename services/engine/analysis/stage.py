"""Stage Detector (Y2): lifecycle stage from cash-flow sign patterns, after Dickinson (2011),
implementing rules STG-00 to STG-07 in rulebook/finance_rules.yaml.

The cash flows are evidence; the owner's stated stage is a hypothesis. When they disagree the
result says so and explains which flow contradicts the owner, and never silently picks one.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import product
from typing import Literal

from pydantic import BaseModel, Field

from engine.analysis import rulebook
from engine.analysis._contracts import Figure, FigureInput, Money, Origin, Unit
from engine.analysis.statements import Window

Sign = Literal["pos", "neg", "near_zero"]
Stage = Literal["introduction", "growth", "mature", "shake_out", "decline", "not_classifiable"]
Confidence = Literal["high", "medium", "low", "none"]
_LEVELS: list[Confidence] = ["high", "medium", "low"]

STAGE_WORDS = {
    "introduction": "an early-stage (introduction) business",
    "growth": "a growth business",
    "mature": "a mature business",
    "shake_out": "a shake-out business",
    "decline": "a declining business",
}
SIGN_WORDS = {"pos": "an inflow", "neg": "an outflow", "near_zero": "close to zero"}
FLOW_WORDS = {"cfo": "operating", "cfi": "investing", "cff": "financing"}


class WindowStage(BaseModel):
    label: str
    signs: dict[str, Sign]
    stage: Stage
    pattern_id: str | None
    alternatives: list[Stage] = Field(default_factory=list)
    distortions: list[str] = Field(default_factory=list)


class StageResult(BaseModel):
    stage: Stage
    confidence: Confidence
    pattern_id: str | None
    consistency: Literal["stable", "transition", "single_window", "none"]
    windows: list[WindowStage]
    owner_stated_stage: str | None
    disagreement: bool
    explanation: str
    contradictions: list[str] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    rules_applied: list[str] = Field(default_factory=list)


def _patterns() -> dict[tuple[str, str, str], tuple[str, Stage]]:
    return {
        (p["cfo"], p["cfi"], p["cff"]): (p["pattern_id"], p["stage"])
        for p in rulebook.stage_patterns()
    }


def _sign(amount: int, band: Decimal) -> Sign:
    if amount >= band and amount != 0:
        return "pos"
    if amount <= -band and amount != 0:
        return "neg"
    return "near_zero"


def classify_window(w: Window) -> WindowStage:
    """STG-01 and STG-02 for one window, plus STG-05 distortion flags."""
    band = Decimal(abs(w.income.revenue)) * rulebook.value_bp("T-STG-ZERO-01") / 10000
    flows = {"cfo": w.cash_flows.cfo, "cfi": w.cash_flows.cfi, "cff": w.cash_flows.cff}
    signs: dict[str, Sign] = {k: _sign(v, band) for k, v in flows.items()}
    table = _patterns()

    options = [
        ("pos", "neg") if signs[k] == "near_zero" else (signs[k],) for k in ("cfo", "cfi", "cff")
    ]
    candidates = {combo: table[combo] for combo in product(*options)}
    stages = {stage for _, stage in candidates.values()}
    if len(stages) == 1:
        pattern_id, stage = next(iter(candidates.values()))
        if any(s == "near_zero" for s in signs.values()):
            pattern_id = None  # stage is certain, pattern is not
        alternatives: list[Stage] = []
    else:
        # primary = treat each near-zero flow by its actual sign (zero counts as an inflow)
        primary = tuple(
            ("pos" if flows[k] >= 0 else "neg") if signs[k] == "near_zero" else signs[k]
            for k in ("cfo", "cfi", "cff")
        )
        pattern_id, stage = table[primary]
        alternatives = sorted(stages - {stage})

    params = rulebook.stage_distortion_parameters()
    cf, rev = w.cash_flows, abs(w.income.revenue)
    distortions = []
    if cf.cfi != 0 and abs(cf.acquisitions) * 10000 > abs(cf.cfi) * params["acquisition_share_bp"]:
        distortions.append("acquisition")
    if (
        rev
        and cf.largest_financing_inflow * 10000 > rev * params["one_off_financing_revenue_share_bp"]
    ):
        distortions.append("one_off_financing")
    if cf.cfi > 0 and cf.largest_disposal * 10000 > cf.cfi * params["one_off_disposal_share_bp"]:
        distortions.append("one_off_asset_sale")
    if w.months_of_data < 12:
        distortions.append("missing_period")
    return WindowStage(
        label=w.label,
        signs=signs,
        stage=stage,
        pattern_id=pattern_id,
        alternatives=alternatives,
        distortions=distortions,
    )


def _lower(level: Confidence, steps: int) -> Confidence:
    if level == "none":
        return level
    return _LEVELS[min(_LEVELS.index(level) + steps, len(_LEVELS) - 1)]


def _expected(stage: str) -> str:
    rows = [p for p in rulebook.stage_patterns() if p["stage"] == stage]
    if not rows:
        return "a different pattern"
    parts = [
        f"operating {SIGN_WORDS[p['cfo']]}, investing {SIGN_WORDS[p['cfi']]} and financing {SIGN_WORDS[p['cff']]}"
        for p in rows
    ]
    return " or ".join(parts)


def _money_figure(metric_id: str, label: str, amount: int, w: Window) -> Figure:
    return Figure(
        metric_id=metric_id,
        label=label,
        money=Money(minor=amount, currency=w.currency),
        unit=Unit.MINOR,
        formula=f"net cash from {label.lower()}",
        source_refs=w.source_refs,
        inputs=[
            FigureInput(
                name=label,
                money=Money(minor=amount, currency=w.currency),
                unit=Unit.MINOR,
                origin=Origin.LEDGER,
            )
        ],
    )


def detect_stage(
    latest: Window,
    prior: Window | None = None,
    owner_stated_stage: str | None = None,
    revenue_growth_bp: int | None = None,
    operating_margin_bp: int | None = None,
    owner_declared_event: str | None = None,
) -> StageResult:
    """Classify the latest 12 months, check them against the prior 12 and the owner's view."""
    rules = ["STG-00"]
    months = Figure(
        metric_id="stage.months_of_data",
        label="Months of cash-flow history",
        value=latest.months_of_data + (prior.months_of_data if prior else 0),
        unit=Unit.MONTHS,
        formula="complete months with reconciled data",
    )
    if latest.months_of_data < rulebook.value("T-STG-MIN-01"):
        return StageResult(
            stage="not_classifiable",
            confidence="none",
            pattern_id=None,
            consistency="none",
            windows=[],
            owner_stated_stage=owner_stated_stage,
            disagreement=False,
            figures=[months],
            rules_applied=rules,
            explanation=(
                f"Fiona needs at least 12 months of cash flows to infer a lifecycle stage; it has "
                f"{latest.months_of_data}. Until then it shows your stated stage "
                f"({owner_stated_stage or 'not given'}), marked as unverified."
            ),
        )

    rules += ["STG-01", "STG-02"]
    now = classify_window(latest)
    windows = [now]
    consistency: Literal["stable", "transition", "single_window", "none"] = "single_window"
    if prior is not None and prior.months_of_data >= 12:
        rules.append("STG-03")
        then = classify_window(prior)
        windows.append(then)
        consistency = "stable" if then.stage == now.stage else "transition"

    confidence: Confidence = "high" if consistency == "stable" else "medium"
    if now.alternatives:
        confidence = "low"

    contradictions: list[str] = []
    if revenue_growth_bp is not None or operating_margin_bp is not None:
        rules.append("STG-04")
        if now.stage in ("growth",) and revenue_growth_bp is not None and revenue_growth_bp <= 0:
            contradictions.append("revenue is not growing")
        if now.stage == "decline" and revenue_growth_bp is not None and revenue_growth_bp > 0:
            contradictions.append("revenue is still growing")
        if (
            now.stage in ("growth", "mature")
            and operating_margin_bp is not None
            and operating_margin_bp < 0
        ):
            contradictions.append("operating margin is negative")
        if now.stage == "shake_out" and revenue_growth_bp is not None and revenue_growth_bp > 0:
            contradictions.append("revenue is growing")
        if len(contradictions) >= 2:
            confidence = _lower(confidence, 1)

    distortions = list(now.distortions) + (
        [f"owner_declared:{owner_declared_event}"] if owner_declared_event else []
    )
    if distortions:
        rules.append("STG-05")
        confidence = _lower(confidence, len(distortions))
    rules.append("STG-06")

    cf = latest.cash_flows
    figures = [
        months,
        _money_figure("cash.cfo", "Operating activities", cf.cfo, latest),
        _money_figure("cash.cfi", "Investing activities", cf.cfi, latest),
        _money_figure("cash.cff", "Financing activities", cf.cff, latest),
    ]

    lines = [
        f"Over {latest.label} operating cash flow was {SIGN_WORDS[now.signs['cfo']]}, investing "
        f"{SIGN_WORDS[now.signs['cfi']]} and financing {SIGN_WORDS[now.signs['cff']]}. "
        f"That is the pattern of {STAGE_WORDS[now.stage]}."
    ]
    if now.alternatives:
        lines.append(
            f"One flow is close to zero, so it could also read as {', '.join(STAGE_WORDS[a] for a in now.alternatives)}."
        )
    if consistency == "transition":
        lines.append(
            f"The year before ({windows[1].label}) looked like {STAGE_WORDS[windows[1].stage]}, so the business is changing stage."
        )
    elif consistency == "stable":
        lines.append("The year before showed the same pattern.")
    if distortions:
        lines.append(
            "Treat this with care: "
            + ", ".join(d.replace("_", " ") for d in distortions)
            + " affected the year."
        )

    disagreement = bool(owner_stated_stage and owner_stated_stage not in ("unsure", now.stage))
    if disagreement:
        rules.append("STG-07")
        expected_rows = [p for p in rulebook.stage_patterns() if p["stage"] == owner_stated_stage]
        mismatched = sorted(
            {
                k
                for p in expected_rows
                for k in ("cfo", "cfi", "cff")
                if now.signs[k] not in (p[k], "near_zero")
            }
        )
        culprit = (
            ", ".join(f"{FLOW_WORDS[k]} cash flow ({SIGN_WORDS[now.signs[k]]})" for k in mismatched)
            or "the overall pattern"
        )
        lines.insert(
            0,
            f"You described the business as {STAGE_WORDS.get(owner_stated_stage, owner_stated_stage)}. Its cash flows say otherwise.",
        )
        lines.append(
            f"{STAGE_WORDS.get(owner_stated_stage, owner_stated_stage).capitalize()} would normally show {_expected(owner_stated_stage)}. "
            f"The difference comes from {culprit}. Fiona plans with the cash-flow stage and keeps your view on record; "
            "if a one-off event explains the gap, tell Fiona and it will show both."
        )
    if contradictions:
        lines.append("Other evidence does not fully fit: " + "; ".join(contradictions) + ".")

    return StageResult(
        stage=now.stage,
        confidence=confidence,
        pattern_id=now.pattern_id,
        consistency=consistency,
        windows=windows,
        owner_stated_stage=owner_stated_stage,
        disagreement=disagreement,
        explanation=" ".join(lines),
        contradictions=contradictions,
        figures=figures,
        rules_applied=rules,
    )
