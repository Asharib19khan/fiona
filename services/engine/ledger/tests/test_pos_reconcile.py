"""Tests for POS Reconciliation Engine (D9 / Tier 2)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.app.main import app
from engine.ledger import api, db, pos_reconcile

TENANT = "ten_pos_test"
client = TestClient(app)


def _seed_pos_test_data(conn):
    with db.tenant_session(conn, TENANT):
        conn.execute(
            """
            INSERT INTO public.tenants (id, name, country, currency, framework, fiscal_year_start_month, timezone, cash_buffer_minor, created_at)
            VALUES (%s, 'POS Test Store', 'PK', 'PKR', 'IFRS_SMES', 7, 'Asia/Karachi', 200000000, '2026-10-20T00:00:00Z')
            ON CONFLICT (id) DO NOTHING
            """,
            (TENANT,),
        )
        # Insert POS sales events
        conn.execute(
            """
            INSERT INTO public.events (tenant_id, id, type, occurred_at, recorded_at, business_date, currency, payload, source)
            VALUES
            (%s, 'evt_01HZZZZZZZZZZZZZZZZZZZZZZ1', 'sale', '2026-10-20T10:00:00Z', '2026-10-20T10:00:00Z', '2026-10-20', 'PKR',
             %s, '{"type": "pos_export", "file": "pos.csv", "row": 1, "key": "R001"}'),
            (%s, 'evt_01HZZZZZZZZZZZZZZZZZZZZZZ2', 'sale', '2026-10-20T11:00:00Z', '2026-10-20T11:00:00Z', '2026-10-20', 'PKR',
             %s, '{"type": "pos_export", "file": "pos.csv", "row": 2, "key": "R002"}'),
            (%s, 'evt_01HZZZZZZZZZZZZZZZZZZZZZZ3', 'sale', '2026-10-21T12:00:00Z', '2026-10-21T12:00:00Z', '2026-10-21', 'PKR',
             %s, '{"type": "pos_export", "file": "pos.csv", "row": 3, "key": "R003"}')
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (
                TENANT,
                json.dumps(
                    {
                        "branch": "BR01",
                        "register": "REG01",
                        "txn": "sale",
                        "total_minor": 50_000,
                        "tax_minor": 5_000,
                        "payment": {"method": "cash", "status": "completed"},
                    }
                ),
                TENANT,
                json.dumps(
                    {
                        "branch": "BR01",
                        "register": "REG01",
                        "txn": "sale",
                        "total_minor": 100_000,
                        "tax_minor": 10_000,
                        "payment": {"method": "card", "status": "completed"},
                    }
                ),
                TENANT,
                json.dumps(
                    {
                        "branch": "BR02",
                        "register": "REG02",
                        "txn": "sale",
                        "total_minor": 30_000,
                        "tax_minor": 3_000,
                        "payment": {"method": "cash", "status": "completed"},
                    }
                ),
            ),
        )

        # Insert bank lines
        conn.execute(
            """
            INSERT INTO public.bank_lines (tenant_id, id, account_iban, line_no, posted_on, value_date, narration, reference, amount_minor, balance_minor, currency, event_id)
            VALUES
            (%s, 'bln_01HZZZZZZZZZZZZZZZZZZZZZZ1', 'PK36SCBL0000001123456701', 1, '2026-10-21', '2026-10-21', 'CASH DEPOSIT BR01', 'REF_DEP1', 49_800, 1_000_000, 'PKR', 'evt_01HZZZZZZZZZZZZZZZZZZZZZZ1'),
            (%s, 'bln_01HZZZZZZZZZZZZZZZZZZZZZZ2', 'PK36SCBL0000001123456701', 2, '2026-10-21', '2026-10-21', 'POS CARD SETTL BR01', 'REF_SETTL1', 98_200, 1_098_200, 'PKR', 'evt_01HZZZZZZZZZZZZZZZZZZZZZZ2')
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (TENANT, TENANT),
        )


def test_pos_reconciliation_calculations(conn):
    _seed_pos_test_data(conn)
    result = pos_reconcile.run_pos_reconciliation(
        conn,
        TENANT,
        now=datetime(2026, 10, 22, 9, 0, tzinfo=UTC),
    )

    assert result["api_version"] == "v1"
    assert result["tenant_id"] == TENANT
    assert result["run_id"].startswith("pos_rec_")

    summary = result["summary"]
    assert summary["total_pos_gross_minor"] == 180_000
    assert summary["total_net_sales_minor"] == 180_000
    assert summary["total_cash_sales_minor"] == 80_000
    assert summary["total_cash_deposited_minor"] == 49_800
    assert summary["total_card_sales_minor"] == 100_000
    assert summary["total_card_settled_minor"] == 98_200
    assert summary["total_merchant_fees_minor"] == 1_800

    # Drawers
    drawers = result["drawer_reconciliations"]
    assert len(drawers) == 2
    br01 = next(d for d in drawers if d["branch_id"] == "BR01")
    assert br01["cash_sales_minor"] == 50_000
    assert br01["cash_deposited_minor"] == 49_800
    assert br01["variance_minor"] == -200
    assert br01["status"] == "short"

    br02 = next(d for d in drawers if d["branch_id"] == "BR02")
    assert br02["cash_sales_minor"] == 30_000
    assert br02["cash_deposited_minor"] == 0
    assert br02["status"] == "unbanked"

    # Settlements
    settlements = result["settlement_batches"]
    assert len(settlements) == 1
    card_batch = settlements[0]
    assert card_batch["branch_id"] == "BR01"
    assert card_batch["payment_method"] == "card"
    assert card_batch["gross_pos_minor"] == 100_000
    assert card_batch["settled_amount_minor"] == 98_200
    assert card_batch["fee_minor"] == 1_800
    assert card_batch["fee_rate_bp"] == 180
    assert card_batch["status"] == "matched"

    # Exceptions
    assert len(result["exceptions"]) >= 1
    unbanked = next(e for e in result["exceptions"] if e["category"] == "unbanked_cash")
    assert unbanked["branch_id"] == "BR02"
    assert unbanked["amount_minor"] == 30_000


@pytest.fixture
def test_client(migrated_db: str) -> Iterator[TestClient]:
    def conn_override() -> Iterator:
        with db.connect(migrated_db, autocommit=True) as connection:
            yield connection

    app.dependency_overrides[api.get_conn] = conn_override
    app.dependency_overrides[api.get_clock] = lambda: datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_pos_reconcile_api_endpoint(conn, test_client: TestClient):
    _seed_pos_test_data(conn)
    resp = test_client.post(
        "/v1/reconcile/pos",
        headers={"X-Fiona-Tenant": TENANT, "X-Fiona-Mode": "mock"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["api_version"] == "v1"
    assert data["tenant_id"] == TENANT
    assert data["summary"]["total_merchant_fees_minor"] == 1_800
    assert len(data["drawer_reconciliations"]) == 2
    assert len(data["settlement_batches"]) == 1
