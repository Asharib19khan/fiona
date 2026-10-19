"""Claude CLI Terminal Bridge for multi-model autonomous agent execution.

Enables Fiona to dispatch tasks across Claude models (Haiku for fast extraction,
Sonnet for CFO/Treasurer reasoning, Opus for Guardian adversarial review) via
headless CLI subprocess calls without requiring raw API keys.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time

from fiona_agents import credentials

log = logging.getLogger("fiona.cli_bridge")

# High-affinity model routing per agent role
ROLE_MODELS: dict[str, str] = {
    "extract": os.environ.get("FIONA_MODEL_EXTRACT", "haiku"),
    "reason": os.environ.get("FIONA_MODEL_REASON", "sonnet"),
    "guide": os.environ.get("FIONA_MODEL_GUIDE", "sonnet"),
    "guardian": os.environ.get("FIONA_MODEL_GUARDIAN", "opus"),
    "default": "sonnet",
}


def is_claude_cli_available() -> bool:
    """Return True if the `claude` executable is located on PATH."""
    return shutil.which("claude") is not None


def run_claude_cli(
    prompt: str,
    *,
    role: str = "default",
    system_prompt: str | None = None,
    timeout_seconds: float = 30.0,
    tenant_id: str | None = None,
) -> str:
    """Execute a prompt via headless Claude CLI with smart role-based model routing."""
    if not is_claude_cli_available():
        raise RuntimeError("Claude CLI ('claude') is not found on PATH.")

    model = ROLE_MODELS.get(role, "sonnet")
    # Headless, no tools, no MCP servers, no local settings or slash commands. The prompt goes on
    # stdin, never the command line, so text that starts with "--" can't be read as a CLI flag.
    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--tools",
        "",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    # The workspace's own Claude account, if its owner connected one (fails closed).
    env = credentials.claude_env(tenant_id)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Claude CLI ({model}) timed out after {timeout_seconds}s") from exc

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        log.warning("Claude CLI (%s) failed with code %d: %s", model, proc.returncode, err)
        raise RuntimeError(f"Claude CLI error: {err}")

    raw_output = proc.stdout.strip()
    # Filter any CLI startup warnings (e.g. stdin notice)
    clean_lines = [line for line in raw_output.splitlines() if not line.startswith("Warning:")]
    result = "\n".join(clean_lines).strip()
    log.info(
        "Claude CLI execution success (%s) in %.2fs (%d chars)",
        model,
        time.monotonic() - t0,
        len(result),
    )
    return result
