"""D1 done-when: two tenants, and tenant A cannot read, write or reference tenant B's data.

Every ledger table gets one row per tenant, written through ``tenant_session`` as the engine
role, so the same test also proves that the engine's grants are enough to do its work.
"""

from __future__ import annotations

import json

import psycopg
import pytest
from psycopg import errors

from engine.ledger import db
from engine.ledger.ids import source_ulid, utc

A = "ten_test_alpha"
B = "ten_test_beta"
T0 = utc(2026, 10, 22, 9)
LEDGER_TABLES = [
    "tenants",
    "mandates",
    "parties",
    "documents",
    "items",
    "purchase_orders",
    "goods_received",
    "events",
    "bank_lines",
    "accounts",
    "journal_lines",
    "matches",
    "proposals",
    "verdicts",
    "audit_log",
]
APPEND_ONLY = ["events", "bank_lines", "proposals", "verdicts", "audit_log"]
HASH = "sha256:" + "ab" * 32
GENESIS = "sha256:" + "00" * 32


def seed_tenant(conn: psycopg.Connection, tenant: str) -> None:
    """One row in every ledger table for ``tenant``. Readable IDs repeat across tenants on purpose."""
    bill_event = source_ulid("evt", T0, tenant, "bill_extraction", "bill_2231")
    bank_event = source_ulid("evt", T0, tenant, "bank_statement", "PK00SYNA#1")
    bank_line = source_ulid("bln", T0, tenant, "bank_statement", "PK00SYNA#1")
    with db.tenant_session(conn, tenant):
        x = conn.execute
        x(
            "insert into tenants (id, name, country, currency, framework, fiscal_year_start_month,"
            " timezone, cash_buffer_minor, created_at) values (%s, %s, 'PK', 'PKR', 'IFRS_SMES', 7,"
            " 'Asia/Karachi', 200000000, %s)",
            (tenant, f"Synthetic {tenant}", T0),
        )
        x(
            "insert into mandates (tenant_id, id, agent, version, currency, per_payment_cap_minor,"
            " daily_cap_minor, allowed_action_types, effective_from, created_at)"
            " values (%s, 'mnd_treasurer_v1', 'treasurer', 1, 'PKR', 20000000, 60000000, '{payment}', '2026-08-01', %s)",
            (tenant, T0),
        )
        x(
            "insert into parties (tenant_id, id, kind, code, name, tax_id, bank_iban, on_allow_list, created_at)"
            " values (%s, 'sup_017', 'supplier', 'S-017', 'Mehran Garments', '4417023-6', 'PK00SYNB', true, %s)",
            (tenant, T0),
        )
        x(
            "insert into documents (tenant_id, id, kind, storage_path, sha256, received_at)"
            " values (%s, 'doc_88', 'bill', 'documents/doc_88.txt', %s, %s)",
            (tenant, "cd" * 32, T0),
        )
        x(
            "insert into items (tenant_id, sku, name, category, currency, unit_cost_minor, price_minor, supplier_id)"
            " values (%s, 'KRT-M-BLU', 'Cotton kurta', 'kurta', 'PKR', 180000, 300000, 'sup_017')",
            (tenant,),
        )
        x(
            "insert into purchase_orders (tenant_id, id, number, supplier_id, ordered_on, status, currency,"
            " lines, total_minor, created_at) values (%s, 'po_1043', 'PO-1043', 'sup_017', '2026-09-10',"
            " 'received', 'PKR', %s, 7200000, %s)",
            (tenant, json.dumps([{"sku": "KRT-M-BLU", "qty": 40, "unit_cost_minor": 180000}]), T0),
        )
        x(
            "insert into goods_received (tenant_id, id, po_id, supplier_id, received_on, lines, created_at)"
            " values (%s, 'grn_1043', 'po_1043', 'sup_017', '2026-09-17', %s, %s)",
            (tenant, json.dumps([{"sku": "KRT-M-BLU", "qty_received": 40}]), T0),
        )
        for event_id, kind, key, party in (
            (bill_event, "purchase_bill", "bill_2231", "sup_017"),
            (bank_event, "bank_line", "PK00SYNA#1", None),
        ):
            x(
                "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, party_id,"
                " currency, payload, source) values (%s, %s, %s, %s, '2026-10-22', %s, %s, 'PKR', %s, %s)",
                (
                    tenant,
                    event_id,
                    kind,
                    T0,
                    T0,
                    party,
                    json.dumps({"total_minor": 18450000}),
                    json.dumps(
                        {
                            "type": "bill_extraction"
                            if kind == "purchase_bill"
                            else "bank_statement",
                            "key": key,
                        }
                    ),
                ),
            )
        x(
            "insert into bank_lines (tenant_id, id, account_iban, line_no, posted_on, narration, amount_minor,"
            " balance_minor, currency, event_id) values (%s, %s, 'PK00SYNA', 1, '2026-10-22',"
            " 'IBFT TO MEHRAN GARMENTS INV 2231', -18450000, 900000000, 'PKR', %s)",
            (tenant, bank_line, bank_event),
        )
        x(
            "insert into accounts (tenant_id, code, name, class, neutral_class) values"
            " (%s, '1000', 'Bank', 'asset', 'cash'), (%s, '2000', 'Payables', 'liability', 'payables')",
            (tenant, tenant),
        )
        for line_no, account, debit, credit in ((1, "2000", 18450000, 0), (2, "1000", 0, 18450000)):
            x(
                "insert into journal_lines (tenant_id, journal_id, line_no, event_id, account_code, debit_minor,"
                " credit_minor, currency, business_date, posted_at)"
                " values (%s, 'jnl_1', %s, %s, %s, %s, %s, 'PKR', '2026-10-22', %s)",
                (tenant, line_no, bank_event, account, debit, credit, T0),
            )
        x(
            "insert into matches (tenant_id, match_id, event_id, bank_line_id, run_id, pass, confidence, created_at)"
            " values (%s, 'mch_1', %s, %s, 'run_1', 'exact', 1, %s)",
            (tenant, bill_event, bank_line, T0),
        )
        x(
            "insert into proposals (tenant_id, id, agent, type, created_at, summary, amount_minor, currency,"
            " payload, evidence, reasoning, mandate_ref) values (%s, 'prop_01JC8Q2R7X', 'treasurer', 'payment',"
            " %s, 'Pay supplier bill INV-2231', 18450000, 'PKR', %s, %s, 'Due on 24 October', 'mnd_treasurer_v1')",
            (
                tenant,
                T0,
                json.dumps({"payee_id": "sup_017"}),
                json.dumps([{"kind": "ledger_row", "ref": "bill_2231"}]),
            ),
        )
        x(
            "insert into verdicts (tenant_id, proposal_id, outcome, checks, decided_at, verdict_hash)"
            " values (%s, 'prop_01JC8Q2R7X', 'block', '[]', %s, %s)",
            (tenant, T0, HASH),
        )
        x(
            "insert into audit_log (tenant_id, seq, prev_hash, record, hash, proposal_id, recorded_at)"
            " values (%s, 1, %s, '{\"action\": \"proposal_stored\"}', %s, 'prop_01JC8Q2R7X', %s)",
            (tenant, GENESIS, HASH, T0),
        )


@pytest.fixture(scope="module")
def two_tenants(migrated_db: str) -> str:
    with db.connect(migrated_db, autocommit=True) as conn:
        for tenant in (A, B):
            seed_tenant(conn, tenant)
        # A supplier that exists only for B, used by the cross-tenant reference test.
        with db.tenant_session(conn, B):
            conn.execute(
                "insert into parties (tenant_id, id, kind, name, created_at)"
                " values (%s, 'sup_900', 'supplier', 'Only in B', %s)",
                (B, T0),
            )
    return migrated_db


def test_every_public_table_has_forced_rls_and_a_policy(
    two_tenants: str, conn: psycopg.Connection
) -> None:
    rows = conn.execute(
        "select c.relname, c.relrowsecurity, c.relforcerowsecurity,"
        " (select count(*) from pg_policies p where p.schemaname = 'public' and p.tablename = c.relname)"
        " from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = 'public' and c.relkind in ('r', 'p')"
    ).fetchall()
    tables = {name for name, *_ in rows}
    assert set(LEDGER_TABLES) <= tables
    for name, enabled, forced, policies in rows:
        assert enabled and forced, f"{name}: RLS must be enabled and forced"
        assert policies >= 1, f"{name}: no RLS policy"


@pytest.mark.parametrize("tenant,other", [(A, B), (B, A)])
@pytest.mark.parametrize("table", LEDGER_TABLES)
def test_tenant_reads_only_its_own_rows(
    two_tenants: str, conn: psycopg.Connection, table: str, tenant: str, other: str
) -> None:
    with db.tenant_session(conn, tenant):
        own = conn.execute(
            f"select count(*) from public.{table} where tenant_id = %s", (tenant,)
        ).fetchone()[0]
        foreign = conn.execute(
            f"select count(*) from public.{table} where tenant_id <> %s", (tenant,)
        ).fetchone()[0]
    assert own >= 1, f"{table}: tenant {tenant} should see its own rows"
    assert foreign == 0, f"{table}: tenant {tenant} can see {foreign} rows of {other}"


def test_without_tenant_context_the_engine_sees_and_writes_nothing(
    two_tenants: str, conn: psycopg.Connection
) -> None:
    with conn.transaction():
        conn.execute(f"set local role {db.ENGINE_ROLE}")
        for table in LEDGER_TABLES:
            assert conn.execute(f"select count(*) from public.{table}").fetchone()[0] == 0, table
        with pytest.raises(errors.InsufficientPrivilege):
            with conn.transaction():
                conn.execute(
                    "insert into accounts (tenant_id, code, name, class, neutral_class) values (%s, '9', 'x', 'asset', 'cash')",
                    (A,),
                )


def test_cannot_insert_rows_for_another_tenant(two_tenants: str, conn: psycopg.Connection) -> None:
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with db.tenant_session(conn, A):
            conn.execute(
                "insert into parties (tenant_id, id, kind, name, created_at) values (%s, 'sup_666', 'supplier', 'x', %s)",
                (B, T0),
            )


def test_cannot_change_or_delete_another_tenants_rows(
    two_tenants: str, conn: psycopg.Connection
) -> None:
    with db.tenant_session(conn, A):
        updated = conn.execute(
            "update parties set name = 'hijacked' where tenant_id = %s", (B,)
        ).rowcount
        deleted = conn.execute("delete from matches where tenant_id = %s", (B,)).rowcount
    assert (updated, deleted) == (0, 0)
    with db.tenant_session(conn, B):
        names = {r[0] for r in conn.execute("select name from parties")}
    assert "hijacked" not in names


def test_cannot_move_a_row_into_another_tenant(two_tenants: str, conn: psycopg.Connection) -> None:
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with db.tenant_session(conn, A):
            conn.execute("update parties set tenant_id = %s where id = 'sup_017'", (B,))


def test_rows_cannot_reference_another_tenants_rows(
    two_tenants: str, conn: psycopg.Connection
) -> None:
    # Even the superuser, who bypasses RLS, cannot point A's goods receipt at B's supplier.
    with pytest.raises(errors.ForeignKeyViolation):
        conn.execute(
            "insert into goods_received (tenant_id, id, supplier_id, received_on, lines, created_at)"
            " values (%s, 'grn_x', 'sup_900', '2026-10-01', '[]', %s)",
            (A, T0),
        )


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_append_only_tables_reject_update_delete_truncate(
    two_tenants: str, conn: psycopg.Connection, table: str
) -> None:
    # The owner (here the superuser) is stopped by the trigger...
    for statement in (
        f"update public.{table} set tenant_id = tenant_id",
        f"delete from public.{table}",
        f"truncate public.{table} cascade",
    ):
        with pytest.raises(errors.RestrictViolation, match="append-only"):
            conn.execute(statement)
    # ...and the engine role is stopped by its grants before the trigger runs.
    with pytest.raises(errors.InsufficientPrivilege):
        with db.tenant_session(conn, A):
            conn.execute(f"delete from public.{table}")


def test_unbalanced_journal_is_rejected_at_commit(
    two_tenants: str, conn: psycopg.Connection
) -> None:
    event_id = source_ulid("evt", T0, A, "bank_statement", "PK00SYNA#1")
    with pytest.raises(errors.CheckViolation, match="unbalanced"):
        with db.tenant_session(conn, A):
            conn.execute(
                "insert into journal_lines (tenant_id, journal_id, line_no, event_id, account_code, debit_minor,"
                " credit_minor, currency, business_date, posted_at)"
                " values (%s, 'jnl_bad', 1, %s, '1000', 100, 0, 'PKR', '2026-10-22', %s)",
                (A, event_id, T0),
            )


def test_money_is_never_a_float(migrated_db: str, conn: psycopg.Connection) -> None:
    columns = conn.execute(
        "select table_name, column_name, data_type from information_schema.columns where table_schema = 'public'"
    ).fetchall()
    for table, column, data_type in columns:
        assert data_type not in {"real", "double precision", "money"}, (
            f"{table}.{column} is {data_type}"
        )
        if column.endswith("_minor"):
            assert data_type == "bigint", f"{table}.{column} must be bigint minor units"


def test_migrations_are_idempotent(migrated_db: str, conn: psycopg.Connection) -> None:
    assert db.apply_migrations(conn) == []
    versions = [
        r[0]
        for r in conn.execute(
            "select version from supabase_migrations.schema_migrations order by 1"
        )
    ]
    assert versions == [p.stem.split("_", 1)[0] for p in db.migration_files()]


def test_tenant_session_refuses_an_open_transaction(migrated_db: str) -> None:
    with db.connect(migrated_db) as conn:  # not autocommit: the first statement opens a transaction
        conn.execute("select 1")
        with pytest.raises(RuntimeError, match="no open transaction"):
            with db.tenant_session(conn, A):
                pass
