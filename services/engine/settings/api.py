"""Workspace settings endpoints.

- /v1/settings/ai: how this workspace's agents and Guardian reach Claude. People see the mode and
  the last four characters; only the owner changes it; only the agents and the Guardian receive
  the secret itself (to start Claude), never a browser.
- /v1/settings/launch-lab: the workspace's own Launch Lab defaults (people read, owner writes).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from engine.app import clock
from engine.app.errors import ApiError
from engine.app.tenancy import CurrentActor, TenantId
from engine.ledger import db
from engine.settings import store

router = APIRouter(tags=["settings"])

AI = "ai_connection"
LAUNCH = "launch_lab_defaults"
AiMode = Literal["server", "api_key", "subscription_token"]


def get_conn() -> Iterator[psycopg.Connection]:
    with db.connect(autocommit=True) as conn:
        yield conn


def get_clock() -> datetime:
    return clock.now()


Conn = Annotated[psycopg.Connection, Depends(get_conn)]
Clock = Annotated[datetime, Depends(get_clock)]


def _people_only(actor: Any) -> None:
    if not actor.is_person:
        raise ApiError(403, "people_only", "Only the owner or finance team can see settings.")


def _owner_only(actor: Any) -> None:
    if actor.role != "owner":
        raise ApiError(403, "owner_only", "Only the owner can change workspace settings.")


def _when(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# ---------------------------------------------------------------- AI connection


class AiConnectionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: AiMode
    secret: str | None = Field(None, min_length=20, max_length=500)


def _check_secret(mode: str, secret: str) -> None:
    if any(c.isspace() for c in secret) or not secret.startswith("sk-ant-"):
        raise ApiError(422, "invalid_secret", "That doesn't look like an Anthropic key or token.")
    is_token = secret.startswith("sk-ant-oat")
    if mode == "api_key" and is_token:
        raise ApiError(
            422, "wrong_kind", "That is a subscription token; choose 'Claude subscription'."
        )
    if mode == "subscription_token" and not is_token:
        raise ApiError(422, "wrong_kind", "That is an API key; choose 'Anthropic API key' for it.")


def _ai_view(row: dict[str, Any] | None) -> dict[str, Any]:
    value = (row or {}).get("value") or {}
    return {
        "api_version": "v1",
        "mode": value.get("mode", "server"),
        "hint": value.get("hint"),
        "updated_by": (row or {}).get("updated_by"),
        "updated_at": _when((row or {}).get("updated_at")),
        "storage_ready": store.storage_ready(),
    }


@router.get("/v1/settings/ai")
def get_ai_connection(tenant_id: TenantId, actor: CurrentActor, conn: Conn) -> dict[str, Any]:
    _people_only(actor)
    return _ai_view(store.read(conn, tenant_id, AI))


@router.post("/v1/settings/ai")
def set_ai_connection(
    tenant_id: TenantId, actor: CurrentActor, conn: Conn, now: Clock, body: AiConnectionChange
) -> dict[str, Any]:
    _owner_only(actor)
    current = store.read(conn, tenant_id, AI)
    if body.mode == "server":
        store.write(
            conn, tenant_id, AI, {"mode": "server"}, ciphertext=None, updated_by=actor.id, now=now
        )
        return _ai_view(store.read(conn, tenant_id, AI))
    if body.secret is None:
        # Keeping the stored secret is allowed only when it is already for this mode.
        same = current and current["value"].get("mode") == body.mode and current["ciphertext"]
        if not same:
            raise ApiError(422, "secret_required", "Paste the key or token to connect.")
        return _ai_view(current)
    _check_secret(body.mode, body.secret)
    try:
        sealed = store.seal(tenant_id, AI, body.secret)
    except store.SecretStorageUnavailable as exc:
        raise ApiError(503, "secret_storage_unavailable", str(exc)) from exc
    value = {"mode": body.mode, "hint": f"…{body.secret[-4:]}"}
    store.write(conn, tenant_id, AI, value, ciphertext=sealed, updated_by=actor.id, now=now)
    return _ai_view(store.read(conn, tenant_id, AI))


@router.get("/v1/settings/ai/credential")
def ai_credential(tenant_id: TenantId, actor: CurrentActor, conn: Conn) -> dict[str, Any]:
    """The secret, for the agents and the Guardian only: they start Claude with it."""
    if actor.role not in ("agent", "guardian"):
        raise ApiError(403, "services_only", "Only Fiona's own services can read this.")
    row = store.read(conn, tenant_id, AI)
    mode = ((row or {}).get("value") or {}).get("mode", "server")
    if mode == "server" or not row or not row["ciphertext"]:
        return {"api_version": "v1", "mode": "server", "secret": None}
    try:
        secret = store.unseal(tenant_id, AI, row["ciphertext"])
    except store.SecretStorageUnavailable as exc:
        # Fail closed: the caller must not fall back to the server's own Claude account.
        raise ApiError(503, "secret_storage_unavailable", str(exc)) from exc
    return {"api_version": "v1", "mode": mode, "secret": secret}


# ---------------------------------------------------------------- Launch Lab defaults

Money = Annotated[int, Field(ge=0, le=10**13)]
ShareBp = Annotated[int, Field(ge=0, le=10_000)]


class LaunchDefaults(BaseModel):
    """Defaults for products this business launches. Per-unit costs are a share of the unit
    cost (basis points), so one default fits a PKR 50 item and a PKR 5,000 item alike."""

    model_config = ConfigDict(extra="forbid")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    freight_share_bp: ShareBp | None = None
    packaging_share_bp: ShareBp | None = None
    storage_share_bp_per_month: ShareBp | None = None
    launch_costs_minor: Money | None = None
    marketing_monthly_minor: Money | None = None
    monthly_fixed_costs_minor: Money | None = None
    discount_rate_bp: Annotated[int, Field(ge=0, lt=10_000)] | None = None
    return_rate_bp: Annotated[int, Field(ge=0, lt=10_000)] | None = None
    payment_fee_rate_bp: Annotated[int, Field(ge=0, lt=10_000)] | None = None
    lead_time_days: Annotated[int, Field(ge=0, le=365)] | None = None
    moq: Annotated[int, Field(ge=1, le=10_000_000)] | None = None
    horizon_months: Annotated[int, Field(ge=1, le=36)] | None = None


@router.get("/v1/settings/launch-lab")
def get_launch_defaults(tenant_id: TenantId, actor: CurrentActor, conn: Conn) -> dict[str, Any]:
    _people_only(actor)
    row = store.read(conn, tenant_id, LAUNCH)
    return {
        "api_version": "v1",
        "defaults": (row or {}).get("value") or None,
        "updated_by": (row or {}).get("updated_by"),
        "updated_at": _when((row or {}).get("updated_at")),
    }


@router.post("/v1/settings/launch-lab")
def set_launch_defaults(
    tenant_id: TenantId, actor: CurrentActor, conn: Conn, now: Clock, body: LaunchDefaults
) -> dict[str, Any]:
    _owner_only(actor)
    value = body.model_dump(exclude_none=True)
    store.write(conn, tenant_id, LAUNCH, value, ciphertext=None, updated_by=actor.id, now=now)
    return get_launch_defaults(tenant_id, actor, conn)
