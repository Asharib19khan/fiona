"""Export one proposal's full trail as evidence: agent run, tool calls, proposal, verdict chain,
owner decisions, wallet payment, journal lines and audit records, plus the chain check.

Run from the repo root against the local database (or DATABASE_URL):
    uv run --project services/engine python scripts/export_evidence.py <out_dir> <prop_id>[=<agent_run_id>] ...

Agent run records are read from FIONA_AGENT_HOME/runs (default: <temp>/fiona-agents/runs).
The data is synthetic; nothing here is secret (no tokens or keys are stored with a run).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services"))

from engine.ledger import db  # noqa: E402
from engine.wallet.audit import verify  # noqa: E402

TENANT = os.environ.get("DEMO_TENANT_ID", "ten_karachi_apparel")


def _rows(conn, sql: str, params: tuple) -> list[dict]:
    cur = conn.execute(sql, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def export(conn, proposal_id: str, run_id: str | None) -> dict:
    with db.tenant_session(conn, TENANT):
        proposal = _rows(conn, "select * from proposals where id = %s", (proposal_id,))
        if not proposal:
            raise SystemExit(f"no proposal {proposal_id} in {TENANT}")
        verdicts = _rows(
            conn,
            "select id, outcome, decided_at, verdict_hash, previous_verdict_id, body from verdicts"
            " where proposal_id = %s order by decided_at, id",
            (proposal_id,),
        )
        decisions = _rows(
            conn,
            "select id, verdict_id, decision, decided_by, decided_at, note from decisions"
            " where proposal_id = %s order by decided_at",
            (proposal_id,),
        )
        payments = _rows(
            conn,
            "select id, type, occurred_at, business_date, payload from events"
            " where type = 'supplier_payment' and payload->>'proposal_id' = %s",
            (proposal_id,),
        )
        journal = _rows(
            conn,
            "select event_id, journal_id, line_no, account_code, debit_minor, credit_minor, currency"
            " from journal_lines where event_id = any(%s) order by journal_id, line_no",
            ([p["id"] for p in payments],),
        )
        audit = _rows(
            conn,
            "select seq, record, prev_hash, hash from audit_log where proposal_id = %s order by seq",
            (proposal_id,),
        )
        chain = verify(conn, TENANT)
    run, tool_calls = None, []
    if run_id:
        runs = (
            Path(os.environ.get("FIONA_AGENT_HOME") or Path(tempfile.gettempdir()) / "fiona-agents")
            / "runs"
        )
        run = json.loads((runs / f"{run_id}.json").read_text(encoding="utf-8"))
        run.pop("session_id", None)
        journal_file = runs / f"{run_id}.journal.jsonl"
        if journal_file.exists():
            tool_calls = [
                json.loads(line)
                for line in journal_file.read_text(encoding="utf-8").splitlines()
                if line
            ]
    return {
        "notice": "SYNTHETIC DATA and SIMULATED payments: an invented business; no real money moved.",
        "tenant_id": TENANT,
        "proposal_id": proposal_id,
        "agent_run": run,
        "agent_tool_calls": tool_calls,
        "proposal": proposal[0],
        "verdict_chain": verdicts,
        "owner_decisions": decisions,
        "wallet_payments": payments,
        "journal_lines": journal,
        "journal_balanced": sum(j["debit_minor"] for j in journal)
        == sum(j["credit_minor"] for j in journal),
        "audit_records": audit,
        "audit_chain": {
            "verified": chain.ok,
            "length": chain.length,
            "first_bad_seq": chain.first_bad_seq,
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    with db.connect(autocommit=True) as conn:
        for arg in argv[1:]:
            proposal_id, _, run_id = arg.partition("=")
            data = export(conn, proposal_id, run_id or None)
            path = out / f"{proposal_id}.json"
            path.write_text(
                json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(
                f"{path}: {len(data['verdict_chain'])} verdicts, {len(data['wallet_payments'])} payments,"
                f" chain verified={data['audit_chain']['verified']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
