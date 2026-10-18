"""Guardian endpoints: public rule metadata, and the adversarial review of any proposal.

The engine calls POST /v1/guardian/review with its inbound service token after it stores a
proposal and its deterministic verdict. The Guardian then fetches the review packet itself,
runs the reviewer in its own Claude process, and posts the answer back; the engine records the
G-12 check as a new verdict. The call returns 202 at once unless `wait` is set.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fiona_guardian import engine_client, reviewer
from fiona_guardian.replay import guardian_rules

router = APIRouter(tags=["guardian"])
log = logging.getLogger("fiona_guardian.api")

# Opus runs are heavy; at most this many reviews run at once, the rest wait their turn.
_slots = threading.BoundedSemaphore(int(os.environ.get("GUARDIAN_MAX_CONCURRENT", "2")))


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(pattern=r"^ten_[a-z0-9_]{1,60}$")
    proposal_id: str = Field(pattern=r"^prop_[A-Za-z0-9_]+$")


@router.get("/v1/guardian/rules")
def rules() -> dict[str, object]:
    return {"api_version": "v1", "policy_version": "1.0.0", "rules": guardian_rules()}


def _authorise(token: str | None) -> None:
    configured = os.environ.get("GUARDIAN_INBOUND_TOKEN")
    if not configured:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "guardian_not_configured",
                "message": "Guardian review requires GUARDIAN_INBOUND_TOKEN.",
            },
        )
    if not token or not secrets.compare_digest(token, configured):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": "Guardian review requires its inbound service token.",
            },
        )


def run_review(tenant_id: str, proposal_id: str) -> dict[str, Any] | None:
    """Fetch, review, record. Returns the engine's new verdict, or None when nothing was recorded."""
    with _slots:
        try:
            packet = engine_client.review_packet(tenant_id, proposal_id)
        except engine_client.EngineError as exc:
            log.error("review packet for %s unavailable: %s", proposal_id, exc)
            return None
        if not packet.get("review_required"):
            return None
        answer = reviewer.review(packet)
        try:
            recorded = engine_client.post_review(
                tenant_id,
                proposal_id,
                {"reviewed_verdict_id": packet["reviewed_verdict_id"], **answer},
            )
        except engine_client.EngineError as exc:
            # 409: a newer verdict arrived while we reviewed; that verdict gets its own review.
            log.error("review for %s not recorded: %s", proposal_id, exc)
            return None
        return recorded.get("verdict")


@router.post("/v1/guardian/review", status_code=202)
def review(
    body: ReviewRequest,
    background: BackgroundTasks,
    wait: bool = Query(default=False),
    x_guardian_inbound_token: str | None = Header(default=None),
) -> dict[str, object]:
    _authorise(x_guardian_inbound_token)
    if wait:
        verdict = run_review(body.tenant_id, body.proposal_id)
        return {
            "api_version": "v1",
            "status": "recorded" if verdict else "not_recorded",
            "verdict": verdict,
        }
    background.add_task(run_review, body.tenant_id, body.proposal_id)
    return {"api_version": "v1", "status": "accepted", "proposal_id": body.proposal_id}
