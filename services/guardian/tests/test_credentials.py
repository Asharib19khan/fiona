"""The Guardian reviews with the workspace's own Claude account, and fails closed."""

from __future__ import annotations

from typing import Any

import pytest

from fiona_guardian import api, credentials, engine_client, reviewer

TOKEN = "sk-ant-oat01-" + "t" * 40


def test_a_subscription_token_is_the_only_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-key")
    monkeypatch.setattr(
        engine_client, "ai_credential", lambda t: {"mode": "subscription_token", "secret": TOKEN}
    )
    env = credentials.claude_env("ten_a")
    assert env is not None
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN and "ANTHROPIC_API_KEY" not in env


def test_an_unreadable_connection_becomes_an_error_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIONA_LLM_PROVIDER", "claude_cli")
    monkeypatch.delenv("AGENTS_FORCE_REPLAY", raising=False)

    def broken(tenant_id: str) -> dict[str, Any]:
        raise engine_client.EngineError(503, "secret storage unavailable")

    monkeypatch.setattr(engine_client, "ai_credential", broken)
    called: list[int] = []
    monkeypatch.setattr(reviewer, "review", lambda *a, **k: called.append(1) or {})
    answer = api._review_with_workspace_claude("ten_a", {"reviewed_verdict_id": "vrd_1"})
    assert called == [] and answer["error"].startswith("AI connection")


def test_the_review_gets_the_workspace_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIONA_LLM_PROVIDER", "claude_cli")
    monkeypatch.delenv("AGENTS_FORCE_REPLAY", raising=False)
    monkeypatch.setattr(
        engine_client, "ai_credential", lambda t: {"mode": "subscription_token", "secret": TOKEN}
    )
    seen: dict[str, Any] = {}
    monkeypatch.setattr(reviewer, "review", lambda packet, **k: seen.update(k) or {"ok": 1})
    api._review_with_workspace_claude("ten_a", {})
    assert seen["claude_env"]["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
