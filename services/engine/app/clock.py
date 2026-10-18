"""The engine's clock.

Real time by default. FIONA_NOW (an ISO 8601 UTC instant, e.g. 2026-10-22T09:00:00Z) pins it,
so a synthetic business whose data runs up to a fixed date can be demonstrated as of that date.
Logic takes the time from here (or from the `Clock` dependency), never from datetime.now().
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def now() -> datetime:
    pinned = os.environ.get("FIONA_NOW")
    if pinned:
        moment = datetime.fromisoformat(pinned.replace("Z", "+00:00"))
        return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return datetime.now(UTC)


def business_date(timezone: str) -> date:
    """Today in the tenant's time zone."""
    return now().astimezone(ZoneInfo(timezone)).date()
