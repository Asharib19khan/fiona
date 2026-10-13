"""Deterministic identifiers shared by the generator and the importers (see FORMATS.md §1).

``source_ulid`` gives the same ULID for the same source record on every machine, so importing
a file twice, or importing overlapping statements, never creates a second event.
``data/generator/ids.py`` carries an identical copy (the generator is stdlib-only and runs
outside the engine package); a test asserts the two agree.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def encode_ulid(timestamp_ms: int, randomness: bytes) -> str:
    if not 0 <= timestamp_ms < 2**48:
        raise ValueError("timestamp out of ULID range")
    if len(randomness) != 10:
        raise ValueError("ULID randomness must be 10 bytes")
    value = (timestamp_ms << 80) | int.from_bytes(randomness, "big")
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def source_ulid(
    prefix: str, occurred_at: datetime, tenant_id: str, source_type: str, source_key: str
) -> str:
    """``prefix`` + ULID(time = occurred_at, randomness = SHA-256 of the source identity)."""
    if occurred_at.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")
    ms = (occurred_at - EPOCH) // timedelta(milliseconds=1)  # exact integer, no float
    digest = hashlib.sha256(f"{tenant_id}|{source_type}|{source_key}".encode()).digest()
    return f"{prefix}_{encode_ulid(ms, digest[:10])}"


def utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
