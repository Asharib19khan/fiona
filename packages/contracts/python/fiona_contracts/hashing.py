"""Canonical JSON (RFC 8785, for the value types contracts use) and the verdict hash (CG-16).

verdict_hash = "sha256:" + hex(SHA-256(canonical JSON of the verdict without verdict_hash)).
Contracts never carry floats (money is integer minor units, ratios are basis points), so a float
is refused rather than risk a number-formatting mismatch between Python and TypeScript.
packages/contracts/src/hash.ts implements the same function; both are tested on the same example.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def _check(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError(
            "Canonical JSON refuses floats: contracts use integers (minor units, basis points)."
        )
    if isinstance(value, Mapping):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError("Object keys must be strings.")
            _check(v)
    elif isinstance(value, list | tuple):
        for v in value:
            _check(v)


def canonical_json(value: Any) -> str:
    """Sorted keys, no whitespace, UTF-8 text. Matches RFC 8785 for strings, integers, booleans and null."""
    _check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def verdict_hash(verdict: Mapping[str, Any]) -> str:
    """Hash of a verdict (a dict, e.g. `Verdict.model_dump(mode="json", exclude_none=True)`)."""
    body = {k: v for k, v in verdict.items() if k != "verdict_hash"}
    return "sha256:" + hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
