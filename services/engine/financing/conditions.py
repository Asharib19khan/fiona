"""Evaluator for the rulebook condition grammar (rulebook/finance_rules.yaml, header).

    condition := {all: [...]} | {any: [...]} | {not: condition} | predicate
    predicate := {metric: id | input: path, op, value | threshold: id[.key] | rhs_metric: id}

Three-valued: a predicate whose input or metric is unknown evaluates to None, and None
propagates (all: False beats None; any: True beats None). The evaluator also reports which
inputs were missing, so the caller can say "insufficient data, need X" instead of guessing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

Lookup = Callable[[str], Any]

_MISSING = object()


@dataclass
class Evaluation:
    result: bool | None
    missing: set[str] = field(default_factory=set)
    used: dict[str, Any] = field(default_factory=dict)


def _threshold_value(ref: str, thresholds: Callable[[str], Mapping[str, Any]]) -> Any:
    tid, _, key = ref.partition(".")
    item = thresholds(tid)
    if key:
        return item[key]
    for name in ("value_bp", "value_minor", "value"):
        if name in item:
            return item[name]
    raise KeyError(f"threshold {tid} has no comparable value")


def _compare(op: str, left: Any, right: Any) -> bool:
    match op:
        case "lt":
            return left < right
        case "le":
            return left <= right
        case "gt":
            return left > right
        case "ge":
            return left >= right
        case "eq":
            return left == right
        case "ne":
            return left != right
        case "in":
            return left in right
        case "not_in":
            return left not in right
    raise ValueError(f"unknown operator {op!r}")


def evaluate(
    condition: Mapping[str, Any],
    *,
    inputs: Lookup,
    metrics: Lookup,
    thresholds: Callable[[str], Mapping[str, Any]],
) -> Evaluation:
    """Evaluate one condition. `inputs` and `metrics` return None for unknown values."""
    if "all" in condition:
        parts = [
            evaluate(c, inputs=inputs, metrics=metrics, thresholds=thresholds)
            for c in condition["all"]
        ]
        result: bool | None = (
            False
            if any(p.result is False for p in parts)
            else None
            if any(p.result is None for p in parts)
            else True
        )
        return _merge(result, parts)
    if "any" in condition:
        parts = [
            evaluate(c, inputs=inputs, metrics=metrics, thresholds=thresholds)
            for c in condition["any"]
        ]
        result = (
            True
            if any(p.result is True for p in parts)
            else None
            if any(p.result is None for p in parts)
            else False
        )
        return _merge(result, parts)
    if "not" in condition:
        inner = evaluate(condition["not"], inputs=inputs, metrics=metrics, thresholds=thresholds)
        return Evaluation(
            None if inner.result is None else not inner.result, inner.missing, inner.used
        )

    if "input" in condition:
        name, left = condition["input"], inputs(condition["input"])
    elif "metric" in condition:
        name, left = condition["metric"], metrics(condition["metric"])
    else:
        raise ValueError(f"predicate needs input or metric: {condition!r}")
    op = condition["op"]
    used = {name: left}
    if op == "is_null":
        return Evaluation(left is None, set(), used)
    if op == "not_null":
        return Evaluation(left is not None, set(), used)
    if left is None:
        return Evaluation(None, {name}, used)

    if "value" in condition:
        right = condition["value"]
    elif "threshold" in condition:
        right = _threshold_value(condition["threshold"], thresholds)
        used[condition["threshold"]] = right
    elif "rhs_metric" in condition:
        right = metrics(condition["rhs_metric"])
        used[condition["rhs_metric"]] = right
        if right is None:
            return Evaluation(None, {condition["rhs_metric"]}, used)
    else:
        raise ValueError(f"predicate needs value, threshold or rhs_metric: {condition!r}")
    return Evaluation(_compare(op, left, right), set(), used)


def _merge(result: bool | None, parts: list[Evaluation]) -> Evaluation:
    missing: set[str] = set()
    used: dict[str, Any] = {}
    for p in parts:
        missing |= p.missing
        used.update(p.used)
    return Evaluation(result, missing if result is None else set(), used)


def lookup_path(data: Mapping[str, Any]) -> Lookup:
    """Dotted-path lookup into nested mappings; missing or null gives None."""

    def get(path: str) -> Any:
        node: Any = data
        for part in path.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return node

    return get
