"""The agent runtime: one headless Claude process per agent run, each with its own memory.

Every agent is a separate `claude -p` process with:
- its own versioned system prompt (prompts/<agent>.md) and model (FIONA_MODEL_<AGENT>, else the
  role default: Sonnet for reasoning agents);
- its own toolbox, served by `fiona_agents.mcp_server` for that agent only, and no built-in
  tools (no shell, no files, no web): `--tools ""`, `--strict-mcp-config`;
- its own working directory outside the repository, so no CLAUDE.md, settings, hooks or skills
  leak in (`--setting-sources ""`, `--disable-slash-commands`);
- its own conversation, resumed run after run (`--session-id` then `--resume`), so the
  Treasurer remembers what it proposed yesterday and why. `reset_memory` starts it afresh;
- a structured report validated against its JSON Schema (`--json-schema`);
- a hard timeout and an optional dollar budget per run (LLM_RUN_BUDGET_USD).

Each run is recorded under FIONA_AGENT_HOME/runs: status, report, cost, session and the journal
of every tool call the MCP server made. Nothing here can move money: agents only propose.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("fiona_agents.runtime")

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
AGENTS = ("controller", "treasurer", "cfo_strategist", "growth_analyst", "council_chair")
DEFAULT_MODELS = {
    "controller": "claude-sonnet-5-5",
    "treasurer": "claude-sonnet-5-5",
    "cfo_strategist": "claude-sonnet-5-5",
    "growth_analyst": "claude-sonnet-5-5",
    "council_chair": "claude-sonnet-5-5",
}
_locks: dict[str, threading.Lock] = {name: threading.Lock() for name in AGENTS}


class AgentFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class Prompt:
    agent: str
    version: str
    system: str
    schema: dict[str, Any]


def home() -> Path:
    root = Path(os.environ.get("FIONA_AGENT_HOME") or Path(tempfile.gettempdir()) / "fiona-agents")
    root.mkdir(parents=True, exist_ok=True)
    return root


def model_for(agent: str) -> str:
    return (
        os.environ.get(f"FIONA_MODEL_{agent.upper()}")
        or os.environ.get("FIONA_MODEL_REASON")
        or DEFAULT_MODELS[agent]
    )


def load_prompt(agent: str) -> Prompt:
    """prompts/<agent>.md: a front block (version and output schema as JSON), then the prompt."""
    text = (PROMPTS / f"{agent}.md").read_text(encoding="utf-8")
    head, _, body = text.partition("\n---\n")
    meta = json.loads(head.removeprefix("<!--").removesuffix("-->").strip())
    return Prompt(agent=agent, version=meta["version"], system=body.strip(), schema=meta["schema"])


# ---------------------------------------------------------------- memory


def _sessions_file() -> Path:
    return home() / "sessions.json"


def _sessions() -> dict[str, str]:
    path = _sessions_file()
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _save_session(key: str, session_id: str | None) -> None:
    sessions = _sessions()
    if session_id is None:
        sessions.pop(key, None)
    else:
        sessions[key] = session_id
    _sessions_file().write_text(json.dumps(sessions, indent=2), encoding="utf-8")


def reset_memory(tenant_id: str, agent: str) -> None:
    _save_session(f"{tenant_id}:{agent}", None)


# ---------------------------------------------------------------- runs


def _runs_dir() -> Path:
    path = home() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_run(record: dict[str, Any]) -> None:
    path = _runs_dir() / f"{record['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def load_run(run_id: str) -> dict[str, Any] | None:
    if not run_id.replace("_", "").isalnum():
        return None
    path = _runs_dir() / f"{run_id}.json"
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    journal = _runs_dir() / f"{run_id}.journal.jsonl"
    if journal.is_file():
        record["tool_calls"] = [
            json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
        ]
    return record


def list_runs(tenant_id: str, limit: int = 30) -> list[dict[str, Any]]:
    records = []
    for path in sorted(
        _runs_dir().glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("tenant_id") == tenant_id:
            records.append(
                {
                    k: record.get(k)
                    for k in (
                        "id",
                        "agent",
                        "task",
                        "status",
                        "started_at",
                        "finished_at",
                        "cost_usd",
                        "summary",
                        "pipeline_id",
                    )
                }
            )
        if len(records) >= limit:
            break
    return records


def new_run(
    tenant_id: str,
    agent: str,
    task: str,
    *,
    pipeline_id: str | None = None,
    prompt: str | None = None,
    toolbox: str | None = None,
    ephemeral: bool = False,
) -> dict[str, Any]:
    """A queued run. `prompt` and `toolbox` default to the agent's own; `toolbox=""` gives no
    tools. An ephemeral run (a council round) neither reads nor extends the agent's memory."""
    if agent not in AGENTS:
        raise AgentFailure(f"unknown agent {agent!r}")
    record = {
        "id": f"run_{agent}_{secrets.token_hex(6)}",
        "tenant_id": tenant_id,
        "agent": agent,
        "task": task,
        "pipeline_id": pipeline_id,
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "model": model_for(agent),
        "prompt": prompt or agent,
        "toolbox": agent if toolbox is None else toolbox,
        "ephemeral": ephemeral,
        "replayed": False,
    }
    save_run(record)
    return record


def _mcp_config(agent: str, toolbox: str, tenant_id: str, journal: Path) -> str:
    args = ["-m", "fiona_agents.mcp_server", "--agent", agent, "--toolbox", toolbox]
    args += ["--tenant", tenant_id, "--journal", str(journal)]
    return json.dumps({"mcpServers": {"fiona": {"command": sys.executable, "args": args}}})


def execute(record: dict[str, Any], *, timeout_seconds: float | None = None) -> dict[str, Any]:
    """Run one agent to completion and return the finished record. Never raises for model
    trouble: a failed run is recorded as failed, with the reason."""
    agent = record["agent"]
    timeout = timeout_seconds or float(os.environ.get("AGENT_TIMEOUT_SECONDS", "420"))
    journal = _runs_dir() / f"{record['id']}.journal.jsonl"
    with _locks[agent]:  # one run per agent at a time: its memory is one conversation
        record.update(status="running", started_at=datetime.now(UTC).isoformat())
        save_run(record)
        started = time.monotonic()
        try:
            result = _invoke(record, journal, timeout)
            record.update(status="completed", **result)
        except AgentFailure as exc:
            record.update(status="failed", error=str(exc)[:600])
            log.warning("%s run %s failed: %s", agent, record["id"], exc)
        record.update(
            finished_at=datetime.now(UTC).isoformat(),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        save_run(record)
    return load_run(record["id"]) or record


def _invoke(record: dict[str, Any], journal: Path, timeout: float) -> dict[str, Any]:
    agent, tenant_id = record["agent"], record["tenant_id"]
    executable = shutil.which("claude")
    if executable is None:
        raise AgentFailure("Claude CLI ('claude') is not on PATH")
    prompt = load_prompt(record.get("prompt") or agent)
    toolbox = record.get("toolbox", agent)
    ephemeral = bool(record.get("ephemeral"))
    workdir = home() / "work" / agent
    workdir.mkdir(parents=True, exist_ok=True)

    key = f"{tenant_id}:{agent}"
    session = None if ephemeral else _sessions().get(key)
    cmd = [
        executable,
        "-p",
        "--model",
        record["model"],
        "--system-prompt",
        prompt.system,
        "--json-schema",
        json.dumps(prompt.schema),
        "--output-format",
        "json",
        "--strict-mcp-config",
        "--tools",
        "",
        "--setting-sources",
        "",
        "--disable-slash-commands",
    ]
    if toolbox:
        cmd += ["--mcp-config", _mcp_config(agent, toolbox, tenant_id, journal)]
        cmd += ["--allowedTools", "mcp__fiona"]
    if ephemeral:
        cmd += ["--no-session-persistence"]
    elif session:
        cmd += ["--resume", session]
    else:
        session = str(uuid.uuid4())
        cmd += ["--session-id", session]
    budget = os.environ.get("LLM_RUN_BUDGET_USD")
    if budget:
        cmd += ["--max-budget-usd", budget]

    task = f"Today's task (run {record['id']}, tenant {tenant_id}):\n{record['task']}"
    try:
        proc = subprocess.run(
            cmd,
            input=task,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentFailure(f"{agent} timed out after {timeout:.0f}s") from exc
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        detail = (proc.stderr or proc.stdout).strip()[:400]
        if session and "--resume" in cmd and "session" in detail.lower():
            reset_memory(tenant_id, agent)  # a lost session must not block the agent forever
        raise AgentFailure(f"Claude CLI exited {proc.returncode}: {detail}") from exc
    if envelope.get("is_error") or proc.returncode != 0:
        raise AgentFailure(f"Claude CLI error: {str(envelope.get('result'))[:400]}")
    report = envelope.get("structured_output")
    if not isinstance(report, dict):
        raise AgentFailure("the agent returned no structured report")
    if not ephemeral:
        _save_session(key, envelope.get("session_id") or session)
    return {
        "report": report,
        "summary": str(report.get("summary", ""))[:500],
        "session_id": envelope.get("session_id") or session,
        "prompt_version": prompt.version,
        "cost_usd": envelope.get("total_cost_usd"),
        "turns": envelope.get("num_turns"),
    }
