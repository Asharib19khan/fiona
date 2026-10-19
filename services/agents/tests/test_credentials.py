"""Each workspace's Claude runs use that workspace's own credential, and fail closed."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from fiona_agents import credentials, runtime
from fiona_agents.engine import EngineError

KEY = "sk-ant-api03-" + "k" * 40
TOKEN = "sk-ant-oat01-" + "t" * 40


def test_an_api_key_replaces_both_server_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-key")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "server-token")
    monkeypatch.setattr(credentials, "lookup", lambda t: ("api_key", KEY))
    env = credentials.claude_env("ten_a")
    assert env is not None
    assert env["ANTHROPIC_API_KEY"] == KEY and "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_a_subscription_token_is_used_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-key")
    monkeypatch.setattr(credentials, "lookup", lambda t: ("subscription_token", TOKEN))
    env = credentials.claude_env("ten_a")
    assert env is not None
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN and "ANTHROPIC_API_KEY" not in env


def test_server_mode_inherits_this_machines_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credentials, "lookup", lambda t: ("server", None))
    assert credentials.claude_env("ten_a") is None


def _engine_fails(code: str):
    def get(self: Any, path: str, **params: Any) -> dict[str, Any]:
        raise EngineError(503, code, "boom")

    return get


def test_lookup_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # the real lookup, not the conftest stub
    from fiona_agents import engine

    # A stored secret that can't be opened: never fall back to the server's account.
    monkeypatch.setattr(engine.Engine, "get", _engine_fails("secret_storage_unavailable"))
    with pytest.raises(credentials.CredentialUnavailable):
        credentials.lookup("ten_a")
    # No engine at all: allowed only in local development, refused in live mode.
    monkeypatch.setattr(engine.Engine, "get", _engine_fails("engine_unreachable"))
    monkeypatch.delenv("FIONA_MODE", raising=False)
    assert credentials.lookup("ten_a") == ("server", None)
    monkeypatch.setenv("FIONA_MODE", "live")
    with pytest.raises(credentials.CredentialUnavailable):
        credentials.lookup("ten_a")


def test_an_agent_run_starts_claude_with_the_workspace_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("FIONA_AGENT_HOME", str(tmp_path))
    monkeypatch.setattr(credentials, "lookup", lambda t: ("api_key", KEY))
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "claude")
    seen: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        seen.update(kwargs)
        envelope = {"structured_output": {"ok": True}, "is_error": False}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(envelope), "")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    runtime.structured_call(
        "x", system="s", schema={}, model="m", timeout=5, workdir_name="t", tenant_id="ten_a"
    )
    assert seen["env"]["ANTHROPIC_API_KEY"] == KEY
    assert KEY not in json.dumps([str(v) for k, v in seen.items() if k != "env"])


def test_an_unreadable_connection_stops_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("FIONA_AGENT_HOME", str(tmp_path))
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "claude")

    def broken(tenant_id: str) -> tuple[str, str | None]:
        raise credentials.CredentialUnavailable("no")

    monkeypatch.setattr(credentials, "lookup", broken)
    called: list[int] = []
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: called.append(1))
    with pytest.raises(runtime.AgentFailure):
        runtime.structured_call(
            "x", system="s", schema={}, model="m", timeout=5, workdir_name="t", tenant_id="ten_a"
        )
    assert called == []
