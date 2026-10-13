"""Check the rulebook's internal consistency: every file parses, IDs are unique, every
threshold and metric reference resolves, and no float appears where the units convention
requires integers. Run: python rulebook/tools/validate_rulebook.py  (exit 1 on any error).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FLOAT_ALLOWED_KEYS = {"elasticity_scenarios"}  # dimensionless slopes, by convention


def load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def floats(node, path="", out=None):
    out = [] if out is None else out
    if isinstance(node, float):
        out.append(path)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key not in FLOAT_ALLOWED_KEYS:
                floats(value, f"{path}.{key}", out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            floats(value, f"{path}[{i}]", out)
    return out


def split_items(node, path="", out=None):
    """Unquoted flow-list items like [a (b, c)] silently become two items; catch them."""
    out = [] if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            split_items(value, f"{path}.{key}", out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            if isinstance(value, str) and value.count("(") != value.count(")"):
                out.append(f"{path}[{i}]")
            split_items(value, f"{path}[{i}]", out)
    return out


def main() -> int:
    errors: list[str] = []
    files = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.yaml"))
    docs = {}
    for name in files:
        try:
            docs[name] = load(name)
        except yaml.YAMLError as exc:
            errors.append(f"{name}: does not parse: {exc}")
    if errors:
        print("\n".join(errors))
        return 1

    thresholds = docs["thresholds.yaml"]["thresholds"]
    t_ids = [t["id"] for t in thresholds]
    errors += [f"thresholds.yaml: duplicate id {i}" for i in {i for i in t_ids if t_ids.count(i) > 1}]

    metrics = docs["metrics.yaml"]
    m_ids = [m["id"] for m in metrics["metrics"]] + [c["id"] for c in metrics["concepts"]]
    errors += [f"metrics.yaml: duplicate id {i}" for i in {i for i in m_ids if m_ids.count(i) > 1}]

    text = {name: (ROOT / name).read_text(encoding="utf-8") for name in files}
    t_set, m_set = set(t_ids), set(m_ids)
    for name, body in text.items():
        if name == "thresholds.yaml":
            continue
        for ref in set(re.findall(r"\bT-[A-Z0-9]+-[A-Z0-9]+(?:-[0-9]+)?\b", body)):
            if ref not in t_set:
                errors.append(f"{name}: unknown threshold {ref}")
    metric_ref = re.compile(r"(?:\bmetric|rhs_metric|metric_id|primary): ([a-z_]+\.[a-z0-9_]+)|\{figure:([a-z_]+\.[a-z0-9_]+)\}")
    list_ref = re.compile(r"(?:metric_dependencies|context_metrics|formula_reference): \[([^\]]+)\]")
    for name, body in text.items():
        refs = {a or b for a, b in metric_ref.findall(body)}
        for group in list_ref.findall(body):
            refs |= {x.strip() for x in group.split(",")}
        for ref in sorted(refs):
            if ref not in m_set:
                errors.append(f"{name}: unknown metric {ref}")

    for name, doc in docs.items():
        for path in floats(doc):
            errors.append(f"{name}: float at {path} (use _bp or _minor integers)")
        for path in split_items(doc):
            errors.append(f"{name}: list item split at a comma inside parentheses at {path} (quote it)")

    guardian = docs.get("guardian.yaml")
    if guardian:
        g_ids = [r["rule_id"] for r in guardian["rules"]]
        for required in (f"G-{n:02d}" for n in range(1, 13)):
            if required not in g_ids:
                errors.append(f"guardian.yaml: missing {required}")
        outcomes = set(guardian["verdict"]["outcomes"])
        for rule in guardian["rules"]:
            for out in rule.get("outcome_table", []):
                if out["outcome"] not in outcomes | {"pass"}:
                    errors.append(f"guardian.yaml: {rule['rule_id']} bad outcome {out['outcome']}")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"rulebook OK: {len(files)} files, {len(t_ids)} thresholds, {len(m_ids)} metric and concept ids")
    return 0


if __name__ == "__main__":
    sys.exit(main())
