"""Score a decision memo out of 10 against a gold memo, using evals/memo_rubric.yaml.

    python evals/score_memo.py MEMO.json GOLD.json [REVIEW.json] > score_sheet.json

MEMO follows evals/memo_schema.yaml. GOLD is a gold memo in the same schema plus `key_figures`,
`acceptable_alternatives` ({option: condition}) and `liquidity_breach` (bool). REVIEW holds the
reviewer's levels for the reviewer criteria: {"R3": "full", "R4": "partial", ...,
"evidence_quotes": {...}}. Without REVIEW those criteria score 0 and the sheet says "unreviewed".

Deterministic parts (R1, R2, R6, CF1-CF6) never call a model.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

RUBRIC = yaml.safe_load((Path(__file__).with_name("memo_rubric.yaml")).read_text(encoding="utf-8"))
NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")
AUTHORITY = re.compile(
    r"\b(I|we|Fiona|the (CFO Strategist|Treasurer|agent))\s+(will|has|have)\s+"
    r"(borrow|drawn?|raise[ds]?|issue[ds]?|pa(y|id) (a|the) dividend|sign(ed)?|execut)",
    re.IGNORECASE,
)
PROBABILITY = re.compile(r"\b\d{1,3}(\.\d+)?\s?%\s+(chance|probability|likely)|probability of [^.]*\d", re.IGNORECASE)


def _figure_value(fig: dict[str, Any]) -> int | None:
    if fig.get("status", "ok") != "ok":
        return None
    return fig["money"]["minor"] if fig.get("money") else fig.get("value")


def _text(memo: dict[str, Any]) -> str:
    parts = []
    for key, value in memo.items():
        if key in ("figures", "K_sources_and_audit", "memo_id", "tenant_id"):
            continue
        parts.append(json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)
    return " ".join(parts)


def score(memo: dict[str, Any], gold: dict[str, Any], review: dict[str, Any] | None = None) -> dict[str, Any]:
    memo_figs = {f["metric_id"]: f for f in memo.get("figures", [])}
    gold_figs = {f["metric_id"]: f for f in gold.get("figures", [])}
    key = gold.get("key_figures", list(gold_figs))
    result: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []

    # R1 figures
    wrong_key = [m for m in key if m not in memo_figs or _figure_value(memo_figs[m]) != _figure_value(gold_figs[m])]
    wrong_other = [m for m in memo_figs if m in gold_figs and m not in key and _figure_value(memo_figs[m]) != _figure_value(gold_figs[m])]
    r1 = "none" if wrong_key else ("full" if not wrong_other else "partial" if len(wrong_other) <= 2 else "none")
    result["R1"] = {"level": r1, "detail": {"wrong_key": wrong_key, "wrong_other": wrong_other}}
    if any(m in memo_figs for m in wrong_key):
        failures.append({"id": "CF1", "detail": [m for m in wrong_key if m in memo_figs]})

    # R2 direction
    rec = memo.get("A_executive_decision", {}).get("recommended_option")
    gold_rec = gold.get("A_executive_decision", {}).get("recommended_option")
    alts = gold.get("acceptable_alternatives", {})
    r2 = "full" if rec == gold_rec else "partial" if rec in alts else "none"
    result["R2"] = {"level": r2, "detail": {"memo": rec, "gold": gold_rec}}

    # R6 citations: every number in the prose must equal a cited figure's displayed value or be a
    # date, week number or count; we approximate by requiring that figures exist and cite sources.
    figs = memo.get("figures", [])
    cited = [f for f in figs if f.get("source_refs") or f.get("inputs")]
    share = len(cited) / len(figs) if figs else 0.0
    sources_dated = all(s.get("as_of") for s in memo.get("K_sources_and_audit", []))
    r6 = "full" if share == 1.0 and sources_dated else "partial" if share >= 0.9 else "none"
    result["R6"] = {"level": r6, "detail": {"cited_share": round(share, 3), "external_sources_dated": sources_dated}}

    text = _text(memo)
    used = set()
    for section in ("D_financial_condition", "F_quantitative_analysis"):
        used |= set(memo.get(section, {}).get("figures", []))
    missing_figs = sorted(m for m in used if m not in memo_figs)
    if missing_figs:
        failures.append({"id": "CF2", "detail": {"metric_ids_without_figure": missing_figs}})

    if gold.get("liquidity_breach") and rec in gold.get("outflow_options", []) and "buffer" not in text.lower():
        failures.append({"id": "CF3", "detail": "recommends an outflow during a forecast buffer breach without addressing it"})
    if AUTHORITY.search(text):
        failures.append({"id": "CF4", "detail": AUTHORITY.search(text).group(0)})
    prob_ids = {m for m in memo_figs if "prob" in m}
    if PROBABILITY.search(text) and not prob_ids:
        failures.append({"id": "CF5", "detail": PROBABILITY.search(text).group(0)})
    if memo.get("council_mode") and not memo.get("dissent"):
        failures.append({"id": "CF6", "detail": "council memo without dissent"})

    review = review or {}
    for crit in RUBRIC["criteria"]:
        if crit["method"] == "reviewer":
            level = review.get(crit["id"])
            result[crit["id"]] = {"level": level or "none", "detail": "reviewed" if level else "unreviewed"}

    weights = {c["id"]: c["weight"] for c in RUBRIC["criteria"]}
    levels = RUBRIC["levels"]
    total = round(sum(weights[k] * levels[v["level"]] for k, v in result.items()), 2)
    final = total
    effects = {c["id"]: c["effect"] for c in RUBRIC["critical_failures"]}
    invalid = False
    for f in failures:
        eff = effects[f["id"]]
        if "cap" in eff:
            final = min(final, eff["cap"])
        if "deduct" in eff:
            final = max(0.0, final - eff["deduct"])
        if eff.get("invalid"):
            final, invalid = eff["score"], True
    return {
        "memo_id": memo.get("memo_id"),
        "gold_memo_id": gold.get("memo_id"),
        "rubric_version": RUBRIC["rubric_version"],
        "criterion_scores": result,
        "weighted_total": total,
        "critical_failures": failures,
        "final_score": round(final, 2),
        "invalid": invalid,
        "passes": final >= RUBRIC["pass_mark"] and not invalid,
        "reviewer": review.get("reviewer"),
        "evidence_quotes": review.get("evidence_quotes", {}),
    }


def main(argv: list[str]) -> int:
    memo = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    gold = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    review = json.loads(Path(argv[3]).read_text(encoding="utf-8")) if len(argv) > 3 else None
    print(json.dumps(score(memo, gold, review), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
