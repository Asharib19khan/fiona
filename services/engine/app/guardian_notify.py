"""Ask the Guardian service to review a proposal (engine → guardian, R8).

The engine never calls a model. After it stores a proposal and its deterministic verdict, it
tells the Guardian, which fetches the review packet itself and posts its answer back. The call
runs after the response is sent; if the Guardian is down the proposal simply keeps its
deterministic verdict with no G-12 check, and the owner sees the review as missing.
Notification is on whenever GUARDIAN_INBOUND_TOKEN is set (the Guardian refuses without it).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("engine.guardian_notify")


def enabled() -> bool:
    return bool(os.environ.get("GUARDIAN_INBOUND_TOKEN"))


def request_review(tenant_id: str, proposal_id: str) -> bool:
    token = os.environ.get("GUARDIAN_INBOUND_TOKEN")
    if not token:
        return False
    base = os.environ.get("GUARDIAN_BASE_URL") or "http://localhost:8200"
    if not base.startswith(("http://", "https://")):
        log.error("GUARDIAN_BASE_URL must be an http(s) URL")
        return False
    url = base.rstrip("/") + "/v1/guardian/review"  # scheme checked above: http(s) only
    req = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps({"tenant_id": tenant_id, "proposal_id": proposal_id}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Guardian-Inbound-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:  # noqa: S310
            return res.status == 202
    except (urllib.error.URLError, TimeoutError) as exc:
        log.warning("Guardian review of %s not requested: %s", proposal_id, exc)
        return False
