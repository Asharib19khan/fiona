"""Shared fixtures for ledger tests.

Each test run gets its own throwaway database, created and dropped here, so the four lanes
never touch each other's data or the shared fiona_dev database.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import psycopg
import pytest

from engine.ledger import db


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    name = f"fiona_test_ledger_{os.getpid()}_{time.time_ns() % 10**9}"
    db.create_database(name)
    try:
        with db.connect(name, autocommit=True) as conn:
            db.apply_migrations(conn)
        yield name
    finally:
        db.drop_database(name)


@pytest.fixture
def conn(migrated_db: str) -> Iterator[psycopg.Connection]:
    """Superuser connection to the throwaway database (bypasses RLS: use for setup only)."""
    with db.connect(migrated_db, autocommit=True) as connection:
        yield connection
