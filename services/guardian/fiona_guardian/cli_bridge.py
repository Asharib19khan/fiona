"""Claude CLI Terminal Bridge for Guardian adversarial prompt-injection review.

Allows Guardian to invoke Opus for deep adversarial evaluation (G-12) via headless
terminal execution without requiring raw API keys.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time

log = logging.getLogger("fiona_guardian.cli_bridge")

GUARDIAN_MODEL = os.environ.get("FIONA_MODEL_GUARDIAN", "opus")


def is_claude_cli_available() -> bool:
    """Return True if the `claude` executable is located on PATH."""
    return shutil.which("claude") is not None


def run_guardian_review_cli(
    prompt: str,
    *,
    system_prompt: str | None = None,
    timeout_seconds: float = 30.0,
) -> str:
    """Execute Guardian adversarial review via Claude CLI (defaulting to Opus)."""
    if not is_claude_cli_available():
        raise RuntimeError("Claude CLI ('claude') is not found on PATH.")

    cmd = ["claude", "-p", prompt, "--model", GUARDIAN_MODEL, "--tools", ""]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"Guardian CLI ({GUARDIAN_MODEL}) timed out after {timeout_seconds}s"
        ) from exc

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        log.warning("Guardian CLI failed with code %d: %s", proc.returncode, err)
        raise RuntimeError(f"Guardian CLI error: {err}")

    raw_output = proc.stdout.strip()
    clean_lines = [line for line in raw_output.splitlines() if not line.startswith("Warning:")]
    result = "\n".join(clean_lines).strip()
    log.info(
        "Guardian CLI adversarial review success (%s) in %.2fs",
        GUARDIAN_MODEL,
        time.monotonic() - t0,
    )
    return result
