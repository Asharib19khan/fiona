"""Guardian replay fixture access. Kept separate from the agents' provider code for R8."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def provider_name() -> str:
    return os.environ.get("FIONA_LLM_PROVIDER", "replay")


def planted_bill_review() -> dict[str, Any]:
    return json.loads(
        (REPO_ROOT / "packages/contracts/examples/scenarios/planted-bill-block.json").read_text(
            encoding="utf-8"
        )
    )


def guardian_rules() -> list[dict[str, str | None]]:
    """Read public rule metadata from the rulebook without importing the engine."""
    rules: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    for raw in (REPO_ROOT / "rulebook/guardian.yaml").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- rule_id: "):
            if current:
                rules.append(current)
            current = {
                "id": line.removeprefix("- rule_id: "),
                "name": None,
                "check": None,
                "threshold": None,
            }
        elif current and line.startswith("name: "):
            current["name"] = line.removeprefix("name: ")
        elif current and line.startswith("check: "):
            current["check"] = line.removeprefix("check: ")
        elif current and line.startswith("threshold: "):
            current["threshold"] = line.removeprefix("threshold: ")
    if current:
        rules.append(current)
    return rules
