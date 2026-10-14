"""D3: load the full synthetic dataset into a database with one command (`python -m engine.ledger.db demo-data`).

Order: reset and migrate, seed reference data, import the raw files (bank CSV, POS CSV, bills with their
documents), load the other recorded events (payments, invoices, stock receipts, bank changes, journals),
post every event, and open the simulated wallet account. Every step is idempotent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from engine.ledger import importers, posting, seed

# The loader's clock: recorded_at and posted_at of demo rows, fixed so rebuilds are identical.
DEMO_CLOCK = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)
# Recorded by people or systems other than the three importers.
OTHER_SOURCES = {"manual", "invoicing"}


def load_tenant(conn: psycopg.Connection, folder: Path, *, now: datetime = DEMO_CLOCK) -> dict:
    tenant_id = json.loads((folder / "tenant.json").read_text(encoding="utf-8"))["id"]
    report: dict = {"tenant": tenant_id, "seed": seed.seed_tenant(conn, folder)}
    report["bank"] = importers.import_bank_csv(
        conn, tenant_id, (folder / "bank_statement.csv").read_text(encoding="utf-8"), now=now
    ).as_dict()
    report["pos"] = importers.import_pos_csv(
        conn, tenant_id, (folder / "pos_sales.csv").read_text(encoding="utf-8"), now=now
    ).as_dict()
    bills = json.loads((folder / "bills.json").read_text(encoding="utf-8"))["bills"]
    documents = {b["document_path"]: (folder / b["document_path"]).read_bytes() for b in bills}
    report["bills"] = importers.import_bills(
        conn, tenant_id, bills, documents, storage_prefix=f"data/fixtures/{tenant_id}", now=now
    ).as_dict()
    events = importers.events_from_jsonl((folder / "events.jsonl").read_text(encoding="utf-8"))
    report["other_events"] = importers.import_events(
        conn, tenant_id, events, source_types=OTHER_SOURCES, now=now
    ).as_dict()
    loans_path = folder / "loans.json"
    loans = (
        json.loads(loans_path.read_text(encoding="utf-8"))["loans"] if loans_path.exists() else []
    )
    report["journal_lines"] = posting.post_unposted(
        conn, tenant_id, posting.context_from_db(conn, tenant_id, loans), now=now
    )
    return report


def load_all(conn: psycopg.Connection, fixtures: Path = seed.DEFAULT_FIXTURES) -> list[dict]:
    return [load_tenant(conn, folder) for folder in seed.tenant_dirs(fixtures)]
