"""Shared fixtures for wallet and audit log tests (D6).

Provides a throwaway PostgreSQL database per test run, with all migrations applied.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import psycopg
import pytest

from engine.ledger import db

T0 = "2026-10-22T09:00:00Z"


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    name = f"fiona_test_wallet_{os.getpid()}_{time.time_ns() % 10**9}"
    db.create_database(name)
    try:
        with db.connect(name, autocommit=True) as conn:
            db.apply_migrations(conn)
        yield name
    finally:
        db.drop_database(name)


@pytest.fixture
def conn(migrated_db: str) -> Iterator[psycopg.Connection]:
    """Superuser connection for test setup."""
    with db.connect(migrated_db, autocommit=True) as connection:
        yield connection


def seed_wallet_tenant(
    conn: psycopg.Connection,
    tenant_id: str,
    opening_balance_minor: int = 350000000,
) -> None:
    """Seed baseline tenant, mandate, party, and wallet account data."""
    with conn.cursor() as cur:
        # Tenant
        cur.execute(
            """
            INSERT INTO public.tenants (
                id, name, country, currency, framework, fiscal_year_start_month, timezone, cash_buffer_minor, created_at
            ) VALUES (
                %s, %s, 'PK', 'PKR', 'IFRS_SMES', 7, 'Asia/Karachi', 200000000, %s
            ) ON CONFLICT (id) DO NOTHING
            """,
            (tenant_id, f"Synthetic {tenant_id}", T0),
        )

        # Mandate: PKR 150,000 per-payment cap, PKR 450,000 daily cap
        cur.execute(
            """
            INSERT INTO public.mandates (
                tenant_id, id, agent, version, currency, per_payment_cap_minor, daily_cap_minor,
                allowed_action_types, effective_from, created_at
            ) VALUES (
                %s, 'mnd_treasurer_v1', 'treasurer', 1, 'PKR', 15000000, 45000000,
                '{payment}', '2026-08-01', %s
            ) ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tenant_id, T0),
        )

        # Allow-listed supplier: sup_001
        cur.execute(
            """
            INSERT INTO public.parties (
                tenant_id, id, kind, code, name, tax_id, bank_iban, on_allow_list, created_at
            ) VALUES (
                %s, 'sup_001', 'supplier', 'S-001', 'Al-Karam Textiles', '4417023-6', 'PK70SYNA0000000100000001', true, %s
            ) ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tenant_id, T0),
        )

        # Allow-listed supplier with recent bank change: sup_017
        cur.execute(
            """
            INSERT INTO public.parties (
                tenant_id, id, kind, code, name, tax_id, bank_iban, bank_account_changed_at, on_allow_list, created_at
            ) VALUES (
                %s, 'sup_017', 'supplier', 'S-017', 'Mehran Garments', '4417023-6', 'PK70SYNB0000000200000002', '2026-10-20T06:30:00Z', true, %s
            ) ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tenant_id, T0),
        )

        # Non-allow-listed supplier: sup_018
        cur.execute(
            """
            INSERT INTO public.parties (
                tenant_id, id, kind, code, name, on_allow_list, created_at
            ) VALUES (
                %s, 'sup_018', 'supplier', 'S-018', 'New Trims Co', false, %s
            ) ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tenant_id, T0),
        )

        # Simulated wallet account
        cur.execute(
            """
            INSERT INTO public.wallet_accounts (
                tenant_id, id, iban, currency, balance_minor, created_at, updated_at
            ) VALUES (
                %s, 'wal_account_01', 'PK70SYNA0000000100000001', 'PKR', %s, %s, %s
            ) ON CONFLICT (tenant_id, id) DO UPDATE SET balance_minor = %s
            """,
            (
                tenant_id,
                opening_balance_minor,
                T0,
                T0,
                opening_balance_minor,
            ),
        )
