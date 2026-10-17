"""Labelled replay answers for the public demo and local no-key development path.

This module intentionally does not invoke a model or any engine endpoint. A provider other than
``replay`` is reported as unavailable until its separately audited implementation is added.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


class ReplayUnavailable(RuntimeError):
    """The requested prompt has no recorded synthetic response."""


@dataclass(frozen=True)
class ReplayAnswer:
    run_id: str
    answer: str
    prompt_version: str = "agents/ask/replay/v1"


def provider_name() -> str:
    return os.environ.get("FIONA_LLM_PROVIDER", "replay")


def replay_answer(question: str) -> ReplayAnswer:
    normalized = " ".join(question.lower().split())
    if not normalized:
        raise ReplayUnavailable("A question is required.")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    if "cash" in normalized or "forecast" in normalized:
        answer = "The labelled Seed-42 replay shows cash below the owner buffer in week 7. Open the cash forecast to inspect its synthetic assumptions."
    elif "finance" in normalized or "loan" in normalized:
        answer = "The labelled replay can describe financing comparisons, but it does not submit an application or create a commitment."
    else:
        answer = "This is a labelled replay response. It can explain the synthetic demo, but it cannot change records, approve a proposal, or move money."
    return ReplayAnswer(run_id=f"run_replay_{digest}", answer=answer)
