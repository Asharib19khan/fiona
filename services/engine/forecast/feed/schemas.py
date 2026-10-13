"""Payloads for `GET /v1/forecast/findings`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from engine.forecast._contracts import Finding
from engine.forecast.figures import Envelope


class SourceStatus(BaseModel):
    """Whether each producing engine contributed, so one failure never hides the others."""

    source: Literal["forecast", "inventory", "launch_lab", "decisions", "financing"]
    status: Literal["ok", "stale", "unavailable"]
    run_id: str | None = None
    generated_at: datetime | None = None
    note: str | None = None


class FindingsResponse(Envelope):
    ranked_by: Literal["money_at_stake"] = "money_at_stake"
    findings: list[Finding] = Field(
        description="Highest money at stake first; severity breaks ties."
    )
    sources: list[SourceStatus]
