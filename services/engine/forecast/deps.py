"""Request helpers shared by the Yahya-lane routers (forecast, decisions, financing)."""

from __future__ import annotations

from fastapi import Request

from engine.app.errors import ApiError
from engine.forecast.mocks import MOCK_TENANT


def mode(request: Request) -> str:
    """FIONA_MODE as resolved at app start-up (see engine.app.main.fiona_mode)."""
    return getattr(request.app.state, "mode", "mock")


def require_mock_tenant(tenant_id: str) -> None:
    if tenant_id != MOCK_TENANT:
        raise ApiError(
            404, "not_found", f"No mock data for tenant {tenant_id}.", {"tenant_id": tenant_id}
        )


def not_live_yet(task: str, due: str) -> ApiError:
    return ApiError(
        501,
        "not_implemented",
        f"Live mode for this endpoint arrives with task {task} ({due}). Use FIONA_MODE=mock until then.",
        {"module": "forecast", "task": task},
    )
