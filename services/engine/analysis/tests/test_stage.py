import pytest

from engine.analysis.stage import detect_stage
from engine.analysis.statements import CashFlows


def _with_flows(window, cfo, cfi, cff, **extra):
    return window.model_copy(update={"cash_flows": CashFlows(cfo=cfo, cfi=cfi, cff=cff, **extra)})


@pytest.mark.parametrize(
    ("signs", "stage", "pattern"),
    [
        ((-1, -1, 1), "introduction", "P1"),
        ((1, -1, 1), "growth", "P2"),
        ((1, -1, -1), "mature", "P3"),
        ((-1, -1, -1), "shake_out", "P4"),
        ((1, 1, 1), "shake_out", "P5"),
        ((1, 1, -1), "shake_out", "P6"),
        ((-1, 1, 1), "decline", "P7"),
        ((-1, 1, -1), "decline", "P8"),
    ],
)
def test_all_eight_dickinson_patterns(fy2026, signs, stage, pattern):
    big = 500_000_000  # well outside the 2% near-zero band (192m on 9.6bn revenue)
    w = _with_flows(fy2026, *(s * big for s in signs))
    result = detect_stage(w)
    assert (result.stage, result.pattern_id) == (stage, pattern)


def test_owner_says_growth_cash_says_shake_out(fy2025, fy2026):
    latest = _with_flows(fy2026, -400_000_000, -300_000_000, -250_000_000)
    result = detect_stage(latest, fy2025, owner_stated_stage="growth")
    assert result.stage == "shake_out"
    assert result.disagreement is True
    assert result.consistency == "transition"  # FY2025 reads as growth
    assert result.windows[1].stage == "growth"
    assert "You described the business as a growth business" in result.explanation
    assert (
        "operating cash flow (an outflow)" in result.explanation
    )  # the flow that contradicts growth
    assert "STG-07" in result.rules_applied


def test_near_zero_flow_makes_the_stage_ambiguous(fy2026):
    # CFO of -95.4m is inside the 192m band: could be mature (+) or shake-out (-)
    result = detect_stage(fy2026)
    assert result.windows[0].signs["cfo"] == "near_zero"
    assert result.confidence == "low"
    assert result.windows[0].alternatives


def test_fewer_than_12_months_is_not_classifiable(fy2026):
    short = fy2026.model_copy(update={"months_of_data": 8})
    result = detect_stage(short, owner_stated_stage="growth")
    assert result.stage == "not_classifiable"
    assert "unverified" in result.explanation


def test_one_off_financing_lowers_confidence(fy2025):
    w = _with_flows(
        fy2025, 500_000_000, -600_000_000, 1_200_000_000, largest_financing_inflow=1_200_000_000
    )
    result = detect_stage(w)
    assert result.stage == "growth"
    assert "one_off_financing" in result.windows[0].distortions
    assert result.confidence == "low"  # single window (medium) minus one step
