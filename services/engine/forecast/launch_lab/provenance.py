"""Where every Launch Lab input came from, so no figure is silently invented."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Source(StrEnum):
    USER = "user_provided"  # the owner typed it
    LEDGER = "ledger_derived"  # computed from the business's own records
    MARKET = "market_observed"  # an identifiable external observation, dated and in date
    ESTIMATE = "engine_estimate"  # computed by a stated model from other inputs
    ASSUMPTION = "assumption_unverified"  # a placeholder that someone must verify


class MarketKind(StrEnum):
    OBSERVATION = "verified_observation"
    TREND = "historical_trend"
    FORECAST = "forecast"
    UNAVAILABLE = "unavailable"


class ResolvedInput(BaseModel):
    """One input to the model, with its value, origin and the reasoning behind it."""

    name: str
    value: float | int | str | list[float] | None
    unit: str
    source: Source
    basis: str = Field(description="How the value was obtained, in one sentence.")
    refs: list[str] = Field(
        default_factory=list, description="Evidence references, e.g. ledger SKUs or dataset ids."
    )
    as_of: date | None = None
    needs_verification: bool = False


class DataGap(BaseModel):
    """An input that is missing or weak, what it affects, and the question that would fix it."""

    field: str
    blocking: bool
    impact: str
    question: str
