"""A throwaway migrated database per test session (same pattern as the ledger tests)."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest

from engine.ledger import db


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    name = f"fiona_test_settings_{os.getpid()}_{time.time_ns() % 10**9}"
    db.create_database(name)
    try:
        with db.connect(name, autocommit=True) as conn:
            db.apply_migrations(conn)
        yield name
    finally:
        db.drop_database(name)
