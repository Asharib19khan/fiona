"""Verification for short-lived BFF-to-agents HS256 tokens (R15)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass


class TokenError(ValueError):
    pass


class AuthNotConfigured(TokenError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str


_TENANT = re.compile(r"^ten_[a-z0-9_]{1,60}$")
_USER = re.compile(r"^usr_[A-Za-z0-9_]{1,80}$")
_ROLES = {"owner", "finance"}


def _decode_segment(segment: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        raise TokenError("Malformed bearer token.")
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise TokenError("Malformed bearer token.") from exc


def _encode_segment(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def verify_agents_token(token: str, *, now: int | None = None) -> Principal:
    secret = os.environ.get("INTERNAL_JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise AuthNotConfigured("Internal authentication is not configured.")
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("Malformed bearer token.")
    header_bytes, payload_bytes = (_decode_segment(part) for part in parts[:2])
    signature = parts[2]
    expected = hmac.new(
        secret.encode("utf-8"), f"{parts[0]}.{parts[1]}".encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, _encode_segment(expected)):
        raise TokenError("Invalid bearer token.")
    try:
        header = json.loads(header_bytes)
        claims = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenError("Malformed bearer token.") from exc
    if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise TokenError("Unsupported bearer token.")
    if not isinstance(claims, dict):
        raise TokenError("Malformed bearer token.")

    current = int(time.time()) if now is None else now
    issued = claims.get("iat")
    expires = claims.get("exp")
    if (
        not isinstance(issued, int)
        or isinstance(issued, bool)
        or not isinstance(expires, int)
        or isinstance(expires, bool)
        or issued > current + 5
        or expires <= current
        or expires <= issued
        or expires - issued > 60
    ):
        raise TokenError("Expired or invalid bearer token lifetime.")
    if claims.get("aud") != "fiona-agents":
        raise TokenError("Bearer token audience is invalid.")
    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    role = claims.get("role")
    if not isinstance(user_id, str) or not _USER.fullmatch(user_id):
        raise TokenError("Bearer token subject is invalid.")
    if not isinstance(tenant_id, str) or not _TENANT.fullmatch(tenant_id):
        raise TokenError("Bearer token tenant is invalid.")
    if role not in _ROLES:
        raise TokenError("This role cannot submit documents for processing.")
    return Principal(user_id=user_id, tenant_id=tenant_id, role=role)
