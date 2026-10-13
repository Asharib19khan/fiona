"""Rank and de-duplicate findings from every Yahya-lane engine (task Y6)."""

from __future__ import annotations

from collections.abc import Iterable

from engine.forecast._contracts import Finding

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def rank_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Highest money at stake first, severity breaking ties; one finding per dedupe_key.

    When two findings share a dedupe_key the newer one wins, so a re-run updates an alert
    instead of repeating it.
    """
    latest: dict[str, Finding] = {}
    for f in findings:
        kept = latest.get(f.dedupe_key)
        if kept is None or f.created_at >= kept.created_at:
            latest[f.dedupe_key] = f
    return sorted(
        latest.values(),
        key=lambda f: (-f.money_at_stake.minor, SEVERITY_ORDER[f.severity], f.dedupe_key),
    )
