"""Endpoints for the agent team: start work, follow it, read what each agent did.

People call these through the web app's signed 60-second token (aud fiona-agents, role owner or
finance); the tenant comes from that token. Without INTERNAL_JWT_SECRET the service is in local
development and acts for DEMO_TENANT_ID, unless FIONA_MODE=live, where it refuses (fail closed).

With FIONA_LLM_PROVIDER=replay (the public link) live runs are off: the recorded real runs in
replays/ are listed instead, each marked replayed.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fiona_agents import orchestrator, runtime
from fiona_agents.auth import AuthNotConfigured, Principal, TokenError, verify_agents_token

router = APIRouter(tags=["agent team"])
REPLAYS = Path(__file__).resolve().parents[1] / "replays"
WORKERS = ("controller", "treasurer", "cfo_strategist", "growth_analyst")


def principal(authorization: str | None) -> Principal:
    if os.environ.get("INTERNAL_JWT_SECRET"):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                401,
                {
                    "code": "unauthorized",
                    "message": "A short-lived internal bearer token is required.",
                },
            )
        try:
            return verify_agents_token(authorization.removeprefix("Bearer "))
        except AuthNotConfigured as exc:
            raise HTTPException(503, {"code": "auth_not_configured", "message": str(exc)}) from exc
        except TokenError as exc:
            raise HTTPException(401, {"code": "unauthorized", "message": str(exc)}) from exc
    if os.environ.get("FIONA_MODE") == "live":
        raise HTTPException(
            503, {"code": "auth_not_configured", "message": "Live mode needs INTERNAL_JWT_SECRET."}
        )
    return Principal(
        user_id=os.environ.get("DEMO_USER_ID") or "usr_owner_karachi",
        tenant_id=os.environ.get("DEMO_TENANT_ID") or "ten_karachi_apparel",
        role="owner",
    )


def _live_enabled() -> None:
    if (os.environ.get("FIONA_LLM_PROVIDER") or "replay") != "claude_cli":
        raise HTTPException(
            503,
            {
                "code": "live_agents_off",
                "message": "Live agent runs are off on this deployment; the recorded runs are shown instead.",
            },
        )


def _background(target: Any, *args: Any) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pipeline: str | None = Field(default=None, pattern="^daily$")
    agent: str | None = Field(
        default=None, pattern="^(controller|treasurer|cfo_strategist|growth_analyst)$"
    )
    task: str | None = Field(default=None, max_length=1_000)


@router.post("/v1/agents/team/run", status_code=202)
def start_run(body: RunRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    who = principal(authorization)
    _live_enabled()
    if body.pipeline == "daily" or (body.pipeline is None and body.agent is None):
        record = orchestrator._start(who.tenant_id, "daily", requested_by=who.user_id)
        _background(orchestrator.run_daily, who.tenant_id, record)
        return {"api_version": "v1", "status": "accepted", "pipeline_id": record["id"]}
    task = body.task or dict(orchestrator.DAILY).get(
        body.agent, "Review the business from your role and report."
    )
    run = runtime.new_run(who.tenant_id, body.agent, task)
    _background(runtime.execute, run)
    return {"api_version": "v1", "status": "accepted", "run_id": run["id"]}


class CouncilRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=10, max_length=1_000)


@router.post("/v1/agents/council", status_code=202)
def start_council(
    body: CouncilRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    who = principal(authorization)
    _live_enabled()
    record = orchestrator._start(
        who.tenant_id, "council", question=body.question, requested_by=who.user_id
    )
    _background(orchestrator.run_council, who.tenant_id, body.question, record)
    return {"api_version": "v1", "status": "accepted", "pipeline_id": record["id"]}


@router.post("/v1/agents/pay-approved")
def pay_approved(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Send what the owner approved and is due today to the sandbox wallet (no model involved)."""
    who = principal(authorization)
    return {"api_version": "v1", "results": orchestrator.pay_approved(who.tenant_id)}


@router.post("/v1/agents/{agent}/reset-memory")
def reset_memory(agent: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    who = principal(authorization)
    if agent not in WORKERS:
        raise HTTPException(404, {"code": "not_found", "message": f"No agent called {agent}."})
    runtime.reset_memory(who.tenant_id, agent)
    return {"api_version": "v1", "agent": agent, "memory": "reset"}


def _replayed(kind: str) -> list[dict[str, Any]]:
    folder = REPLAYS / kind
    if not folder.is_dir():
        return []
    return [
        {**json.loads(path.read_text(encoding="utf-8")), "replayed": True}
        for path in sorted(folder.glob("*.json"), reverse=True)
    ]


@router.get("/v1/agents/team/runs")
def runs(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    who = principal(authorization)
    live = runtime.list_runs(who.tenant_id)
    recorded = [
        {
            k: r.get(k)
            for k in (
                "id",
                "agent",
                "task",
                "status",
                "started_at",
                "finished_at",
                "cost_usd",
                "summary",
                "pipeline_id",
                "replayed",
            )
        }
        for r in _replayed("runs")
        if r.get("tenant_id") == who.tenant_id
    ]
    return {"api_version": "v1", "runs": live or recorded}


@router.get("/v1/agents/team/runs/{run_id}")
def run_detail(run_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    who = principal(authorization)
    record = runtime.load_run(run_id) or next(
        (r for r in _replayed("runs") if r.get("id") == run_id), None
    )
    if record is None or record.get("tenant_id") != who.tenant_id:
        raise HTTPException(404, {"code": "not_found", "message": "No run matches this ID."})
    return {"api_version": "v1", **record}


@router.get("/v1/agents/pipelines")
def pipelines(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    who = principal(authorization)
    live = orchestrator.list_pipelines(who.tenant_id)
    recorded = [
        {
            k: p.get(k)
            for k in ("id", "kind", "status", "question", "started_at", "finished_at", "replayed")
        }
        for p in _replayed("pipelines")
        if p.get("tenant_id") == who.tenant_id
    ]
    return {"api_version": "v1", "pipelines": live or recorded}


@router.get("/v1/agents/pipelines/{pipeline_id}")
def pipeline_detail(
    pipeline_id: str, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    who = principal(authorization)
    record = orchestrator.load_pipeline(pipeline_id) or next(
        (p for p in _replayed("pipelines") if p.get("id") == pipeline_id), None
    )
    if record is None or record.get("tenant_id") != who.tenant_id:
        raise HTTPException(404, {"code": "not_found", "message": "No pipeline matches this ID."})
    return {"api_version": "v1", **record}


class ReadBillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=10, max_length=7_200_000)


@router.post("/v1/agents/read-bill")
def read_bill_route(
    body: ReadBillRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Read an uploaded bill into fields for a person to review. Nothing is recorded here."""
    import base64
    import binascii

    from fiona_agents import reader
    from fiona_agents.engine import Engine, EngineError

    who = principal(authorization)
    _live_enabled()
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            400, {"code": "invalid_file", "message": "The file could not be decoded."}
        ) from exc
    try:
        result = reader.read_bill(content, body.filename)
    except reader.ReadError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)}) from exc
    # Suggest the supplier: tax ID first, then IBAN, then name. A suggestion, never a decision.
    fields = result["fields"]
    candidates: list[dict[str, Any]] = []
    engine = Engine(who.tenant_id, "controller")
    for key in ("supplier_tax_id", "bank_iban", "supplier_name"):
        value = fields[key]["value"]
        if value and not candidates:
            try:
                candidates = engine.get("/v1/parties", q=str(value)[:120]).get("parties", [])
            except EngineError:
                candidates = []
    return {"api_version": "v1", **result, "supplier_candidates": candidates[:5]}
