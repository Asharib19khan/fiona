"""Local dev server for the engine (`pnpm dev`): reloads on code changes in the engine's own
folders and never watches `.venv`, so `uv add` doesn't restart it mid-install.

Run from services/engine: `uv run python app/dev.py`. A module folder added after start-up is
picked up on the next restart.
"""

from __future__ import annotations

from pathlib import Path

import uvicorn

ENGINE = Path(__file__).resolve().parents[1]
SKIP = {"__pycache__", "node_modules"}


def code_dirs() -> list[str]:
    return [
        str(p)
        for p in sorted(ENGINE.iterdir())
        if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP
    ]


if __name__ == "__main__":
    uvicorn.run(
        "engine.app.main:app",
        app_dir=str(ENGINE.parent),
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=code_dirs(),
    )
