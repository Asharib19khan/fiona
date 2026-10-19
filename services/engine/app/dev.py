"""Local dev server for the engine (`pnpm dev`): reloads on code changes in the engine's own
folders and never watches `.venv`, so `uv add` doesn't restart it mid-install.

Run from services/engine: `uv run python app/dev.py`. A module folder added after start-up is
picked up on the next restart.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

ENGINE = Path(__file__).resolve().parents[1]
SKIP = {"__pycache__", "node_modules"}


def load_root_env() -> None:
    """D-011: the root .env.local feeds every service in local dev. Real environment variables
    win; a missing file is fine (a fresh clone runs in mock mode with no secrets)."""
    env_file = Path(__file__).resolve().parents[3] / ".env.local"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and value.strip():
            os.environ.setdefault(key.strip(), value.strip())


def code_dirs() -> list[str]:
    return [
        str(p)
        for p in sorted(ENGINE.iterdir())
        if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP
    ]


if __name__ == "__main__":
    load_root_env()
    # Some drives send no file-change events, so reload never fired; polling works everywhere.
    os.environ.setdefault("WATCHFILES_FORCE_POLLING", "true")
    uvicorn.run(
        "engine.app.main:app",
        app_dir=str(ENGINE.parent),
        host="127.0.0.1",
        port=8000,
        reload=True,
        # Open keep-alive connections from the web app would otherwise stall every reload on Windows.
        timeout_graceful_shutdown=2,
        reload_dirs=code_dirs(),
    )
