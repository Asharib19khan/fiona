"""Agents service app: labelled replay endpoints and contract-gated bill extraction.

The agent team (runtime.py, orchestrator.py, team_api.py) runs each agent in its own Claude process.
Run from services/agents: `uv run uvicorn fiona_agents.main:app --port 8100`.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fiona_agents import orchestrator
from fiona_agents.api import router
from fiona_agents.body_limit import BodyLimit
from fiona_agents.team_api import router as team_router

API_VERSION = "v1"
SERVICE = "agents"
_INCOMING_ID = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
log = logging.getLogger(SERVICE)


def _error(request: Request, status: int, code: str, message: str, details: Any = None):
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", f"req_{secrets.token_hex(8)}"),
    }
    if details:
        error["details"] = details
    return JSONResponse(status_code=status, content={"api_version": API_VERSION, "error": error})


def create_app() -> FastAPI:
    # Live services are on public URLs: no interactive docs or schema there.
    live = os.environ.get("FIONA_MODE") == "live"
    hidden = {"docs_url": None, "redoc_url": None, "openapi_url": None} if live else {}
    app = FastAPI(title="Fiona agents", version="0.1.0", **hidden)
    # Bills for reading are up to 5 MB, base64-encoded; nothing legitimate is larger.
    app.add_middleware(BodyLimit, max_bytes=8 * 1024 * 1024)

    @app.middleware("http")
    async def request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("X-Request-Id", "")
        request.state.request_id = (
            incoming if _INCOMING_ID.match(incoming) else f"req_{secrets.token_hex(8)}"
        )
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return _error(
                request,
                exc.status_code,
                str(exc.detail.get("code", "http_error")),
                str(exc.detail.get("message", "The request could not be completed.")),
                exc.detail.get("details"),
            )
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return _error(
            request, 422, "validation_error", "The request is invalid.", {"errors": problems}
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return _error(request, 500, "internal_error", "Something went wrong. Quote the request_id.")

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"api_version": API_VERSION, "status": "ok", "service": SERVICE}

    app.include_router(router)
    app.include_router(team_router)
    orchestrator.start_autopilot()

    return app


app = create_app()
