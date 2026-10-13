"""Lane-local payload models and constructors shared by forecast, decisions and financing.

The shared contract models (Figure, Finding, Money, ...) come from `_contracts`; this module
adds the response envelope, decision-rule checks and "insufficient data" notes, plus small
constructors that take engine floats and round them exactly once.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from engine.forecast._contracts import Figure, FigureInput, Origin, Threshold, Unit
from engine.forecast.money import round_minor, to_money

API_VERSION = "v1"


class Envelope(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    mode: Literal["mock", "live"]
    tenant_id: str
    generated_at: datetime


class RuleCheck(BaseModel):
    """One transparent decision rule and how this case fared against it."""

    rule_id: str
    description: str
    metric_id: str
    threshold: Threshold
    passed: bool | None = Field(description="None when the figure could not be computed.")
    hard: bool = Field(True, description="Hard rules gate the decision; soft rules set confidence.")


class InsufficientData(BaseModel):
    """'Insufficient data, need X' instead of a guess."""

    need: str
    why: str
    blocking: bool
    metric_ids: list[str] = Field(default_factory=list)


def to_bp(fraction: float) -> int:
    return round_minor(fraction * 10_000)


def money_figure(metric_id: str, label: str, amount_minor: float, currency: str, **kw) -> Figure:
    return Figure(
        metric_id=metric_id,
        label=label,
        money=to_money(amount_minor, currency),
        unit=Unit.MINOR,
        **kw,
    )


def value_figure(metric_id: str, label: str, value: float, unit: Unit, **kw) -> Figure:
    return Figure(metric_id=metric_id, label=label, value=round_minor(value), unit=unit, **kw)


def bp_figure(metric_id: str, label: str, fraction: float, **kw) -> Figure:
    return Figure(metric_id=metric_id, label=label, value=to_bp(fraction), unit=Unit.BP, **kw)


def money_input(name: str, amount_minor: float, currency: str, origin: Origin, **kw) -> FigureInput:
    return FigureInput(
        name=name, money=to_money(amount_minor, currency), unit=Unit.MINOR, origin=origin, **kw
    )


def value_input(name: str, value: float, unit: Unit, origin: Origin, **kw) -> FigureInput:
    return FigureInput(name=name, value=round_minor(value), unit=unit, origin=origin, **kw)


def bp_input(name: str, fraction: float, origin: Origin, **kw) -> FigureInput:
    return FigureInput(name=name, value=to_bp(fraction), unit=Unit.BP, origin=origin, **kw)


def figure_ref(figure: Figure, name: str | None = None) -> FigureInput:
    """Use one Figure as an input of another, so explain-any-number can drill down."""
    return FigureInput(
        name=name or figure.metric_id,
        money=figure.money,
        value=figure.value,
        unit=figure.unit,
        origin=Origin.FIGURE,
        metric_id=figure.metric_id,
        ref=figure.metric_id,
    )


def bp_threshold(name: str, fraction: float, origin: Origin, comparison, passed=None) -> Threshold:
    return Threshold(
        name=name,
        value=to_bp(fraction),
        unit=Unit.BP,
        origin=origin,
        comparison=comparison,
        passed=passed,
    )


def money_threshold(
    name: str, amount_minor: float, currency: str, origin: Origin, comparison, passed=None
) -> Threshold:
    return Threshold(
        name=name,
        money=to_money(amount_minor, currency),
        unit=Unit.MINOR,
        origin=origin,
        comparison=comparison,
        passed=passed,
    )


def stable_id(prefix: str, *parts: str) -> str:
    """Deterministic ULID-shaped id (Crockford base32, 26 chars) from the given parts."""
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    number = int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:17], "big") >> 6
    chars = []
    for _ in range(26):
        number, rem = divmod(number, 32)
        chars.append(alphabet[rem])
    return f"{prefix}_{''.join(reversed(chars))}"
