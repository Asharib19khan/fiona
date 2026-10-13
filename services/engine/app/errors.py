"""The contract's error envelope and request IDs, shared by every engine module.

Every error response is `{api_version, error: {code, message, details?, request_id}}`.
Modules may raise `ApiError` instead of building responses by hand.
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
REQUEST_ID_HEADER = "X-Request-Id"
_INCOMING_ID = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")

log = logging.getLogger("engine")


class ApiError(Exception):
    """An error the client should see, carried in the contract's envelope."""

    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def new_request_id() -> str:
    return f"req_{secrets.token_hex(8)}"


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id(request)}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status, content={"api_version": API_VERSION, "error": error})


def install(app: FastAPI) -> None:
    """Attach request IDs and the error envelope to every response."""

    @app.middleware("http")
    async def _request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request.state.request_id = incoming if _INCOMING_ID.match(incoming) else new_request_id()
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and messages only, never the submitted values.
        problems = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return error_response(
            request, 422, "validation_error", "The request is invalid.", {"errors": problems}
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"request_id": request_id(request)})
        return error_response(
            request, 500, "internal_error", "Something went wrong. Quote the request_id."
        )
