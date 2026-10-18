"""How an agent's tools reach the engine: as that agent, through the engine's public API.

With INTERNAL_JWT_SECRET set (live), every call carries a 60-second token naming the tenant and
the agent (role agent), so the engine knows which agent proposed what and refuses anything an
agent may not do (deciding, proposing as another agent). The local mock engine reads the same
facts from headers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import httpx


class EngineError(RuntimeError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def agent_token(tenant_id: str, agent: str, *, now: int | None = None) -> str | None:
    secret = os.environ.get("INTERNAL_JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        return None
    issued = int(time.time()) if now is None else now
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    claims = {
        "sub": f"agt_{agent}",
        "role": "agent",
        "agent": agent,
        "tenant_id": tenant_id,
        "aud": "fiona-engine",
        "iat": issued,
        "exp": issued + 60,
    }
    body = _b64(json.dumps(claims).encode())
    signature = hmac.new(
        secret.encode("utf-8"), f"{header}.{body}".encode("ascii"), hashlib.sha256
    ).digest()
    return f"{header}.{body}.{_b64(signature)}"


class Engine:
    """A small synchronous client bound to one tenant and one agent."""

    def __init__(self, tenant_id: str, agent: str, *, base_url: str | None = None) -> None:
        self.tenant_id = tenant_id
        self.agent = agent
        self.base_url = (
            base_url or os.environ.get("ENGINE_BASE_URL") or "http://localhost:8000"
        ).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"X-Fiona-Tenant": self.tenant_id, "X-Fiona-Agent": self.agent}
        token = agent_token(self.tenant_id, self.agent)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        try:
            res = httpx.request(
                method,
                self.base_url + path,
                json=json_body,
                params=params,
                headers=self._headers(),
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise EngineError(503, "engine_unreachable", str(exc)) from exc
        try:
            data = res.json()
        except ValueError as exc:
            raise EngineError(res.status_code, "bad_response", res.text[:200]) from exc
        if res.status_code >= 400:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            raise EngineError(
                res.status_code,
                str(err.get("code", "error")),
                str(err.get("message", res.text[:200])),
            )
        return data

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Any = None) -> dict[str, Any]:
        return self.request("POST", path, json_body=body if body is not None else {})
