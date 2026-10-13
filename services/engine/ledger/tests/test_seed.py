"""D1 seed: fixture reference data loads through RLS, matches the files, and re-runs as a no-op."""

from __future__ import annotations

import psycopg

from engine.ledger import db, seed

TABLES = [
    "tenants",
    "mandates",
    "accounts",
    "parties",
    "items",
    "documents",
    "purchase_orders",
    "goods_received",
]


def _counts(conn: psycopg.Connection, tenant: str) -> dict[str, int]:
    with db.tenant_session(conn, tenant):
        return {t: conn.execute(f"select count(*) from public.{t}").fetchone()[0] for t in TABLES}


def test_seed_loads_fixtures_and_is_idempotent(migrated_db: str) -> None:
    with db.connect(migrated_db, autocommit=True) as conn:
        expected = seed.seed_reference_data(conn)
        assert "ten_karachi_apparel" in expected
        for tenant, counts in expected.items():
            assert _counts(conn, tenant) == counts
        seed.seed_reference_data(conn)  # second run adds nothing
        for tenant, counts in expected.items():
            assert _counts(conn, tenant) == counts


def test_seeded_demo_rows_are_queryable(migrated_db: str) -> None:
    with db.connect(migrated_db, autocommit=True) as conn:
        seed.seed_reference_data(conn)
        with db.tenant_session(conn, "ten_karachi_apparel"):
            buffer = conn.execute("select cash_buffer_minor from tenants").fetchone()[0]
            cap = conn.execute(
                "select per_payment_cap_minor from mandates where id = 'mnd_treasurer_v1'"
            ).fetchone()[0]
            changed = conn.execute(
                "select bank_account_changed_at is not null from parties where id = 'sup_017'"
            ).fetchone()[0]
            same_hash = conn.execute(
                "select count(*) from documents where sha256 = (select sha256 from documents where id = 'doc_88')"
            ).fetchone()[0]
    assert buffer == 200_000_000
    assert cap == 15_000_000
    assert changed is True
    assert same_hash == 1  # the same-file duplicate variant arrives in D2
