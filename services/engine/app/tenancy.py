"""The tenant for the current request (R15).

The tenant is injected by the server. It is never read from a request body, a query string or
any URL the user can edit. Endpoints take it as a dependency:

    from engine.app.tenancy import TenantId

    @router.get("/v1/forecast/cash")
    def cash(tenant_id: TenantId, weeks: int = 13) -> ...: ...

Mock mode (`FIONA_MODE=mock`, the default) trusts the `X-Fiona-Tenant` header, so lanes can test
both personas, and falls back to `DEMO_TENANT_ID`. In live mode the tenant will come from the
verified internal token (the BFF's 60-second JWT in A3, or the agents' service token in A4).
Until that lands, live mode fails closed with 401 (R9).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from engine.app.errors import ApiError

TENANT_HEADER = "X-Fiona-Tenant"
DEFAULT_DEMO_TENANT = "ten_karachi_apparel"
_TENANT_ID = re.compile(r"^ten_[a-z0-9_]{1,60}$")


def verify_internal_token(
    token: str, expected_aud: str = "fiona-engine", *, now: int | None = None
) -> str:
    """The tenant from a verified internal token."""
    return verify_internal_claims(token, expected_aud, now=now)["tenant_id"]


def verify_internal_claims(
    token: str, expected_aud: str = "fiona-engine", *, now: int | None = None
) -> dict:
    """Every claim of a verified internal token (signature, lifetime <= 60 s, audience, tenant)."""
    secret = os.environ.get("INTERNAL_JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise ApiError(
            401,
            "unauthenticated",
            "Internal authentication is not configured.",
        )
    parts = token.split(".")
    if len(parts) != 3:
        raise ApiError(401, "unauthenticated", "Malformed bearer token.")
    try:
        header_bytes = base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4))
        payload_bytes = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
    except Exception:
        raise ApiError(401, "unauthenticated", "Malformed bearer token.") from None

    expected_sig = hmac.new(
        secret.encode("utf-8"), f"{parts[0]}.{parts[1]}".encode("ascii"), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(parts[2], sig_b64):
        raise ApiError(401, "unauthenticated", "Invalid bearer token signature.")

    try:
        header = json.loads(header_bytes)
        claims = json.loads(payload_bytes)
    except Exception:
        raise ApiError(401, "unauthenticated", "Malformed bearer token.") from None

    if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise ApiError(401, "unauthenticated", "Unsupported bearer token.")

    if not isinstance(claims, dict):
        raise ApiError(401, "unauthenticated", "Malformed bearer token claims.")

    current = int(time.time()) if now is None else now
    issued = claims.get("iat")
    expires = claims.get("exp")
    if (
        not isinstance(issued, int)
        or not isinstance(expires, int)
        or issued > current + 5
        or expires <= current
        or expires <= issued
        or expires - issued > 60
    ):
        raise ApiError(401, "unauthenticated", "Expired or invalid bearer token lifetime.")

    if claims.get("aud") != expected_aud:
        raise ApiError(401, "unauthenticated", "Bearer token audience is invalid.")

    tenant_id = claims.get("tenant_id")
    if not isinstance(tenant_id, str) or not _TENANT_ID.match(tenant_id):
        raise ApiError(401, "unauthenticated", "Bearer token tenant is invalid.")

    return claims


def _live(request: Request) -> bool:
    return getattr(request.app.state, "mode", "mock") != "mock"


def _request_claims(request: Request) -> dict:
    """The verified token's claims, checked once per request."""
    cached = getattr(request.state, "fiona_claims", None)
    if cached is not None:
        return cached
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ApiError(
            401,
            "unauthenticated",
            "Live mode needs a verified internal token; the tenant is never taken from the request.",
        )
    claims = verify_internal_claims(auth_header[7:].strip())
    request.state.fiona_claims = claims
    return claims


def current_tenant(
    request: Request,
    x_fiona_tenant: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> str:
    if _live(request):
        return _request_claims(request)["tenant_id"]

    tenant = x_fiona_tenant or os.environ.get("DEMO_TENANT_ID") or DEFAULT_DEMO_TENANT
    if not _TENANT_ID.match(tenant):
        raise ApiError(400, "invalid_tenant", f"{TENANT_HEADER} must look like ten_<slug>.")
    return tenant


TenantId = Annotated[str, Depends(current_tenant)]


_USER_ID = re.compile(r"^usr_[A-Za-z0-9_]{1,80}$")
_AGENT_NAME = re.compile(r"^[a-z][a-z_]{1,40}$")
PEOPLE = frozenset({"owner", "finance"})
GUARDIAN = "guardian"


@dataclass(frozen=True)
class Actor:
    """Who is calling: a person (owner or finance, id usr_…), an agent (id = agent name), or the
    Guardian service (role guardian), which only reviews.

    Only people decide on proposals; agents only propose. Live mode reads this from the verified
    token, never from the request, so an agent cannot approve its own work.
    """

    id: str
    role: str

    @property
    def is_person(self) -> bool:
        return self.role in PEOPLE


def current_actor(
    request: Request,
    x_user_id: Annotated[str | None, Header(include_in_schema=False)] = None,
    x_fiona_agent: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> Actor:
    if _live(request):
        claims = _request_claims(request)
        role = claims.get("role")
        if role in PEOPLE and isinstance(claims.get("sub"), str) and _USER_ID.match(claims["sub"]):
            return Actor(claims["sub"], role)
        if (
            role == "agent"
            and isinstance(claims.get("agent"), str)
            and _AGENT_NAME.match(claims["agent"])
        ):
            if claims["agent"] == GUARDIAN:
                raise ApiError(401, "unauthenticated", "The Guardian has its own role.")
            return Actor(claims["agent"], "agent")
        if role == GUARDIAN:
            return Actor(GUARDIAN, GUARDIAN)
        raise ApiError(401, "unauthenticated", "Bearer token does not name a person or an agent.")

    # Mock mode is local development: the caller says who it is.
    if x_fiona_agent:
        if not _AGENT_NAME.match(x_fiona_agent):
            raise ApiError(400, "invalid_actor", "X-Fiona-Agent must be an agent name.")
        return Actor(x_fiona_agent, GUARDIAN if x_fiona_agent == GUARDIAN else "agent")
    user = x_user_id or "usr_owner"
    if not _USER_ID.match(user):
        raise ApiError(400, "invalid_actor", "X-User-Id must look like usr_<id>.")
    return Actor(user, "owner")


CurrentActor = Annotated[Actor, Depends(current_actor)]
