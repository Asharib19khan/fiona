"""Stand-ins for the shared contract models (A2), mirroring engine.forecast._contracts field for
field so the two lanes emit identical Figures. When fiona-19's generated package lands this file
becomes `from fiona_contracts import ...` and nothing else here changes.

No floats cross the boundary: money is integer minor units plus a currency; every other
non-integer quantity is an integer in basis points (a DSCR of 1.35 -> 13500).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

__all__ = ["Figure", "FigureInput", "Money", "Origin", "Threshold", "Unit"]


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    minor: StrictInt
    currency: str


class Unit(StrEnum):
    MINOR = "minor"
    BP = "bp"
    UNITS = "units"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    COUNT = "count"


class Origin(StrEnum):
    USER = "user_provided"
    LEDGER = "ledger_derived"
    MARKET = "market_observed"
    ESTIMATE = "engine_estimate"
    ASSUMPTION = "assumption_unverified"
    FIGURE = "figure"
    STUB = "stub"
    TENANT_POLICY = "tenant_policy"
    RULEBOOK = "rulebook"
    OWNER = "owner"
    DRAFT_DEFAULT = "draft_default"


class _Quantity(BaseModel):
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
    ref: str | None = None


class Threshold(_Quantity):
    name: str
    origin: Origin
    comparison: Literal[">=", "<=", ">", "<"]
    passed: bool | None = None


class Figure(_Quantity):
    metric_id: str
    label: str
    status: Literal["ok", "insufficient_data", "not_applicable"] = "ok"
    formula: str | None = None
    inputs: list[FigureInput] = Field(default_factory=list)
    thresholds: list[Threshold] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
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
