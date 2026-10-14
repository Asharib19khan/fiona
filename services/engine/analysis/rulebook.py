"""Read thresholds and rules from rulebook/ (the rulebook is data, not code).

Only the Abdullah lane edits those files; this module never hard-codes a threshold value.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

RULEBOOK_DIR = Path(__file__).resolve().parents[3] / "rulebook"


@cache
def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((RULEBOOK_DIR / name).read_text(encoding="utf-8"))


def threshold(threshold_id: str) -> dict[str, Any]:
    for item in _load("thresholds.yaml")["thresholds"]:
        if item["id"] == threshold_id:
            return item
    raise KeyError(f"unknown threshold {threshold_id}")


def bands_bp(threshold_id: str, industry: str | None = None) -> dict[str, int]:
    """A threshold's bands in bp, with the industry override applied when one exists.

    Industry overrides use `<key>_bp` names (e.g. `healthy_min_bp`); the base uses `bands_bp`.
    """
    item = threshold(threshold_id)
    bands = dict(item.get("bands_bp", {}))
    override = (item.get("industry_overrides") or {}).get(industry or "", {})
    for key, value in override.items():
        if key.endswith("_bp") and isinstance(value, int):
            bands[key[: -len("_bp")]] = value
    return bands


def value_bp(threshold_id: str) -> int:
    return int(threshold(threshold_id)["value_bp"])


def value(threshold_id: str) -> Any:
    return threshold(threshold_id)["value"]


def stage_patterns() -> list[dict[str, Any]]:
    return _load("finance_rules.yaml")["stage"]["patterns"]


def stage_distortion_parameters() -> dict[str, Any]:
    rules = _load("finance_rules.yaml")["stage"]["rules"]
    return next(r for r in rules if r["rule_id"] == "STG-05")["parameters"]


def tax_rate_bp(country: str) -> int | None:
    path = RULEBOOK_DIR / "country_packs" / f"{country}.yaml"
    if not path.is_file():
        return None
    return int(
        yaml.safe_load(path.read_text(encoding="utf-8"))["tax"]["corporate_tax_rate_bp"]["value"]
    )
