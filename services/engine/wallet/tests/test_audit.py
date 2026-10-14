"""Tests for hash-chained audit log append, verify, and tamper detection (D6)."""

from __future__ import annotations

import psycopg
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.ledger.db import tenant_session
from engine.wallet.audit import append, verify
from engine.wallet.tests.conftest import seed_wallet_tenant

record_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=["L", "N"])),
    values=st.one_of(
        st.integers(min_value=-1000000, max_value=1000000),
        st.text(alphabet=st.characters(blacklist_characters=["\x00"]), max_size=50),
        st.booleans(),
    ),
    min_size=1,
    max_size=5,
)


def test_audit_append_and_verify(conn: psycopg.Connection) -> None:
    """Appending sequential audit records produces a verifiable cryptographic hash chain."""
    tenant = "ten_audit_test_01"
    seed_wallet_tenant(conn, tenant)

    with tenant_session(conn, tenant):
        e1 = append(conn, tenant, {"action": "proposal_created", "amount": 1000})
        assert e1.seq == 1
        assert e1.prev_hash.startswith("sha256:0000")

        e2 = append(conn, tenant, {"action": "verdict_issued", "outcome": "approve"})
        assert e2.seq == 2
        assert e2.prev_hash == e1.hash

        e3 = append(conn, tenant, {"action": "payment_executed", "ref": "wal_123"})
        assert e3.seq == 3
        assert e3.prev_hash == e2.hash

        res = verify(conn, tenant)
        assert res.ok is True
        assert res.length == 3
        assert res.first_bad_seq is None


def test_audit_detects_tampering(conn: psycopg.Connection) -> None:
    """Editing any audit log row makes verify report that row's seq as bad."""
    tenant = "ten_tamper_test_02"
    seed_wallet_tenant(conn, tenant)

    with tenant_session(conn, tenant):
        append(conn, tenant, {"action": "record_1"})
        append(conn, tenant, {"action": "record_2"})
        append(conn, tenant, {"action": "record_3"})

        res = verify(conn, tenant)
        assert res.ok is True
        assert res.length == 3

    # As superuser, deliberately tamper with row 2 by temporarily disabling append-only trigger
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE public.audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute(
            """
            UPDATE public.audit_log
               SET record = '{"action": "tampered_by_attacker"}'::jsonb
             WHERE tenant_id = %s AND seq = 2
            """,
            (tenant,),
        )
        cur.execute("ALTER TABLE public.audit_log ENABLE TRIGGER audit_log_append_only")

    # Verification must detect the tampering at seq 2
    with tenant_session(conn, tenant):
        tamper_res = verify(conn, tenant)
        assert tamper_res.ok is False
        assert tamper_res.first_bad_seq == 2


@settings(
    max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(records=st.lists(record_strategy, min_size=1, max_size=8))
def test_random_appends_always_verify(conn: psycopg.Connection, records: list[dict]) -> None:
    """Hypothesis property: any random sequence of valid records appended verifies cleanly."""
    tenant = f"ten_rand_{abs(hash(str(records))) % 1000000}"
    seed_wallet_tenant(conn, tenant)

    with tenant_session(conn, tenant):
        for rec in records:
            append(conn, tenant, rec)

        res = verify(conn, tenant)
        assert res.ok is True
        assert res.length == len(records)
        assert res.first_bad_seq is None
