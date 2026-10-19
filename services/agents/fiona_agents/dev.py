"""Local dev server (`pnpm dev`): loads the root .env.local, then serves with reload.

Tests never import this module, so local secrets never reach a test run.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn


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


if __name__ == "__main__":
    load_root_env()
    # Some drives (mapped or shared folders) send no file-change events, so reload never fired
    # and new routes stayed missing until a manual restart. Polling works everywhere.
    os.environ.setdefault("WATCHFILES_FORCE_POLLING", "true")
    uvicorn.run(
        "fiona_agents.main:app",
        host="127.0.0.1",
        port=8100,
        reload=True,
        # Open keep-alive connections from the web app would otherwise stall every reload on Windows.
        timeout_graceful_shutdown=2,
        reload_dirs=[str(Path(__file__).parent)],
    )
