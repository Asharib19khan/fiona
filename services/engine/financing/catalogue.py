"""Read Abdullah's financing catalogue (rulebook/financing.yaml, B14). Data only; no maths here."""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import yaml

CATALOGUE_PATH = Path(__file__).resolve().parents[3] / "rulebook" / "financing.yaml"


@cache
def load_catalogue(path: Path = CATALOGUE_PATH) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported financing catalogue schema {data.get('schema_version')!r}")
    return data


def options_for(country: str, catalogue: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cat = catalogue or load_catalogue()
    return [o for o in cat["options"] if o.get("country") == country]


def reference_rate(
    key: str | None, catalogue: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if key is None:
        return None
    cat = catalogue or load_catalogue()
    return (cat.get("market", {}).get("reference_lending_rate") or {}).get(key)


def catalogue_as_of(catalogue: dict[str, Any] | None = None) -> date:
    cat = catalogue or load_catalogue()
    return date.fromisoformat(str(cat["as_of"]))


def field_verification(option: dict[str, Any], block: dict[str, Any] | None) -> str:
    """Field-level verification overrides the pricing block, which overrides the option."""
    if isinstance(block, dict) and block.get("verification"):
        return block["verification"]
    pricing = option.get("pricing") or {}
    return pricing.get("verification") or option.get("verification") or "unverified"
