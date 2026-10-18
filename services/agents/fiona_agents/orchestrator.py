"""What runs when: the daily pipeline, the council, paying what the owner approved, the autopilot.

- daily: the Controller reconciles and checks bills, then the Treasurer plans payments on the
  freshly reconciled books. Each proposal goes to the Guardian and waits for the owner.
- council: CFO Strategist, Treasurer and Growth Analyst argue one question in parallel, read each
  other's memos and rebut, then a chair with no tools writes the memo with dissent on record.
  Every figure in that memo is checked against the debate's tool results; anything else is
  flagged as unverified.
- pay_approved: deterministic, no model. Approved payment proposals due today go to the
  sandbox wallet, which re-checks the verdict, the owner's decision and every limit itself.
- autopilot: with AGENTS_AUTOPILOT_MINUTES > 0, pays what was approved and runs the daily
  pipeline on that interval, so the team works without being asked; the owner still decides.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from fiona_agents import runtime
from fiona_agents.engine import Engine, EngineError

log = logging.getLogger("fiona_agents.orchestrator")

DAILY = (
    ("controller", "Reconcile the bank and check this week's bills. Report what needs the owner."),
    ("treasurer", "Plan supplier payments for the next 14 days on the freshly reconciled books."),
)
COUNCIL_ROLES = {
    "cfo_strategist": (
        "cfo_strategist",
        "CFO Strategist: weigh the cost of capital, solvency and the business's stage.",
    ),
    "treasurer": (
        "council_treasurer",
        "Treasurer: protect liquidity; every fixed repayment must be met in the weeks it falls due.",
    ),
    "growth_analyst": (
        "growth_analyst",
        "Growth Analyst: weigh what the money could earn in stock and sales against its cost.",
    ),
}
_PKR = re.compile(r"PKR\s*-?[0-9][0-9,]*(?:\.[0-9]{1,2})?")


def _pipelines_dir():
    path = runtime.home() / "pipelines"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(record: dict[str, Any]) -> None:
    (_pipelines_dir() / f"{record['id']}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def load_pipeline(pipeline_id: str) -> dict[str, Any] | None:
    if not pipeline_id.replace("_", "").isalnum():
        return None
    path = _pipelines_dir() / f"{pipeline_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def list_pipelines(tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
    out = []
    for path in sorted(
        _pipelines_dir().glob("pl_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("tenant_id") == tenant_id:
            out.append(
                {
                    k: record.get(k)
                    for k in ("id", "kind", "status", "question", "started_at", "finished_at")
                }
            )
        if len(out) >= limit:
            break
    return out


def _start(tenant_id: str, kind: str, **extra: Any) -> dict[str, Any]:
    record = {
        "id": f"pl_{kind}_{secrets.token_hex(6)}",
        "tenant_id": tenant_id,
        "kind": kind,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "runs": [],
        **extra,
    }
    _save(record)
    return record


def _finish(record: dict[str, Any], status: str) -> dict[str, Any]:
    record.update(status=status, finished_at=datetime.now(UTC).isoformat())
    _save(record)
    return record


# ---------------------------------------------------------------- daily


def run_daily(tenant_id: str, record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = record or _start(tenant_id, "daily")
    failed = False
    for agent, task in DAILY:
        run = runtime.new_run(tenant_id, agent, task, pipeline_id=record["id"])
        record["runs"].append(run["id"])
        _save(record)
        done = runtime.execute(run)
        failed = failed or done["status"] != "completed"
    return _finish(record, "completed_with_failures" if failed else "completed")


# ---------------------------------------------------------------- council


def _member_task(role: str, question: str) -> str:
    return f"Your role: {role}\n\nThe question before the council:\n{question}"


def _quoted(memos: dict[str, Any]) -> str:
    return "<memos>\n" + json.dumps(memos, ensure_ascii=False, indent=1) + "\n</memos>"


def verify_figures(text: str, tool_results: list[Any]) -> dict[str, list[str]]:
    """Every PKR figure in the memo must appear in some tool result of the debate."""
    seen = json.dumps(tool_results, ensure_ascii=False, default=str)
    known = {re.sub(r"\s+", " ", m) for m in _PKR.findall(seen)}
    cited = {re.sub(r"\s+", " ", m) for m in _PKR.findall(text)}
    return {"verified": sorted(cited & known), "unverified": sorted(cited - known)}


def run_council(
    tenant_id: str, question: str, record: dict[str, Any] | None = None
) -> dict[str, Any]:
    record = record or _start(tenant_id, "council", question=question)

    def member(name: str, prompt: str, task: str, toolbox: str) -> dict[str, Any]:
        run = runtime.new_run(
            tenant_id,
            name,
            task,
            pipeline_id=record["id"],
            prompt=prompt,
            toolbox=toolbox,
            ephemeral=True,
        )
        record["runs"].append(run["id"])
        return runtime.execute(run)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            name: pool.submit(member, name, "council_member", _member_task(role, question), toolbox)
            for name, (toolbox, role) in COUNCIL_ROLES.items()
        }
        first = {name: future.result() for name, future in futures.items()}
    memos = {name: run.get("report") for name, run in first.items() if run["status"] == "completed"}
    record["round_1"] = {
        name: {"run_id": run["id"], "status": run["status"], "memo": run.get("report")}
        for name, run in first.items()
    }
    _save(record)
    if len(memos) < 2:
        return _finish(record, "failed")

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            name: pool.submit(
                member,
                name,
                "council_rebuttal",
                f"{_member_task(COUNCIL_ROLES[name][1], question)}\n\n"
                f"Your first-round memo and the others':\n{_quoted(memos)}",
                "",
            )
            for name in memos
        }
        second = {name: future.result() for name, future in futures.items()}
    rebuttals = {
        name: run.get("report") for name, run in second.items() if run["status"] == "completed"
    }
    record["round_2"] = {
        name: {"run_id": run["id"], "status": run["status"], "rebuttal": run.get("report")}
        for name, run in second.items()
    }
    _save(record)

    chair = member(
        "council_chair",
        "council_chair",
        f"The question:\n{question}\n\nRound 1 memos:\n{_quoted(memos)}\n\nRound 2 rebuttals:\n{_quoted(rebuttals)}",
        "",
    )
    record["memo"] = chair.get("report")
    record["chair_run_id"] = chair["id"]
    if chair["status"] != "completed":
        return _finish(record, "failed")
    tool_results = [
        call.get("result")
        for run in first.values()
        for call in (runtime.load_run(run["id"]) or {}).get("tool_calls", [])
    ]
    record["figure_check"] = verify_figures(
        json.dumps(record["memo"], ensure_ascii=False), [question, *tool_results]
    )
    return _finish(record, "completed")


# ---------------------------------------------------------------- paying what the owner approved


def pay_approved(tenant_id: str) -> list[dict[str, Any]]:
    """Send approved payment proposals due today to the wallet. No model is involved, and the
    wallet itself refuses anything without a cleared or owner-approved verdict."""
    engine = Engine(tenant_id, "treasurer")
    proposals = engine.get("/v1/proposals").get("proposals", [])
    results = []
    for p in proposals:
        payload = p.get("payload") or {}
        if p.get("type") != "payment" or p.get("status") not in ("approved", "cleared"):
            continue
        pay_on = payload.get("pay_on")
        if not pay_on:
            continue
        verdict = p.get("verdict") or {}
        body = {
            "proposal_id": p["id"],
            "verdict_id": verdict.get("id") or p.get("verdict_id"),
            "payee_id": payload.get("payee_id"),
            "amount_minor": (p.get("amount") or {}).get("minor"),
            "currency": (p.get("amount") or {}).get("currency"),
            "pay_on": pay_on,
        }
        try:
            res = engine.post("/v1/wallet/pay", body)
            results.append(
                {"proposal_id": p["id"], "status": res.get("status"), "reason": res.get("reason")}
            )
        except EngineError as exc:
            results.append({"proposal_id": p["id"], "status": "error", "reason": exc.message})
    return results


# ---------------------------------------------------------------- autopilot

_autopilot_stop = threading.Event()


def _autopilot(tenant_id: str, minutes: float) -> None:
    while not _autopilot_stop.wait(minutes * 60):
        try:
            paid = pay_approved(tenant_id)
            if paid:
                log.info("autopilot payments: %s", paid)
            run_daily(tenant_id)
        except Exception:  # the loop must survive one bad cycle
            log.exception("autopilot cycle failed")


def start_autopilot() -> threading.Thread | None:
    minutes = float(os.environ.get("AGENTS_AUTOPILOT_MINUTES", "0") or 0)
    if minutes <= 0:
        return None
    tenant_id = os.environ.get("DEMO_TENANT_ID") or "ten_karachi_apparel"
    thread = threading.Thread(
        target=_autopilot, args=(tenant_id, minutes), name="fiona-autopilot", daemon=True
    )
    thread.start()
    log.info("autopilot on for %s every %s minutes", tenant_id, minutes)
    return thread
