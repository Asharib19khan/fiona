"""Public rule metadata and authenticated labelled Guardian replay review."""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fiona_guardian.replay import guardian_rules, planted_bill_review, provider_name

router = APIRouter(tags=["guardian"])


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: str = Field(pattern=r"^prop_[A-Za-z0-9_]+$")


@router.get("/v1/guardian/rules")
def rules() -> dict[str, object]:
    return {"api_version": "v1", "policy_version": "1.0.0", "rules": guardian_rules()}


@router.post("/v1/guardian/review")
def review(
    body: ReviewRequest,
    x_guardian_inbound_token: str | None = Header(default=None),
) -> dict[str, object]:
    configured_token = os.environ.get("GUARDIAN_INBOUND_TOKEN")
    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "guardian_not_configured",
                "message": "Guardian review requires GUARDIAN_INBOUND_TOKEN.",
            },
        )
    if not x_guardian_inbound_token or not secrets.compare_digest(
        x_guardian_inbound_token, configured_token
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": "Guardian review requires its inbound service token.",
            },
        )
    if provider_name() not in ("replay", "claude_cli"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_not_configured",
                "message": "Only the labelled replay or claude_cli provider is enabled in this build.",
            },
        )
    scenario = planted_bill_review()
    if body.proposal_id != scenario["proposal"]["id"]:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "replay_miss",
                "message": "No labelled Guardian replay matches this proposal.",
            },
        )
    verdict = scenario["verdict"]
    verdict["meta"] = {**verdict.get("meta", {}), "replayed": True, "model": "replay"}
    return {"api_version": "v1", "verdict": verdict}
