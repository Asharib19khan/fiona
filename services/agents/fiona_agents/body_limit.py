"""Refuse request bodies over a size cap before anything reads them.

The services are reachable on public URLs. FastAPI parses a JSON body before the auth
dependency runs, so without a cap an unauthenticated caller could make the service hold a
huge body in memory. This checks Content-Length up front and counts streamed bytes too.
"""

from __future__ import annotations

import json
from typing import Any

_BODY = json.dumps(
    {
        "api_version": "v1",
        "error": {"code": "request_too_large", "message": "The request body is too large."},
    }
).encode("utf-8")


class _TooLarge(Exception):
    pass


class BodyLimit:
    def __init__(self, app: Any, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _refuse(self, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_BODY)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _BODY})

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = -1
                if declared < 0 or declared > self.max_bytes:
                    await self._refuse(send)
                    return

        received = 0
        started = False

        async def limited_receive() -> Any:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge
            return message

        async def tracking_send(message: Any) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._refuse(send)
