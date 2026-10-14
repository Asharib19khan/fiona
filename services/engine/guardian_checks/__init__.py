"""Deterministic Guardian checks (D5).

Standalone rulebook evaluation library with no database dependencies,
implementing rules G-01 to G-11, G-13 (Tier 1), and proposed G-14, G-15 (Tier 2).
"""

from __future__ import annotations

from engine.guardian_checks.combine import build_verdict, combine
from engine.guardian_checks.context import CheckContext
from engine.guardian_checks.rules import POLICY_VERSION
from engine.guardian_checks.run import run_deterministic_checks

__all__ = [
    "POLICY_VERSION",
    "CheckContext",
    "build_verdict",
    "combine",
    "run_deterministic_checks",
]
