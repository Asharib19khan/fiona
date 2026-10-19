"""Reconsideration: only rejected proposals, the CFO's note always reaches the supplier verbatim,
the right follow-up for each source, and failures recorded instead of raised. Model and engine
are faked."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from fiona_agents import reconsider, runtime
from fiona_agents.main import create_app

PROPOSAL = {
    "id": "prop_1",
    "status": "rejected",
    "summary": "Pay Saddar Embroidery Works for bill_2253",
    "reasoning": "Due 2026-10-23.",
    "amount": {"minor": 15_000_000, "currency": "PKR"},
    "payload": {"bill_id": "bill_2253", "payee_id": "sup_004", "pay_on": "2026-10-23"},
    "verdict": {"checks": [{"rule": "G-12", "outcome": "escalate", "audit": {"reasons": ["x"]}}]},
}


class FakeEngine:
    status = "rejected"

    def __init__(self, tenant_id: str, agent: str) -> None:
        pass

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        if path.startswith("/v1/proposals/"):
            return {**PROPOSAL, "status": FakeEngine.status}
        if path.startswith("/v1/bills/"):
            return {
                "bill": {
                    "supplier_id": "sup_004",
                    "number": "SEW-1716",
                    "due_date": "2026-10-23",
                    "total": {"minor": 15_000_000},
                    "open": {"minor": 15_000_000},
                }
            }
        if path == "/v1/parties":
            return {"parties": [{"id": "sup_004", "name": "Saddar Embroidery Works"}]}
        raise AssertionError(path)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> dict[str, Any]:
    monkeypatch.setenv("FIONA_AGENT_HOME", str(tmp_path))
    monkeypatch.setenv("FIONA_LLM_PROVIDER", "claude_cli")
    monkeypatch.delenv("INTERNAL_JWT_SECRET", raising=False)
    monkeypatch.delenv("FIONA_MODE", raising=False)
    monkeypatch.delenv("LLM_DAILY_BUDGET_USD", raising=False)
    monkeypatch.setattr(reconsider, "Engine", FakeEngine)
    FakeEngine.status = "rejected"
    state: dict[str, Any] = {"answer": "", "runs": []}
    monkeypatch.setattr(
        "fiona_agents.cli_bridge.run_claude_cli", lambda prompt, **kw: state["answer"]
    )
    monkeypatch.setattr(reconsider, "_background", lambda fn, *a: fn(*a))
    monkeypatch.setattr(runtime, "execute", lambda run: state["runs"].append(run))
    return state


def _post(note: str = "Freight looks inflated") -> dict[str, Any]:
    client = TestClient(create_app())
    res = client.post("/v1/agents/reconsider", json={"proposal_ids": ["prop_1"], "note": note})
    assert res.status_code == 202, res.text
    return client.get("/v1/agents/reconsiderations").json()["reconsiderations"][0]


def test_supplier_problem_drafts_email_with_cfo_note_verbatim(env: dict[str, Any]) -> None:
    env["answer"] = (
        'Here: {"source": "supplier", "summary": "The freight line was worked backwards.",'
        ' "findings": ["Freight 471,864 is odd"], "treasurer_fix": null,'
        ' "email_subject": "Bill SEW-1716", "email_body": "Please send a corrected bill."}'
    )
    record = _post()
    assert record["status"] == "done"
    assert record["source"] == "supplier"
    assert record["email"]["to"] == "Saddar Embroidery Works"
    assert record["email"]["simulated"] is True
    assert "“Freight looks inflated”" in record["email"]["body"]
    assert env["runs"] == []


def test_treasurer_problem_starts_a_replan(env: dict[str, Any]) -> None:
    env["answer"] = (
        '{"source": "treasurer", "summary": "I paid after the due date.",'
        ' "findings": ["pay_on was late"], "treasurer_fix": "Pay on the due date."}'
    )
    record = _post()
    assert record["source"] == "treasurer"
    assert "email" not in record
    assert len(env["runs"]) == 1
    assert "Freight looks inflated" in env["runs"][0]["task"]
    assert record["rerun_id"] == env["runs"][0]["id"]


def test_supplier_blame_without_email_fails_closed(env: dict[str, Any]) -> None:
    env["answer"] = '{"source": "supplier", "summary": "Bad bill.", "findings": ["x"]}'
    record = _post()
    assert record["status"] == "failed"
    assert "no email" in record["error"]


def test_only_rejected_proposals_can_be_reconsidered(env: dict[str, Any]) -> None:
    FakeEngine.status = "needs_owner"
    client = TestClient(create_app())
    res = client.post("/v1/agents/reconsider", json={"proposal_ids": ["prop_1"], "note": ""})
    assert res.status_code == 202
    body = res.json()
    assert body["reconsiderations"] == []
    assert body["skipped"][0]["reason"].startswith("Reject it first")


def test_off_when_live_agents_are_off(env: dict[str, Any], monkeypatch: Any) -> None:
    monkeypatch.setenv("FIONA_LLM_PROVIDER", "replay")
    client = TestClient(create_app())
    res = client.post("/v1/agents/reconsider", json={"proposal_ids": ["prop_1"]})
    assert res.status_code == 503


def test_retry_without_note_keeps_the_cfo_note(env: dict[str, Any], monkeypatch: Any) -> None:
    decisions = [{"decision": "reject", "note": "Sent back for reconsideration: check freight"}]
    monkeypatch.setitem(PROPOSAL, "decisions", decisions)
    env["answer"] = '{"source": "neither", "summary": "Fine.", "findings": ["ok"]}'
    record = _post(note="")
    assert record["note"] == "check freight"
