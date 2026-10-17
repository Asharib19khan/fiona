"""Read-only agent and briefing endpoints backed by labelled synthetic replay data."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile

from fiona_agents.auth import AuthNotConfigured, TokenError, verify_agents_token
from fiona_agents.extraction import MAX_DOCUMENT_BYTES, ExtractionError, extract_bill
from fiona_agents.replay import ReplayUnavailable, provider_name, replay_answer

router = APIRouter(tags=["agents"])
REPO_ROOT = Path(__file__).resolve().parents[3]
_runs: dict[str, dict[str, Any]] = {}


class AskContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: str | None = Field(default=None, max_length=200)
    selection: str | None = Field(default=None, max_length=500)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2_000)
    context: AskContext | None = None


def _fixture(path: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


@router.post("/v1/agents/extract-bill")
async def extract_bill_route(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Extract one uploaded bill. Only the signed-in BFF may invoke this cost-bearing route."""
    if provider_name() != "anthropic_api":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_not_configured",
                "message": "Bill extraction requires the explicitly enabled anthropic_api provider.",
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": "A short-lived internal bearer token is required.",
            },
        )
    try:
        _principal = verify_agents_token(authorization.removeprefix("Bearer "))
    except AuthNotConfigured as exc:
        raise HTTPException(
            status_code=503, detail={"code": "auth_not_configured", "message": str(exc)}
        ) from exc
    except TokenError as exc:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": str(exc)}
        ) from exc

    length = request.headers.get("content-length")
    if length is not None and (
        not length.isdecimal() or int(length) > MAX_DOCUMENT_BYTES + 64 * 1024
    ):
        raise HTTPException(
            status_code=413,
            detail={"code": "document_too_large", "message": "Documents are limited to 12 MB."},
        )
    limited_body = bytearray()
    async for chunk in request.stream():
        if len(limited_body) + len(chunk) > MAX_DOCUMENT_BYTES + 64 * 1024:
            raise HTTPException(
                status_code=413,
                detail={"code": "document_too_large", "message": "Documents are limited to 12 MB."},
            )
        limited_body.extend(chunk)
    body_bytes = bytes(limited_body)

    async def receive_body() -> dict[str, Any]:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    form_request = Request(request.scope, receive=receive_body)
    try:
        async with form_request.form(max_files=1, max_fields=3, max_part_size=64 * 1024) as form:
            if set(form.keys()) != {"file", "currency", "minor_unit"}:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "unexpected_fields",
                        "message": "Only file, currency and minor_unit are accepted.",
                    },
                )
            file = form.get("file")
            currency_hint = form.get("currency")
            minor_unit = form.get("minor_unit")
            if not isinstance(file, UploadFile):
                raise HTTPException(
                    status_code=422,
                    detail={"code": "file_required", "message": "A bill file is required."},
                )
            if not isinstance(currency_hint, str) or not re.fullmatch(r"[A-Z]{3}", currency_hint):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "currency_required",
                        "message": "The BFF must supply the tenant currency as an uppercase ISO code.",
                    },
                )
            if (
                not isinstance(minor_unit, str)
                or not minor_unit.isdecimal()
                or int(minor_unit) not in range(0, 5)
            ):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "minor_unit_required",
                        "message": "The BFF must supply the tenant currency minor unit (0-4).",
                    },
                )
            content = await file.read(MAX_DOCUMENT_BYTES + 1)
            if len(content) > MAX_DOCUMENT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "document_too_large",
                        "message": "Documents are limited to 12 MB.",
                    },
                )
            media_type = (file.content_type or "").lower()
            if media_type not in {"application/pdf", "image/jpeg", "image/png", "image/webp"}:
                raise HTTPException(
                    status_code=415,
                    detail={
                        "code": "unsupported_media_type",
                        "message": "Upload a PDF, JPEG, PNG or WebP bill.",
                    },
                )
            if (
                not file.filename
                or len(file.filename) > 255
                or any(ord(char) < 32 for char in file.filename)
            ):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "invalid_filename",
                        "message": "The uploaded filename is invalid.",
                    },
                )
            result = await extract_bill(
                content,
                media_type=media_type,
                filename=file.filename,
                currency_hint=currency_hint,
                minor_unit=int(minor_unit),
            )
    except ExtractionError as exc:
        raise HTTPException(
            status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_multipart",
                "message": "Send one document and its currency context as multipart form data.",
            },
        ) from exc
    return result.model_dump(mode="json")


@router.get("/v1/briefing")
def briefing() -> dict[str, Any]:
    """The contract-backed Seed-42 briefing until live source composition is available."""
    return _fixture("packages/contracts/examples/Briefing.seed-42.json")


@router.post("/v1/agents/ask")
def ask(body: AskRequest) -> dict[str, Any]:
    provider = provider_name()
    if provider == "claude_cli":
        from fiona_agents.cli_bridge import is_claude_cli_available, run_claude_cli

        if is_claude_cli_available():
            try:
                answer = run_claude_cli(
                    body.question,
                    role="reason",
                    system_prompt=(
                        "You are Fiona, an autonomous AI finance team for small and medium businesses. "
                        "You advise on cash flow, working capital, and financial decisions with deterministic precision. "
                        "Answer directly and concisely."
                    ),
                    timeout_seconds=25.0,
                )
                import secrets

                run_id = f"run_cli_{secrets.token_hex(8)}"
                response = {
                    "api_version": "v1",
                    "answer": answer,
                    "meta": {
                        "run_id": run_id,
                        "model": "claude_cli:sonnet",
                        "prompt_version": "agents/ask/cli/v1",
                        "replayed": False,
                        "recorded_at": "2026-10-22T04:00:00Z",
                    },
                }
                _runs[run_id] = {
                    "api_version": "v1",
                    "status": "completed",
                    "answer": answer,
                    "meta": response["meta"],
                }
                return response
            except Exception as exc:
                # Fallback gracefully to replay if CLI call encounters timeout/network glitch
                logging.getLogger("fiona_agents.api").warning(
                    "Claude CLI execution failed, falling back to replay: %s", exc
                )

    if provider not in ("replay", "claude_cli"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_not_configured",
                "message": f"Provider {provider!r} is not enabled in this build. Set FIONA_LLM_PROVIDER=replay or claude_cli.",
            },
        )
    try:
        replay = replay_answer(body.question)
    except ReplayUnavailable as exc:
        raise HTTPException(
            status_code=422, detail={"code": "replay_miss", "message": str(exc)}
        ) from exc
    response = {
        "api_version": "v1",
        "answer": replay.answer,
        "meta": {
            "run_id": replay.run_id,
            "model": "replay",
            "prompt_version": replay.prompt_version,
            "replayed": True,
            "recorded_at": "2026-10-22T04:00:00Z",
        },
    }
    _runs[replay.run_id] = {
        "api_version": "v1",
        "status": "completed",
        "answer": replay.answer,
        "meta": response["meta"],
    }
    return response


@router.get("/v1/agents/runs/{run_id}")
def agent_run(run_id: str) -> dict[str, Any]:
    if run_id not in _runs:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No replay run matches this ID."},
        )
    return _runs[run_id]
