"""The Guardian's two calls to the engine: fetch the review packet, post the review.

The Guardian authenticates as itself (role guardian), never as the agent that proposed. With
INTERNAL_JWT_SECRET set it signs a 60-second internal token; the local mock engine reads the
tenant and caller headers instead.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote


class EngineError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"engine {status}: {message}")
        self.status = status


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(tenant_id: str) -> str | None:
    secret = os.environ.get("INTERNAL_JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        return None
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    claims = {
        "sub": "guardian",
        "role": "guardian",
        "tenant_id": tenant_id,
        "aud": "fiona-engine",
        "iat": now,
        "exp": now + 60,
    }
    body = _b64(json.dumps(claims).encode())
    signature = hmac.new(
        secret.encode("utf-8"), f"{header}.{body}".encode("ascii"), hashlib.sha256
    ).digest()
    return f"{header}.{body}.{_b64(signature)}"


def _request(
    method: str, path: str, tenant_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    base = os.environ.get("ENGINE_BASE_URL") or "http://localhost:8000"
    if not base.startswith(("http://", "https://")):
        raise EngineError(500, "ENGINE_BASE_URL must be an http(s) URL")
    headers = {
        "Accept": "application/json",
        "X-Fiona-Tenant": tenant_id,
        "X-Fiona-Agent": "guardian",
    }
    token = _token(tenant_id)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    url = base.rstrip("/") + path  # scheme checked above: http(s) only
    req = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode("utf-8"))["error"]["message"]
        except Exception:
            message = exc.reason
        raise EngineError(exc.code, str(message)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise EngineError(503, f"engine unreachable: {exc}") from exc


def review_packet(tenant_id: str, proposal_id: str) -> dict[str, Any]:
    return _request("GET", f"/v1/proposals/{quote(proposal_id)}/review-packet", tenant_id)


def post_review(tenant_id: str, proposal_id: str, review: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", f"/v1/proposals/{quote(proposal_id)}/review", tenant_id, review)
