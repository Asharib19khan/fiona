"""Launch Lab thresholds and modelling assumptions.

The rulebook is data, not code: values come from `rulebook/launch_lab.yaml` (Abdullah's
lane) when it exists, then the owner's own constraints override them. The defaults below
are drafts pending rulebook B1 and are reported as such in every result.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class PolicySource(StrEnum):
    RULEBOOK = "rulebook"
    OWNER = "owner"
    DRAFT_DEFAULT = "draft_default"


class DemandSigma(BaseModel):
    """Spread (log-normal sigma) of the demand level, by how strong the demand evidence is."""

    own_history: float = 0.20
    comparable_history: float = 0.35
    user_estimate: float = 0.50


class LaunchPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Decision thresholds
    min_contribution_margin: float = Field(0.20, ge=0, lt=1)
    breakeven_horizon_months: int = Field(6, ge=1, le=60)
    launch_min_prob_breakeven: float = Field(0.70, ge=0, le=1)
    max_loss_probability: float = Field(0.30, ge=0, le=1)
    max_investment_minor: int | None = None
    min_cash_reserve_minor: int | None = None
    target_profit_minor: int | None = None

    # Inventory planning
    service_level: float = Field(0.90, gt=0.5, lt=1)
    review_months: int = Field(1, ge=1, le=6)
    pilot_cover_months: int = Field(1, ge=1, le=6)

    # Demand model
    launch_ramp: list[float] = Field(default_factory=lambda: [0.60, 0.85, 1.0])
    demand_sigma: DemandSigma = Field(default_factory=DemandSigma)
    monthly_noise_sigma: float = Field(0.15, ge=0, le=1)
    elasticity_scenarios: dict[str, float] = Field(
        default_factory=lambda: {
            "low_sensitivity": -0.5,
            "medium_sensitivity": -1.2,
            "high_sensitivity": -2.0,
        }
    )

    # Uncertainty and scenario construction
    cost_shock: tuple[float, float, float] = (-0.05, 0.0, 0.10)  # triangular low, mode, high
    max_extra_discount: float = Field(0.10, ge=0, lt=1)
    return_rate_spread: float = Field(0.5, ge=0, le=1)
    low_case_cost_change: float = 0.05
    low_case_extra_discount: float = 0.05
    low_case_return_multiplier: float = 1.25
    simulation_runs: int = Field(5000, ge=200, le=50000)
    seed: int = 42

    # Money and data
    unsold_recovery_rate: float = Field(0.50, ge=0, le=1)
    cost_of_capital_annual: float = Field(0.15, gt=-1)
    market_data_max_age_days: int = Field(180, ge=1)
    sensitivity_swing: float = Field(0.20, gt=0, lt=1)


OWNER_OVERRIDABLE = (
    "min_contribution_margin",
    "breakeven_horizon_months",
    "launch_min_prob_breakeven",
    "max_loss_probability",
    "max_investment_minor",
    "min_cash_reserve_minor",
    "target_profit_minor",
)

DEFAULT_RULEBOOK_PATH = Path(__file__).resolve().parents[4] / "rulebook" / "launch_lab.yaml"


def _from_bp(value: Any) -> Any:
    """Basis points to fractions, through lists and mappings (2000 -> 0.2)."""
    if isinstance(value, bool):
        raise ValueError("basis-point values must be integers")
    if isinstance(value, int):
        return value / 10_000
    if isinstance(value, list | tuple):
        return [_from_bp(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_bp(v) for k, v in value.items()}
    raise ValueError(f"basis-point values must be integers, got {value!r}")


def _normalise_keys(section: dict[str, Any]) -> dict[str, Any]:
    """Rulebook and API payloads write rates as `<name>_bp` integers; the model uses fractions."""
    out: dict[str, Any] = {}
    for key, value in section.items():
        if key.endswith("_bp"):
            out[key.removesuffix("_bp")] = _from_bp(value)
        else:
            out[key] = value
    return out


def load_policy(
    rulebook_path: Path | None = DEFAULT_RULEBOOK_PATH,
    owner_overrides: dict[str, Any] | None = None,
) -> tuple[LaunchPolicy, dict[str, PolicySource]]:
    """Merge draft defaults, the rulebook file and the owner's constraints, in that order.

    Both layers may use `_bp` keys (`min_contribution_margin_bp: 2000`). Returns the policy
    and, for every field, which layer supplied its value.
    """
    values: dict[str, Any] = {}
    sources = {name: PolicySource.DRAFT_DEFAULT for name in LaunchPolicy.model_fields}

    if rulebook_path is not None and rulebook_path.is_file():
        loaded = yaml.safe_load(rulebook_path.read_text(encoding="utf-8")) or {}
        section = _normalise_keys(loaded.get("launch_lab", loaded))
        unknown = set(section) - set(LaunchPolicy.model_fields)
        if unknown:
            raise ValueError(f"unknown launch_lab rulebook keys: {sorted(unknown)}")
        values.update(section)
        sources.update({key: PolicySource.RULEBOOK for key in section})

    for key, value in _normalise_keys(owner_overrides or {}).items():
        if key not in OWNER_OVERRIDABLE:
            raise ValueError(f"owner cannot override {key!r}")
        if value is not None:
            values[key] = value
            sources[key] = PolicySource.OWNER

    return LaunchPolicy(**values), sources
