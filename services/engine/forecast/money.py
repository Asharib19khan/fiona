"""Money at the engine boundary: an integer in minor units plus an ISO 4217 code.

Inside the engine amounts are floats in minor units so the maths stays simple and
vectorisable; they are rounded exactly once, when a result leaves the engine. Rounding is
half away from zero, the same as a spreadsheet's ROUND, so finance QA can recompute every
figure by hand.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator

# Minor-unit exponents (ISO 4217) for the currencies Fiona's tenants use.
MINOR_UNIT_EXPONENT: dict[str, int] = {
    "PKR": 2,
    "CNY": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AED": 2,
    "SAR": 2,
    "HKD": 2,
    "JPY": 0,
}


class Money(BaseModel):
    """`{ "minor": 18450000, "currency": "PKR" }`. Floats are rejected, never coerced."""

    model_config = ConfigDict(frozen=True)

    minor: StrictInt
    currency: str

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        code = value.upper()
        if code not in MINOR_UNIT_EXPONENT:
            raise ValueError(f"unsupported currency {value!r}")
        return code


def round_minor(amount: float) -> int:
    """Round a minor-unit amount to an integer, half away from zero."""
    if not math.isfinite(amount):
        raise ValueError(f"cannot round non-finite amount {amount!r}")
    return int(Decimal(repr(float(amount))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_money(amount_minor: float, currency: str) -> Money:
    return Money(minor=round_minor(amount_minor), currency=currency)


def major_to_minor(amount_major: float | str, currency: str) -> int:
    """Convert a display amount (e.g. 3500.50 PKR) to integer minor units."""
    exponent = MINOR_UNIT_EXPONENT[currency.upper()]
    scaled = Decimal(str(amount_major)) * (Decimal(10) ** exponent)
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))
