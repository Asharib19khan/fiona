"""Deterministic building blocks: integer money, calendar, seeded randomness, IDs, IBANs.

Only integer arithmetic touches money. Randomness comes from named streams derived from the
seed, so adding a new stream never shifts the numbers an existing one produces.
"""

from __future__ import annotations

import calendar
import hashlib
import random
from datetime import UTC, date, datetime, timedelta

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------- money (integer minor units)
def div_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounding half away from zero."""
    quotient, remainder = divmod(abs(numerator), denominator)
    if 2 * remainder >= denominator:
        quotient += 1
    return quotient if numerator >= 0 else -quotient


def tax_on(base_minor: int, rate_bp: int) -> int:
    """Tax added on top of a tax-exclusive amount."""
    return div_half_up(base_minor * rate_bp, 10_000)


def tax_within(gross_minor: int, rate_bp: int) -> int:
    """Tax contained in a tax-inclusive amount."""
    return div_half_up(gross_minor * rate_bp, 10_000 + rate_bp)


def fmt_money(minor: int, minor_unit: int = 2) -> str:
    sign = "-" if minor < 0 else ""
    major, cents = divmod(abs(minor), 10**minor_unit)
    return f"{sign}{major:,}.{cents:0{minor_unit}d}"


# ---------------------------------------------------------------- calendar
def add_months(day: date, months: int) -> date:
    years, month_index = divmod(day.month - 1 + months, 12)
    year, month = day.year + years, month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def days(start: date, end: date) -> list[date]:
    return [start + timedelta(n) for n in range((end - start).days + 1)]


def is_business_day(day: date) -> bool:
    # ASSUMPTION: banks settle Monday to Friday; public holidays are added in D2.
    return day.weekday() < 5


def next_business_day(day: date, n: int = 1) -> date:
    while n > 0:
        day += timedelta(1)
        if is_business_day(day):
            n -= 1
    return day


def on_or_before_business_day(day: date) -> date:
    while not is_business_day(day):
        day -= timedelta(1)
    return day


def nth_business_day_of_month(year: int, month: int, n: int) -> date:
    day = date(year, month, 1)
    while not is_business_day(day):
        day += timedelta(1)
    return next_business_day(day, n - 1) if n > 1 else day


def local_time(day: date, minute_of_day: int, second: int, utc_offset_hours: int) -> datetime:
    local = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(
        minutes=minute_of_day, seconds=second
    )
    return local - timedelta(hours=utc_offset_hours)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- randomness
def stream(seed: int, name: str) -> random.Random:
    """An independent, reproducible random stream for one part of the simulation."""
    digest = hashlib.sha256(f"{seed}:{name}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311 (seeded simulation, not crypto)


# ---------------------------------------------------------------- identifiers
def encode_ulid(timestamp_ms: int, randomness: bytes) -> str:
    value = (timestamp_ms << 80) | int.from_bytes(randomness, "big")
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def source_ulid(
    prefix: str, occurred_at: datetime, tenant_id: str, source_type: str, source_key: str
) -> str:
    """Same rule as engine/ledger/ids.py (FORMATS.md §1). A test asserts the two agree."""
    ms = (occurred_at - EPOCH) // timedelta(milliseconds=1)
    digest = hashlib.sha256(f"{tenant_id}|{source_type}|{source_key}".encode()).digest()
    return f"{prefix}_{encode_ulid(ms, digest[:10])}"


class IdAllocator:
    """Sequential readable IDs (``bill_1001``) that skip IDs reserved for planted records."""

    def __init__(
        self, prefix: str, start: int, width: int, reserved: set[str] | None = None
    ) -> None:
        self.prefix, self.next, self.width = prefix, start, width
        self.reserved = reserved or set()

    def take(self) -> str:
        while True:
            candidate = f"{self.prefix}_{self.next:0{self.width}d}"
            self.next += 1
            if candidate not in self.reserved:
                return candidate


# ---------------------------------------------------------------- synthetic IBANs
def iban(country: str, bank_code: str, account_digits: str) -> str:
    """ISO 13616 IBAN with valid mod-97 check digits."""
    bban = bank_code + account_digits
    rearranged = bban + country + "00"
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    check = 98 - int(numeric) % 97
    return f"{country}{check:02d}{bban}"


def iban_is_valid(value: str) -> bool:
    rearranged = value[4:] + value[:4]
    return int("".join(str(int(ch, 36)) for ch in rearranged)) % 97 == 1


# ---------------------------------------------------------------- v1: calendar with bank holidays
class Calendar:
    """Business days are Monday to Friday, minus the persona's bank holidays."""

    def __init__(self, holidays: list[str]) -> None:
        self.holidays = {date.fromisoformat(h) for h in holidays}

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def next_business_day(self, day: date, n: int = 1) -> date:
        while n > 0:
            day += timedelta(1)
            if self.is_business_day(day):
                n -= 1
        return day

    def on_or_before(self, day: date) -> date:
        while not self.is_business_day(day):
            day -= timedelta(1)
        return day

    def on_or_after(self, day: date) -> date:
        while not self.is_business_day(day):
            day += timedelta(1)
        return day

    def nth_business_day(self, year: int, month: int, n: int) -> date:
        day = self.on_or_after(date(year, month, 1))
        return self.next_business_day(day, n - 1) if n > 1 else day


def month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def compound_ppm(steps: int, rate_ppm: int) -> int:
    """(1 + rate)^steps in parts per million, by integer steps (negative steps divide)."""
    factor = 1_000_000
    for _ in range(abs(steps)):
        factor = (
            factor * (1_000_000 + rate_ppm) // 1_000_000
            if steps > 0
            else factor * 1_000_000 // (1_000_000 + rate_ppm)
        )
    return factor


def subtotal_for_total(total_minor: int, rate_bp: int) -> int:
    """Largest subtotal whose total (subtotal + half-up tax) does not exceed the target total."""
    subtotal = total_minor * 10_000 // (10_000 + rate_bp)
    while subtotal + tax_on(subtotal + 1, rate_bp) + 1 <= total_minor:
        subtotal += 1
    while subtotal + tax_on(subtotal, rate_bp) > total_minor:
        subtotal -= 1
    return subtotal


def lines_for_total(
    target_total: int, rate_bp: int, unit_minor: int, *, sku: str | None, description: str
) -> list[dict]:
    """Lines whose subtotal plus GST is as close to `target_total` as integer tax allows.

    Some totals are unreachable (subtotal + round_half_up(18 %) skips values); the result is then
    the nearest reachable total above the target. A balancing line carries the remainder.
    """
    subtotal = subtotal_for_total(target_total, rate_bp)
    if subtotal + tax_on(subtotal, rate_bp) != target_total:
        subtotal += 1  # unreachable target: nearest total above it
    qty = max(1, subtotal * 97 // 100 // unit_minor)
    lines = [
        {
            "sku": sku,
            "description": description,
            "qty": qty,
            "unit_price_minor": unit_minor,
            "line_total_minor": qty * unit_minor,
        }
    ]
    remainder = subtotal - qty * unit_minor
    if remainder > 0:
        lines.append(
            {
                "sku": None,
                "description": "Freight and handling",
                "qty": 1,
                "unit_price_minor": remainder,
                "line_total_minor": remainder,
            }
        )
    return lines
