"""Guardian service app. A1 skeleton: health, request IDs and the contract error envelope.

The combiner, rulebook loader and adversarial reviewer arrive in A6.
Run from services/guardian: `uv run uvicorn fiona_guardian.main:app --port 8200`.
"""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

API_VERSION = "v1"
SERVICE = "guardian"
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
    app = FastAPI(title="Fiona Guardian", version="0.1.0")

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

    return app


app = create_app()
