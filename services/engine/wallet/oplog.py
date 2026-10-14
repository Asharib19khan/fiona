"""Operation log exporter (Deliverable 06, D6).

Exports human-readable and machine-verifiable JSONL operation logs:
- `operations.jsonl`: Proposals, verdicts, approvals, payments, and refusals.
- `audit_chain.jsonl`: Hash-chained audit entries per tenant.
- `verification_report.json`: Cryptographic verification result.
- `README.md`: Submission documentation and verification instructions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from engine.wallet.audit import verify


def export_operation_log(
    conn: psycopg.Connection,
    tenant_id: str,
    out_dir: Path | str,
) -> dict[str, Any]:
    """Export complete operation log and audit chain for the tenant."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Query audit log chain
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT seq, prev_hash, record, hash, proposal_id, recorded_at
              FROM public.audit_log
             WHERE tenant_id = %s
             ORDER BY seq ASC
            """,
            (tenant_id,),
        )
        audit_rows = cur.fetchall()

    audit_chain_file = out_path / "audit_chain.jsonl"
    with audit_chain_file.open("w", encoding="utf-8") as f:
        for r in audit_rows:
            rec = r[2] if isinstance(r[2], dict) else json.loads(r[2])
            line = {
                "seq": r[0],
                "prev_hash": r[1],
                "record": rec,
                "hash": r[3],
                "proposal_id": r[4],
                "recorded_at": r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5]),
            }
            f.write(json.dumps(line) + "\n")

    # 2. Run verification on the chain
    v_res = verify(conn, tenant_id)
    latest_hash = audit_rows[-1][3] if audit_rows else None

    report = {
        "tenant_id": tenant_id,
        "chain_verified": v_res.ok,
        "chain_length": v_res.length,
        "first_bad_seq": v_res.first_bad_seq,
        "latest_hash": latest_hash,
        "verified_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with (out_path / "verification_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # 3. Query proposals, verdicts, approvals, and payment events for operations log
    operations: list[dict[str, Any]] = []

    with conn.cursor() as cur:
        # Proposals
        cur.execute(
            """
            SELECT id, agent, type, amount_minor, currency, summary, created_at
              FROM public.proposals
             WHERE tenant_id = %s
             ORDER BY created_at ASC
            """,
            (tenant_id,),
        )
        for r in cur.fetchall():
            operations.append(
                {
                    "type": "proposal",
                    "id": r[0],
                    "agent": r[1],
                    "action_type": r[2],
                    "amount_minor": r[3],
                    "currency": r[4],
                    "summary": r[5],
                    "timestamp": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
                }
            )

        # Verdicts
        cur.execute(
            """
            SELECT id, proposal_id, outcome, checks, verdict_hash, decided_at
              FROM public.verdicts
             WHERE tenant_id = %s
             ORDER BY decided_at ASC
            """,
            (tenant_id,),
        )
        for r in cur.fetchall():
            operations.append(
                {
                    "type": "verdict",
                    "id": r[0],
                    "proposal_id": r[1],
                    "outcome": r[2],
                    "checks_count": len(r[3]) if isinstance(r[3], list) else 0,
                    "verdict_hash": r[4],
                    "timestamp": r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5]),
                }
            )

        # Approvals
        cur.execute(
            """
            SELECT id, proposal_id, user_id, decision, notes, created_at
              FROM public.approvals
             WHERE tenant_id = %s
             ORDER BY created_at ASC
            """,
            (tenant_id,),
        )
        for r in cur.fetchall():
            operations.append(
                {
                    "type": "approval",
                    "id": r[0],
                    "proposal_id": r[1],
                    "user_id": r[2],
                    "decision": r[3],
                    "notes": r[4],
                    "timestamp": r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5]),
                }
            )

        # Events (supplier payments and bank detail changes)
        cur.execute(
            """
            SELECT id, type, payload, occurred_at
              FROM public.events
             WHERE tenant_id = %s AND type IN ('supplier_payment', 'bank_detail_change')
             ORDER BY occurred_at ASC
            """,
            (tenant_id,),
        )
        for r in cur.fetchall():
            ev_payload = r[2] if isinstance(r[2], dict) else json.loads(r[2])
            operations.append(
                {
                    "type": f"event:{r[1]}",
                    "id": r[0],
                    "payload": ev_payload,
                    "timestamp": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
                }
            )

    # Sort operations by timestamp
    operations.sort(key=lambda op: str(op.get("timestamp", "")))

    operations_file = out_path / "operations.jsonl"
    with operations_file.open("w", encoding="utf-8") as f:
        for idx, op in enumerate(operations, 1):
            op["op_seq"] = idx
            f.write(json.dumps(op) + "\n")

    # 4. Generate README.md
    readme_content = f"""# Fiona Execution Evidence (Deliverable 06)
- **Tenant ID:** `{tenant_id}`
- **Generated At:** `{report["verified_at"]}`
- **Chain Integrity:** `{"VERIFIED (PASS)" if v_res.ok else "TAMPER DETECTED (FAIL)"}`
- **Total Audit Chain Length:** `{v_res.length}` records
- **Latest Hash:** `{latest_hash or "N/A"}`

## Contents

1. `operations.jsonl`: Chronological operational timeline recording agent proposals, Guardian verdicts, owner approvals, and executed supplier payments.
2. `audit_chain.jsonl`: Append-only, hash-chained cryptographic ledger entries where:
   $$\\text{{hash}} = \\text{{sha256}}(\\text{{prev\\_hash}} \\parallel \\text{{canonical\\_json}}(\\text{{record}}))$$
3. `verification_report.json`: Machine-verifiable result confirming zero broken links or corrupted records across the tenant's history.

## Verification Procedure

To independently verify the audit chain:
```python
from engine.ledger.db import connect, tenant_session
from engine.wallet.audit import verify

with connect("fiona_dev") as conn:
    with tenant_session(conn, "{tenant_id}"):
        result = verify(conn, "{tenant_id}")
        assert result.ok is True
        print(f"Audit log verified: {{result.length}} entries.")
```
"""
    with (out_path / "README.md").open("w", encoding="utf-8") as f:
        f.write(readme_content)

    return report
