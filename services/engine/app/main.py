"""Fiona engine: one FastAPI app that mounts every module's router.

A module (ledger, guardian_checks, forecast, decisions, …) is a folder next to `app/`. To serve
endpoints it exposes `router`, a FastAPI `APIRouter` with full `/v1/...` paths, in
`<module>/api.py`. This file discovers and mounts each one, so module owners never edit it.

Contract paths that no module serves yet answer 501 `not_implemented` with the owning module,
so callers building against the contract get a clear signal rather than a bare 404.

Run from services/engine: `uv run uvicorn engine.app.main:app --app-dir .. --port 8000`.
"""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from engine.app import errors

ENGINE_DIR = Path(__file__).resolve().parents[1]
NOT_MODULES = {"app", "tests"}

# Blueprint §11.2: contract path prefixes and the module that will serve them. Used only to
# answer 501 for paths nobody serves yet; modules declare their real routes in api.py.
CONTRACT_OWNERS: dict[str, str] = {
    "/v1/import": "ledger",
    "/v1/ledger": "ledger",
    "/v1/reconcile": "ledger",
    "/v1/bills": "ledger",
    "/v1/proposals": "ledger",
    "/v1/wallet": "ledger",
    "/v1/audit": "ledger",
    "/v1/stage": "forecast",
    "/v1/forecast": "forecast",
    "/v1/inventory": "forecast",
    "/v1/launch-lab": "forecast",
    "/v1/decisions": "decisions",
}

Mode = Literal["mock", "live"]
log = logging.getLogger("engine")


def fiona_mode() -> Mode:
    """`FIONA_MODE=mock|live` (default mock). Modules serve fixtures in mock mode (R2)."""
    raw = os.environ.get("FIONA_MODE", "") or "mock"
    if raw not in ("mock", "live"):
        raise RuntimeError(f'FIONA_MODE must be "mock" or "live" (got "{raw}").')
    return raw  # type: ignore[return-value]


def discover_modules(engine_dir: Path = ENGINE_DIR) -> list[str]:
    """Module folders that expose `api.py`, in a stable order."""
    return sorted(
        p.name
        for p in engine_dir.iterdir()
        if p.is_dir()
        and p.name not in NOT_MODULES
        and not p.name.startswith((".", "_"))
        and (p / "api.py").is_file()
    )


def mount_modules(app: FastAPI, modules: Iterable[str]) -> list[str]:
    """Import `engine.<module>.api` and include its router. A broken module fails startup loudly."""
    mounted = []
    for name in modules:
        api = importlib.import_module(f"engine.{name}.api")
        router = getattr(api, "router", None)
        if not isinstance(router, APIRouter):
            raise TypeError(f"engine/{name}/api.py must expose `router` as a FastAPI APIRouter.")
        app.include_router(router)
        mounted.append(name)
    return mounted


def contract_owner(path: str) -> str | None:
    for prefix, owner in CONTRACT_OWNERS.items():
        if path == prefix or path.startswith(prefix + "/"):
            return owner
    return None


def create_app(modules: Iterable[str] | None = None) -> FastAPI:
    app = FastAPI(title="Fiona engine", version="0.1.0")
    app.state.mode = fiona_mode()
    errors.install(app)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"api_version": errors.API_VERSION, "status": "ok", "service": "engine"}

    app.state.modules = mount_modules(app, discover_modules() if modules is None else modules)
    log.info("engine started", extra={"mode": app.state.mode, "modules": app.state.modules})

    # Registered last, so every module route above wins.
    @app.api_route(
        "/v1/{rest:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    def not_served(rest: str, request: Request) -> JSONResponse:
        path = f"/v1/{rest}"
        owner = contract_owner(path)
        if owner is None:
            return errors.error_response(request, 404, "not_found", f"No endpoint at {path}.")
        return errors.error_response(
            request,
            501,
            "not_implemented",
            f"{path} is in the contract, but the {owner} module does not serve it yet.",
            {"module": owner},
        )

    return app


app = create_app()
