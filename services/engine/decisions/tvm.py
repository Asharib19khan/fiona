"""Time-value-of-money primitives shared by the decision calculators and Launch Lab.

Cash flows are one value per period; period 0 is today and usually negative.
Rates are per period. Nothing here rounds: callers round once, at the boundary.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise


def monthly_rate(annual_rate: float) -> float:
    """Convert an effective annual rate to the equivalent effective monthly rate."""
    if annual_rate <= -1:
        raise ValueError("annual rate must be greater than -100%")
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def annual_rate(monthly: float) -> float:
    """Convert an effective monthly rate to the equivalent effective annual rate."""
    if monthly <= -1:
        raise ValueError("monthly rate must be greater than -100%")
    return (1.0 + monthly) ** 12 - 1.0


def npv(rate: float, cash_flows: Sequence[float]) -> float:
    """Net present value, with cash_flows[0] undiscounted."""
    if rate <= -1:
        raise ValueError("discount rate must be greater than -100%")
    return math.fsum(cf / (1.0 + rate) ** t for t, cf in enumerate(cash_flows))


class IrrStatus(StrEnum):
    OK = "ok"
    NO_SIGN_CHANGE = "no_sign_change"  # all flows the same sign: no IRR exists
    MULTIPLE_SIGN_CHANGES = "multiple_sign_changes"  # several IRRs may exist; refuse to pick one
    NO_ROOT_FOUND = "no_root_found"


@dataclass(frozen=True)
class IrrResult:
    rate: float | None
    status: IrrStatus

    @property
    def valid(self) -> bool:
        return self.status is IrrStatus.OK


def _sign_changes(cash_flows: Sequence[float]) -> int:
    signs = [cf > 0 for cf in cash_flows if cf != 0]
    return sum(1 for a, b in pairwise(signs) if a != b)


def irr(cash_flows: Sequence[float], *, tol: float = 1e-10, max_iter: int = 300) -> IrrResult:
    """Internal rate of return per period, only when it is numerically unique.

    Descartes' rule of signs: exactly one sign change in the flows guarantees exactly one
    rate above -100%. With more than one change several rates can solve NPV = 0, so we
    report the IRR as not meaningful instead of returning an arbitrary root.
    """
    changes = _sign_changes(cash_flows)
    if changes == 0:
        return IrrResult(None, IrrStatus.NO_SIGN_CHANGE)
    if changes > 1:
        return IrrResult(None, IrrStatus.MULTIPLE_SIGN_CHANGES)

    # Search on a rescaled NPV with the same sign and root, computed in log space, so long
    # schedules near -100% or at very high rates neither underflow nor overflow.
    lo, hi = -0.9999, 1.0
    f_lo = _scaled_npv(lo, cash_flows)
    f_hi = _scaled_npv(hi, cash_flows)
    while f_lo * f_hi > 0 and hi < 1e6:
        hi *= 2.0
        f_hi = _scaled_npv(hi, cash_flows)
    if f_lo * f_hi > 0:
        return IrrResult(None, IrrStatus.NO_ROOT_FOUND)

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = _scaled_npv(mid, cash_flows)
        if f_mid == 0 or (hi - lo) / 2.0 < tol:
            return IrrResult(mid, IrrStatus.OK)
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return IrrResult((lo + hi) / 2.0, IrrStatus.OK)


def _scaled_npv(rate: float, cash_flows: Sequence[float]) -> float:
    """NPV divided by a positive constant: sum cf_t * exp(-t * ln(1 + r) - M)."""
    log_growth = math.log1p(rate)
    exponents = [-t * log_growth for t in range(len(cash_flows))]
    top = max(exponents)
    return math.fsum(cf * math.exp(e - top) for cf, e in zip(cash_flows, exponents, strict=True))


def payback_period(cash_flows: Sequence[float], rate: float = 0.0) -> float | None:
    """Periods until the cumulative (optionally discounted) cash flow first reaches zero.

    Linear interpolation inside the crossing period, so 2.5 means half-way through period 3.
    Returns None if the investment is never recovered within the flows given.
    """
    cumulative = 0.0
    for t, cf in enumerate(cash_flows):
        discounted = cf / (1.0 + rate) ** t
        previous = cumulative
        cumulative += discounted
        if cumulative >= 0:
            if t == 0:
                return 0.0
            if previous >= 0:
                continue
            return (t - 1) + (-previous / discounted)
    return None
