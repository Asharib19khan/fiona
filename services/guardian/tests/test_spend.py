from __future__ import annotations

import subprocess
from typing import Any

import pytest

from fiona_guardian import runtime, spend


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("FIONA_AGENT_HOME", str(tmp_path))
    monkeypatch.delenv("LLM_DAILY_BUDGET_USD", raising=False)
    monkeypatch.delenv("LLM_RUN_BUDGET_USD", raising=False)


def test_no_cap_means_no_limit() -> None:
    spend.record(500.0)
    spend.check()


def test_cap_reached_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "1.00")
    spend.record(0.6)
    spend.check()
    spend.record(0.5)
    with pytest.raises(spend.BudgetExhausted, match="used up"):
        spend.check()


def test_a_typo_in_the_cap_stops_spending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "ten dollars")
    with pytest.raises(spend.BudgetExhausted):
        spend.check()


def test_unknown_cost_counts_the_per_run_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_RUN_BUDGET_USD", "0.25")
    spend.record(None)
    spend.record(None)
    assert spend.spent_today() == pytest.approx(0.5)


def test_runtime_refuses_before_starting_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "0.10")
    spend.record(0.2)
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "/usr/bin/claude")

    def never(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("Claude must not start once the daily budget is used up")

    monkeypatch.setattr(runtime.subprocess, "run", never)
    with pytest.raises(runtime.RuntimeFailure, match="budget"):
        runtime.run_structured("prompt", system_prompt="s", schema={}, timeout_seconds=5)
