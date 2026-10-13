"""Debt-service coverage: the one DSCR implementation every lane uses.

Definitions are in rulebook/metrics.yaml (solvency.dscr, solvency.dscr_forward,
decision.max_debt_at_min_dscr). Inputs are integer minor units of one currency; ratios come
back as integer basis points (1.25x = 12500), rounded once, half away from zero, so finance QA
can recompute them with a spreadsheet's ROUND.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class Status(StrEnum):
    OK = "ok"
    NOT_COMPUTABLE = "not_computable"


@dataclass(frozen=True)
class Coverage:
    """A coverage ratio with the inputs that produced it (what explain-any-number shows)."""

    metric_id: str
    value_bp: int | None
    numerator_minor: int
    denominator_minor: int
    status: Status
    reason: str | None = None


def ratio_bp(numerator: int, denominator: int) -> int | None:
    """numerator / denominator in basis points, rounded half away from zero; None if denominator is 0."""
    if denominator == 0:
        return None
    exact = Decimal(numerator) * 10000 / Decimal(denominator)
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def debt_service(interest_minor: int, principal_minor: int) -> int:
    """Interest plus scheduled principal for the same period. Both must be non-negative."""
    if interest_minor < 0 or principal_minor < 0:
        raise ValueError("interest and principal must be non-negative amounts paid")
    return interest_minor + principal_minor


def _coverage(metric_id: str, ebitda_minor: int, service_minor: int) -> Coverage:
    value = ratio_bp(ebitda_minor, service_minor)
    if value is None:
        return Coverage(metric_id, None, ebitda_minor, service_minor, Status.NOT_COMPUTABLE, "no scheduled debt service")
    return Coverage(metric_id, value, ebitda_minor, service_minor, Status.OK)


def dscr(ebitda_minor: int, interest_minor: int, principal_minor: int) -> Coverage:
    """Trailing DSCR (solvency.dscr): EBITDA / (interest + scheduled principal), same 12 months.

    Negative EBITDA gives a negative ratio, which is meaningful (no capacity at all).
    """
    return _coverage("solvency.dscr", ebitda_minor, debt_service(interest_minor, principal_minor))


def dscr_forward(ebitda_next_12m_minor: int, existing_service_minor: int, new_service_minor: int = 0) -> Coverage:
    """Forward DSCR (solvency.dscr_forward): forecast EBITDA / (existing + new debt service)."""
    if existing_service_minor < 0 or new_service_minor < 0:
        raise ValueError("debt service must be non-negative")
    return _coverage("solvency.dscr_forward", ebitda_next_12m_minor, existing_service_minor + new_service_minor)


def max_principal_at_dscr(
    ebitda_next_12m_minor: int,
    existing_service_minor: int,
    min_dscr_bp: int,
    service_for_principal: Callable[[int], int],
    upper_bound_minor: int,
) -> int:
    """Largest principal P (minor units) with dscr_forward(EBITDA, existing, service(P)) >= min_dscr_bp.

    `service_for_principal(P)` returns the new facility's first-12-month interest plus principal
    under its own terms (built by the decisions or financing module) and must not decrease as P
    grows. Returns 0 when even existing debt is below the minimum. Binary search to 1 minor unit.
    """
    if min_dscr_bp <= 0:
        raise ValueError("min_dscr_bp must be positive")

    def passes(principal: int) -> bool:
        cov = dscr_forward(ebitda_next_12m_minor, existing_service_minor, service_for_principal(principal))
        return cov.value_bp is not None and cov.value_bp >= min_dscr_bp

    if not passes(0):
        return 0
    if passes(upper_bound_minor):
        return upper_bound_minor
    low, high = 0, upper_bound_minor  # passes(low) and not passes(high)
    while high - low > 1:
        mid = (low + high) // 2
        if passes(mid):
            low = mid
        else:
            high = mid
    return low
