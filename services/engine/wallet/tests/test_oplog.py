"""Tests for operation log export and verification report (Deliverable 06, D6)."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg

from engine.ledger.db import tenant_session
from engine.wallet.audit import append
from engine.wallet.oplog import export_operation_log
from engine.wallet.tests.conftest import seed_wallet_tenant


def test_export_operation_log(conn: psycopg.Connection, tmp_path: Path) -> None:
    """Proves operation log exporter produces valid JSONL files and passing verification report."""
    tenant = "ten_oplog_test"
    seed_wallet_tenant(conn, tenant)

    now = "2026-10-22T09:00:00Z"

    # Add audit log entries and proposals/verdicts
    with tenant_session(conn, tenant):
        append(conn, tenant, {"action": "proposal_created", "amount": 1000000})
        append(conn, tenant, {"action": "payment_refused", "reason": "OVER_CAP"})
        append(conn, tenant, {"action": "supplier_payment_executed", "amount": 5000000})

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.proposals (
                    tenant_id, id, agent, type, created_at, summary, amount_minor, currency, reasoning
                ) VALUES (
                    %s, 'prop_oplog01', 'treasurer', 'payment', %s, 'Sample bill', 5000000, 'PKR', 'Due soon'
                ) ON CONFLICT (tenant_id, id) DO NOTHING
                """,
                (tenant, now),
            )
            cur.execute(
                """
                INSERT INTO public.verdicts (
                    tenant_id, id, proposal_id, outcome, checks, verdict_hash, decided_at
                ) VALUES (
                    %s, 'vrd_oplog01', 'prop_oplog01', 'approve', '[]', 'sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef', %s
                ) ON CONFLICT (tenant_id, id) DO NOTHING
                """,
                (tenant, now),
            )

        report = export_operation_log(conn, tenant, tmp_path)

    assert report["chain_verified"] is True
    assert report["chain_length"] == 3

    # Check files exist
    ops_file = tmp_path / "operations.jsonl"
    chain_file = tmp_path / "audit_chain.jsonl"
    rep_file = tmp_path / "verification_report.json"
    readme_file = tmp_path / "README.md"

    assert ops_file.exists()
    assert chain_file.exists()
    assert rep_file.exists()
    assert readme_file.exists()

    # Verify JSON lines
    with ops_file.open("r", encoding="utf-8") as f:
        ops = [json.loads(line) for line in f]
    assert len(ops) >= 2  # proposal, verdict

    with chain_file.open("r", encoding="utf-8") as f:
        chain_lines = [json.loads(line) for line in f]
    assert len(chain_lines) == 3
    assert chain_lines[0]["seq"] == 1
    assert chain_lines[0]["prev_hash"].startswith("sha256:0000")
    assert chain_lines[1]["prev_hash"] == chain_lines[0]["hash"]
    assert chain_lines[2]["prev_hash"] == chain_lines[1]["hash"]

    # Verify README has content
    assert "Fiona Execution Evidence" in readme_file.read_text(encoding="utf-8")
