"""Daily model spend cap (LLM_DAILY_BUDGET_USD).

Every Claude call this service makes adds its reported cost to a per-day total kept on disk
(UTC days). Once the day's total reaches the cap, new calls are refused before Claude starts,
and the caller fails closed: a Guardian review becomes an error, which the engine records as a
CHECK_ERROR escalation. Unset means no daily cap (each run is still capped by
LLM_RUN_BUDGET_USD). A value that isn't a number is treated as 0, so a typo stops spending
instead of removing the limit.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

_lock = threading.Lock()


class BudgetExhausted(RuntimeError):
    pass


def cap() -> float | None:
    raw = os.environ.get("LLM_DAILY_BUDGET_USD", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return max(value, 0.0)


def _path() -> Path:
    root = Path(os.environ.get("FIONA_AGENT_HOME") or Path(tempfile.gettempdir()) / "fiona-agents")
    folder = root / "spend"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "guardian.json"


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _read() -> dict[str, float]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): float(v) for k, v in data.items() if isinstance(v, int | float)}


def spent_today() -> float:
    with _lock:
        return _read().get(_today(), 0.0)


def check() -> None:
    """Refuse a new call when today's spend has reached the cap."""
    limit = cap()
    if limit is None:
        return
    spent = spent_today()
    if spent >= limit:
        raise BudgetExhausted(
            f"today's model budget is used up (${spent:.2f} of ${limit:.2f}); "
            "calls resume at midnight UTC"
        )


def record(cost_usd: float | None) -> None:
    """Add one call's cost. When the CLI reports no cost, the per-run cap is counted instead."""
    if cost_usd is None:
        try:
            cost_usd = float(os.environ.get("LLM_RUN_BUDGET_USD") or 0)
        except ValueError:
            cost_usd = 0.0
    if cost_usd <= 0:
        return
    with _lock:
        data = _read()
        today = _today()
        data = {today: round(data.get(today, 0.0) + float(cost_usd), 6)}  # keep only today
        target = _path()
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, target)
