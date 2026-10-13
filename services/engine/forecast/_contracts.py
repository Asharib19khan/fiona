"""Stand-ins for the shared contract models (A2), kept in one place.

When fiona-19's generated package lands, this file becomes:

    from fiona_contracts import Action, Evidence, Figure, FigureInput, Finding, Money, ...

and nothing else in the Yahya lane changes. Field names follow the blueprint and PLAN
section 3.2 ("every number is a Figure").

No floats cross the boundary. Money is integer minor units plus a currency. Every other
non-integer quantity (rate, share, probability, ratio, multiple, elasticity) is an integer
in basis points of 1: 0.235 -> 2350, a DSCR of 1.35 -> 13500, an elasticity of -1.2 -> -12000.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

from engine.forecast.money import Money

__all__ = [
    "Action",
    "Evidence",
    "Figure",
    "FigureInput",
    "Finding",
    "Money",
    "Origin",
    "Period",
    "Threshold",
    "Unit",
]


class Unit(StrEnum):
    MINOR = "minor"  # money: the amount is in `money`
    BP = "bp"  # dimensionless decimal x 10,000
    UNITS = "units"  # whole stock units
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    COUNT = "count"


class Origin(StrEnum):
    """Where an input or threshold came from."""

    USER = "user_provided"  # the owner typed it
    LEDGER = "ledger_derived"  # computed from the business's own records
    MARKET = "market_observed"  # identifiable, dated, in-date external observation
    ESTIMATE = "engine_estimate"  # computed by a stated model from other inputs
    ASSUMPTION = "assumption_unverified"  # a placeholder someone must verify
    FIGURE = "figure"  # another Figure in the same response; `ref` holds its metric_id
    STUB = "stub"  # labelled fixture value standing in for another lane's engine
    TENANT_POLICY = "tenant_policy"
    RULEBOOK = "rulebook"
    OWNER = "owner"
    DRAFT_DEFAULT = "draft_default"


class _Quantity(BaseModel):
    """Either money or an integer value with a unit, never both."""

    money: Money | None = None
    value: StrictInt | None = None
    unit: Unit

    @model_validator(mode="after")
    def _one_kind(self):
        if self.money is not None and self.value is not None:
            raise ValueError("set money or value, not both")
        if self.money is not None and self.unit is not Unit.MINOR:
            raise ValueError("money goes with unit 'minor'")
        if self.value is not None and self.unit is Unit.MINOR:
            raise ValueError("unit 'minor' needs money, not value")
        return self


class FigureInput(_Quantity):
    name: str
    origin: Origin
    metric_id: str | None = None
    ref: str | None = Field(
        None,
        description="Evidence id (event, SKU, bill, dataset row), or a metric_id when origin is 'figure'.",
    )


class Threshold(_Quantity):
    name: str
    origin: Origin
    comparison: Literal[">=", "<=", ">", "<"]
    passed: bool | None = None


class Figure(_Quantity):
    """One number the product shows, with everything needed to explain it."""

    metric_id: str = Field(
        description="Key in rulebook/metrics.yaml, e.g. 'launch.contribution_per_unit'."
    )
    label: str
    status: Literal["ok", "insufficient_data", "not_applicable"] = "ok"
    formula: str | None = None
    inputs: list[FigureInput] = Field(default_factory=list)
    thresholds: list[Threshold] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    missing: list[str] = Field(
        default_factory=list,
        description="Data that would make an insufficient_data figure computable.",
    )
    note: str | None = None

    @model_validator(mode="after")
    def _status_matches_value(self):
        has_value = self.money is not None or self.value is not None
        if self.status == "ok" and not has_value:
            raise ValueError(f"{self.metric_id}: an ok figure needs money or value")
        if self.status != "ok" and has_value:
            raise ValueError(f"{self.metric_id}: a {self.status} figure carries no value")
        if self.status == "insufficient_data" and not self.missing:
            raise ValueError(f"{self.metric_id}: say what data is missing")
        return self


class Period(BaseModel):
    start: date
    end: date


class Evidence(BaseModel):
    kind: str
    ref: str


class Action(BaseModel):
    label: str
    route: str


class Finding(BaseModel):
    """Blueprint Finding; the fields after `actions` are the proposed additive fields."""

    id: str
    source: Literal["forecast", "inventory", "launch_lab", "decisions", "financing"]
    severity: Literal["high", "medium", "low"]
    title: str
    money_at_stake: Money
    evidence: list[Evidence]
    actions: list[Action]
    type: str
    detail: str | None = None
    period: Period | None = None
    created_at: datetime
    dedupe_key: str = Field(
        description="Stable across runs, so the briefing never repeats an alert."
    )
    figures: list[Figure] = Field(default_factory=list)
