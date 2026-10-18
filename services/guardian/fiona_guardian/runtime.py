"""The Guardian's own Claude process (R8: no code or prompts shared with services/agents).

Each review is one headless `claude -p` run, isolated from this repository and from the
operator's own Claude setup: it starts in an empty working directory outside the repo, with a
replacement system prompt, no tools, no MCP servers, no settings, hooks or slash commands, and
no saved session. The answer must match a JSON Schema; Claude Code validates it and returns it
as `structured_output`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("fiona_guardian.runtime")

DEFAULT_MODEL = "claude-opus-5-5"


class RuntimeFailure(RuntimeError):
    """The model could not produce a valid answer. Callers treat this as fail closed."""


@dataclass(frozen=True)
class ModelAnswer:
    output: dict[str, Any]
    model: str
    latency_ms: int
    cost_usd: float | None


def model_name() -> str:
    return os.environ.get("FIONA_MODEL_GUARDIAN") or DEFAULT_MODEL


def cli_available() -> bool:
    return shutil.which("claude") is not None


def _workdir() -> Path:
    """An empty directory outside the repository, so no CLAUDE.md is ever discovered."""
    root = Path(os.environ.get("FIONA_AGENT_HOME") or Path(tempfile.gettempdir()) / "fiona-agents")
    path = root / "guardian"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_structured(
    prompt: str,
    *,
    system_prompt: str,
    schema: dict[str, Any],
    timeout_seconds: float,
) -> ModelAnswer:
    executable = shutil.which("claude")
    if executable is None:
        raise RuntimeFailure("Claude CLI ('claude') is not on PATH")
    model = model_name()
    cmd = [
        executable,
        "-p",
        "--model",
        model,
        "--system-prompt",
        system_prompt,
        "--json-schema",
        json.dumps(schema),
        "--output-format",
        "json",
        "--tools",
        "",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    budget = os.environ.get("LLM_RUN_BUDGET_USD")
    if budget:
        cmd += ["--max-budget-usd", budget]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,  # the prompt goes on stdin: no command-line length limit, no quoting
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            cwd=_workdir(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeFailure(f"{model} timed out after {timeout_seconds:.0f}s") from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        detail = (proc.stderr or proc.stdout).strip()[:300]
        raise RuntimeFailure(f"Claude CLI exited {proc.returncode}: {detail}") from exc
    if envelope.get("is_error") or proc.returncode != 0:
        raise RuntimeFailure(f"Claude CLI error: {str(envelope.get('result'))[:300]}")
    output = envelope.get("structured_output")
    if not isinstance(output, dict):
        raise RuntimeFailure("The model returned no structured output")
    log.info("guardian review by %s in %d ms", model, latency_ms)
    return ModelAnswer(
        output=output,
        model=f"claude_cli:{model}",
        latency_ms=latency_ms,
        cost_usd=envelope.get("total_cost_usd"),
    )
