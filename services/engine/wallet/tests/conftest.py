"""Shared fixtures for the wallet and audit tests (D6): a throwaway database per run, plus helpers
that store proposals, verdicts and decisions the way the engine does."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
import yaml

from engine.ledger import db
from engine.wallet.wallet import open_account
from fiona_contracts.hashing import verdict_hash

T0 = "2026-10-22T09:00:00Z"
NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)  # 14:00 in Karachi, business date 2026-10-22
TODAY = "2026-10-22"
REPO_ROOT = Path(__file__).resolve().parents[4]
_MANDATES = yaml.safe_load((REPO_ROOT / "rulebook" / "mandates.yaml").read_text(encoding="utf-8"))
TREASURER = next(
    m
    for m in _MANDATES["persona_mandates"]["ten_karachi_apparel"]["mandates"]
    if m["agent"] == "treasurer"
)
CAP = TREASURER["per_payment_cap_minor"]
DAILY_CAP = TREASURER["daily_cap_minor"]
OPENING_BALANCE = 350_000_000


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
    with db.connect(migrated_db, autocommit=True) as connection:
        yield connection


def seed_wallet_tenant(
    conn: psycopg.Connection, tenant_id: str, opening_balance_minor: int = OPENING_BALANCE
) -> None:
    """Tenant, the rulebook treasurer mandate, four suppliers and a funded simulated account."""
    with db.tenant_session(conn, tenant_id):
        x = conn.execute
        x(
            "insert into tenants (id, name, country, currency, framework, fiscal_year_start_month, timezone,"
            " cash_buffer_minor, created_at) values (%s, %s, 'PK', 'PKR', 'IFRS_SMES', 7, 'Asia/Karachi', 200000000, %s)",
            (tenant_id, f"Synthetic {tenant_id}", T0),
        )
        x(
            "insert into mandates (tenant_id, id, agent, version, currency, per_payment_cap_minor, daily_cap_minor,"
            " allowed_action_types, effective_from, created_at) values (%s, %s, 'treasurer', 1, 'PKR', %s, %s, %s, %s, %s)",
            (
                tenant_id,
                TREASURER["id"],
                CAP,
                DAILY_CAP,
                TREASURER["allowed_action_types"],
                TREASURER["effective_from"],
                T0,
            ),
        )
        parties = [
            ("sup_001", "PK00SYNB0000000000000001", True, None),
            ("sup_018", "PK00SYNB0000000000000018", False, None),
            ("sup_017", "PK00SYNC0000000000000017", True, "2026-10-20T06:30:00Z"),
            ("sup_003", "PK00SYNH0000000000000003", True, "2026-09-12T07:00:00Z"),
        ]
        for party_id, iban, allowed, changed in parties:
            x(
                "insert into parties (tenant_id, id, kind, name, bank_iban, bank_account_changed_at, on_allow_list,"
                " created_at) values (%s, %s, 'supplier', %s, %s, %s, %s, %s)",
                (tenant_id, party_id, f"Supplier {party_id}", iban, changed, allowed, T0),
            )
        for party_id, at, via, by in (
            ("sup_017", "2026-10-20T06:30:00Z", "email", "supplier email"),
            ("sup_003", "2026-09-12T07:00:00Z", "phone", "usr_owner"),
        ):
            key = f"bdc:{party_id}"
            x(
                "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, party_id, currency,"
                " payload, source) values (%s, %s, 'bank_detail_change', %s, %s, %s, %s, 'PKR', %s, %s)",
                (
                    tenant_id,
                    f"evt_{'0' * 20}{party_id[-3:]}BDC",
                    at,
                    at[:10],
                    at,
                    party_id,
                    json.dumps({"party": party_id, "confirmed_via": via, "confirmed_by": by}),
                    json.dumps({"type": "manual", "key": key}),
                ),
            )
    open_account(
        conn,
        tenant_id,
        iban="PK00SYNW0000000000000001",
        currency="PKR",
        opening_balance_minor=opening_balance_minor,
        now=NOW,
    )


def store_proposal(
    conn: psycopg.Connection,
    tenant_id: str,
    proposal_id: str,
    *,
    amount: int,
    payee: str = "sup_001",
    pay_on: str = TODAY,
    agent: str = "treasurer",
    created_by: str = "treasurer",
) -> None:
    kind = "user" if created_by.startswith("usr_") else "agent"
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into proposals (tenant_id, id, agent, type, created_at, summary, amount_minor, currency, payload,"
            " evidence, reasoning, created_by) values (%s, %s, %s, 'payment', %s, 'Pay a bill', %s, 'PKR', %s, %s,"
            " 'test', %s)",
            (
                tenant_id,
                proposal_id,
                agent,
                T0,
                amount,
                json.dumps(
                    {"payee_id": payee, "bill_id": "bill_x", "pay_on": pay_on, "channel": "wallet"}
                ),
                json.dumps([{"kind": "ledger_row", "ref": "bill_x"}]),
                json.dumps({"kind": kind, "id": created_by}),
            ),
        )


def store_verdict(
    conn: psycopg.Connection,
    tenant_id: str,
    proposal_id: str,
    outcome: str,
    *,
    verdict_id: str | None = None,
    conditions: list | None = None,
    previous: str | None = None,
) -> str:
    verdict_id = verdict_id or f"vrd_{proposal_id[5:]}"
    body = {
        "id": verdict_id,
        "proposal_id": proposal_id,
        "outcome": outcome,
        "checks": [
            {
                "name": "policy",
                "rule": "G-01",
                "result": "pass" if outcome == "approve" else "fail",
                "outcome": outcome if outcome != "approve_with_conditions" else "approve",
                "detail": "test",
            }
        ],
        "conditions": conditions or [],
        "decided_at": T0,
        "policy_version": "1.0.0",
        "previous_verdict_id": previous,
    }
    digest = verdict_hash(body)
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into verdicts (tenant_id, id, proposal_id, outcome, checks, conditions, decided_at, verdict_hash,"
            " policy_version, previous_verdict_id, body) values (%s, %s, %s, %s, %s, %s, %s, %s, '1.0.0', %s, %s)",
            (
                tenant_id,
                verdict_id,
                proposal_id,
                outcome,
                json.dumps(body["checks"]),
                json.dumps(body["conditions"]),
                T0,
                digest,
                previous,
                json.dumps(body),
            ),
        )
    return verdict_id


def store_decision(
    conn: psycopg.Connection,
    tenant_id: str,
    proposal_id: str,
    verdict_id: str,
    *,
    decided_by: str = "usr_owner",
    decision: str = "approve",
    decided_at: str = T0,
) -> None:
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into decisions (tenant_id, id, proposal_id, verdict_id, decision, decided_by, decided_at)"
            " values (%s, %s, %s, %s, %s, %s, %s)",
            (
                tenant_id,
                f"dec_{proposal_id[5:]}_{decided_by[4:]}",
                proposal_id,
                verdict_id,
                decision,
                decided_by,
                decided_at,
            ),
        )
