import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from score_memo import score  # noqa: E402

FIG = lambda mid, v: {"metric_id": mid, "value": v, "unit": "bp", "source_refs": ["fc_1"]}  # noqa: E731

GOLD = {
    "memo_id": "gold_de",
    "A_executive_decision": {"recommended_option": "E_defer"},
    "acceptable_alternatives": {"D_mixed": "debt sized to downside DSCR 1.0x"},
    "key_figures": ["solvency.dscr_forward"],
    "liquidity_breach": True,
    "outflow_options": ["A_debt", "C_internal"],
    "figures": [FIG("solvency.dscr_forward", 11398), FIG("liquidity.buffer_headroom_min", -42000000)],
}
MEMO = {
    "memo_id": "agent_de",
    "A_executive_decision": {"recommended_option": "E_defer", "one_line": "Defer: cash dips below the buffer in week 7."},
    "D_financial_condition": {"figures": ["solvency.dscr_forward"]},
    "figures": [FIG("solvency.dscr_forward", 11398), FIG("liquidity.buffer_headroom_min", -42000000)],
    "K_sources_and_audit": [{"ref": "fc_1", "kind": "forecast_run", "as_of": "2026-10-19"}],
}
FULL_REVIEW = {c: "full" for c in ("R3", "R4", "R5", "R7", "R8")}


def test_matching_memo_scores_ten():
    sheet = score(MEMO, GOLD, FULL_REVIEW)
    assert sheet["final_score"] == 10.0 and sheet["passes"]


def test_wrong_key_figure_caps_at_four():
    memo = copy.deepcopy(MEMO)
    memo["figures"][0]["value"] = 12500
    sheet = score(memo, GOLD, FULL_REVIEW)
    assert any(f["id"] == "CF1" for f in sheet["critical_failures"])
    assert sheet["final_score"] == 4.0


def test_acceptable_alternative_is_partial_direction():
    memo = copy.deepcopy(MEMO)
    memo["A_executive_decision"]["recommended_option"] = "D_mixed"
    assert score(memo, GOLD, FULL_REVIEW)["final_score"] == 9.0


def test_outflow_during_breach_without_mentioning_buffer_caps_at_three():
    memo = copy.deepcopy(MEMO)
    memo["A_executive_decision"] = {"recommended_option": "C_internal", "one_line": "Use cash on hand."}
    sheet = score(memo, GOLD, FULL_REVIEW)
    assert sheet["final_score"] == 3.0


def test_claiming_to_borrow_invalidates():
    memo = copy.deepcopy(MEMO)
    memo["H_recommendation"] = {"reasoning": "The Treasurer will borrow PKR 5m tomorrow."}
    sheet = score(memo, GOLD, FULL_REVIEW)
    assert sheet["invalid"] and sheet["final_score"] == 0.0


def test_unreviewed_criteria_score_zero_and_say_so():
    sheet = score(MEMO, GOLD)
    assert sheet["criterion_scores"]["R3"]["detail"] == "unreviewed"
    assert sheet["weighted_total"] == 5.0  # R1 2 + R2 2 + R6 1
