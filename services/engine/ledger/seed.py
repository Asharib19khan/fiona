"""D1 seed: load each tenant's reference data from the fixtures into the ledger tables.

Loads tenants, mandates, accounts, parties, items, documents, purchase orders and goods
received. Events, bank lines and postings come from the D3 importers (``demo-data``).
Every write goes through ``tenant_session``, so RLS checks the seed like any other write.
Re-running is a no-op (``on conflict do nothing``). Timestamps come from the fixture period,
never from the wall clock.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from engine.ledger import db

DEFAULT_FIXTURES = db.REPO_ROOT / "data" / "fixtures"
MANDATE_COLUMNS = {
    "tenant_id",
    "id",
    "agent",
    "version",
    "currency",
    "per_payment_cap_minor",
    "daily_cap_minor",
    "allowed_action_types",
    "effective_from",
}


def _csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            {k: (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(handle)
        ]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def tenant_dirs(fixtures: Path) -> list[Path]:
    return sorted(p for p in fixtures.iterdir() if (p / "manifest.json").is_file())


def seed_tenant(conn: psycopg.Connection, folder: Path) -> dict[str, int]:
    tenant = _json(folder / "tenant.json")
    tid = tenant["id"]
    created = f"{tenant['period']['start']}T00:00:00Z"
    counts: dict[str, int] = {}
    with db.tenant_session(conn, tid):
        x = conn.execute
        x(
            "insert into tenants (id, name, country, currency, minor_unit, framework, fiscal_year_start_month, timezone,"
            " cash_buffer_minor, is_synthetic, profile, created_at)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
            (
                tid,
                tenant["name"],
                tenant["country"],
                tenant["currency"],
                tenant["minor_unit"],
                tenant["framework"],
                tenant["fiscal_year_start_month"],
                tenant["timezone"],
                tenant["policies"].get("cash_buffer_minor"),
                tenant.get("synthetic", True),
                Jsonb(
                    {
                        k: tenant[k]
                        for k in (
                            "as_of",
                            "period",
                            "branches",
                            "bank_accounts",
                            "country_pack_draft",
                        )
                    }
                ),
                created,
            ),
        )
        mandates = _json(folder / "mandates.json")["mandates"]
        for m in mandates:
            x(
                "insert into mandates (tenant_id, id, agent, version, currency, per_payment_cap_minor, daily_cap_minor,"
                " allowed_action_types, policy, source, effective_from, created_at)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'rulebook_default', %s, %s) on conflict do nothing",
                (
                    tid,
                    m["id"],
                    m["agent"],
                    m["version"],
                    m["currency"],
                    m["per_payment_cap_minor"],
                    m["daily_cap_minor"],
                    m["allowed_action_types"],
                    Jsonb({k: v for k, v in m.items() if k not in MANDATE_COLUMNS}),
                    m["effective_from"],
                    created,
                ),
            )
        accounts = _csv(folder / "accounts.csv")
        with conn.cursor() as cur:
            cur.executemany(
                "insert into accounts (tenant_id, code, name, class, neutral_class) values (%s, %s, %s, %s, %s)"
                " on conflict do nothing",
                [(tid, a["code"], a["name"], a["class"], a["neutral_class"]) for a in accounts],
            )
            parties = _csv(folder / "parties.csv")
            cur.executemany(
                "insert into parties (tenant_id, id, kind, code, name, tax_id, tax_id_type, bank_iban,"
                " bank_account_changed_at, on_allow_list, payment_terms_days, phone, city, created_at)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                [
                    (
                        tid,
                        p["party_id"],
                        p["kind"],
                        p["code"],
                        p["name"],
                        p["tax_id"],
                        p["tax_id_type"],
                        p["bank_iban"],
                        p["bank_account_changed_at"],
                        p["on_allow_list"] == "true",
                        int(p["payment_terms_days"]),
                        p["phone"],
                        p["city"],
                        created,
                    )
                    for p in parties
                ],
            )
            items = _csv(folder / "items.csv")
            cur.executemany(
                "insert into items (tenant_id, sku, name, category, size, colour, season, currency, unit_cost_minor,"
                " price_minor, opening_stock_qty, reorder_level, supplier_id, lead_time_days, launched_on)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                [
                    (
                        tid,
                        i["sku"],
                        i["name"],
                        i["category"],
                        i["size"],
                        i["colour"],
                        i["season"],
                        i["currency"],
                        int(i["unit_cost_minor"]),
                        int(i["price_minor"]),
                        int(i["opening_stock_qty"]),
                        int(i["reorder_level"]),
                        i["supplier_id"],
                        int(i["lead_time_days"]),
                        i["launched_on"],
                    )
                    for i in items
                ],
            )
            bills = _json(folder / "bills.json")["bills"]
            cur.executemany(
                "insert into documents (tenant_id, id, kind, storage_path, sha256, mime_type, size_bytes, extracted,"
                " received_at) values (%s, %s, 'bill', %s, %s, %s, %s, %s, %s) on conflict do nothing",
                [
                    (
                        tid,
                        b["document_id"],
                        f"data/fixtures/{tid}/{b['document_path']}",
                        b["document_sha256"],
                        "application/pdf" if b["document_path"].endswith(".pdf") else "text/plain",
                        (folder / b["document_path"]).stat().st_size,
                        Jsonb(b),
                        b["received_at"],
                    )
                    for b in bills
                ],
            )
            pos = _json(folder / "purchase_orders.json")["purchase_orders"]
            cur.executemany(
                "insert into purchase_orders (tenant_id, id, number, supplier_id, ordered_on, expected_on, status,"
                " currency, lines, total_minor, created_at) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " on conflict do nothing",
                [
                    (
                        tid,
                        p["po_id"],
                        p["number"],
                        p["supplier_id"],
                        p["ordered_on"],
                        p["expected_on"],
                        p["status"],
                        p["currency"],
                        Jsonb(p["lines"]),
                        p["total_minor"],
                        created,
                    )
                    for p in pos
                ],
            )
            grns = _json(folder / "goods_received.json")["goods_received"]
            cur.executemany(
                "insert into goods_received (tenant_id, id, po_id, supplier_id, received_on, lines, created_at)"
                " values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                [
                    (
                        tid,
                        g["grn_id"],
                        g["po_id"],
                        g["supplier_id"],
                        g["received_on"],
                        Jsonb(g["lines"]),
                        created,
                    )
                    for g in grns
                ],
            )
        counts = {
            "tenants": 1,
            "mandates": len(mandates),
            "accounts": len(accounts),
            "parties": len(parties),
            "items": len(items),
            "documents": len(bills),
            "purchase_orders": len(pos),
            "goods_received": len(grns),
        }
    return counts


def seed_reference_data(
    conn: psycopg.Connection, fixtures: Path = DEFAULT_FIXTURES
) -> dict[str, dict[str, int]]:
    """Seed every tenant folder under ``fixtures``. Returns rows read per table per tenant."""
    return {folder.name: seed_tenant(conn, folder) for folder in tenant_dirs(fixtures)}
