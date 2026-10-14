"""Rulebook and threshold loader for Guardian checks (D5).

Loads rulebook/guardian.yaml and rulebook/thresholds.yaml once, resolves thresholds by ID,
and exposes policy version and control constants.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RULEBOOK_DIR = REPO_ROOT / "rulebook"

GUARDIAN_PATH = RULEBOOK_DIR / "guardian.yaml"
THRESHOLDS_PATH = RULEBOOK_DIR / "thresholds.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Rulebook file missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data)}")
    return data


GUARDIAN_CONFIG: dict[str, Any] = _load_yaml(GUARDIAN_PATH)
THRESHOLDS_CONFIG: dict[str, Any] = _load_yaml(THRESHOLDS_PATH)

POLICY_VERSION: str = str(GUARDIAN_CONFIG.get("policy_version", "1.0.0"))

# Threshold dictionary indexed by ID
THRESHOLDS: dict[str, dict[str, Any]] = {
    t["id"]: t for t in THRESHOLDS_CONFIG.get("thresholds", []) if "id" in t
}

# Strictness ordering: strictest first
STRICTNESS_ORDER: tuple[str, ...] = tuple(
    GUARDIAN_CONFIG.get("verdict", {}).get(
        "strictness_order", ["block", "escalate", "approve_with_conditions", "approve"]
    )
)

ACTION_TYPES: tuple[str, ...] = tuple(
    GUARDIAN_CONFIG.get(
        "action_types",
        [
            "payment",
            "bill_approval",
            "journal_adjustment",
            "send_document",
            "purchase_order",
            "reconciliation_match",
        ],
    )
)

MATERIAL_DECISION_TYPES: tuple[str, ...] = tuple(
    GUARDIAN_CONFIG.get(
        "material_decision_types_never_executable_by_agents",
        [
            "borrowing",
            "equity_issuance",
            "dividend",
            "capital_expenditure_commitment",
            "new_product_commitment",
            "technology_contract",
            "lease_signing",
        ],
    )
)

PO_EXEMPT_CATEGORIES: tuple[str, ...] = tuple(
    GUARDIAN_CONFIG.get(
        "po_exempt_categories",
        [
            "rent",
            "utilities",
            "taxes_and_duties",
            "loan_instalment",
            "payroll_related",
            "bank_charges",
            "insurance",
            "professional_fees_under_contract",
        ],
    )
)


def get_threshold(threshold_id: str) -> dict[str, Any]:
    """Resolve a threshold definition by ID from rulebook/thresholds.yaml."""
    if threshold_id not in THRESHOLDS:
        raise KeyError(f"Threshold ID {threshold_id!r} not found in {THRESHOLDS_PATH}")
    return THRESHOLDS[threshold_id]
