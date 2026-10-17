"""Regression tests for the read-only duplicate-bill adapter."""

import json
from datetime import UTC, datetime

from engine.ledger import bill_checks, db


def test_duplicate_bill_check_uses_imported_bill_documents(conn):
    tenant_id = "ten_bill_check"
    now = datetime(2026, 10, 22, 9, tzinfo=UTC)
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into tenants (id, name, country, currency, framework, fiscal_year_start_month, timezone,"
            " cash_buffer_minor, created_at) values (%s, 'Bill check', 'PK', 'PKR', 'IFRS_SMES', 7,"
            " 'Asia/Karachi', 0, %s)",
            (tenant_id, now),
        )
        for event_id, bill_id, source_key in (
            ("evt_01ARZ3NDEKTSV4RRFFQ69G5FAV", "bill_prior", "prior"),
            ("evt_01ARZ3NDEKTSV4RRFFQ69G5FAW", "bill_current", "current"),
        ):
            conn.execute(
                "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, currency, payload, source)"
                " values (%s, %s, 'purchase_bill', %s, '2026-10-22', %s, 'PKR', %s, %s)",
                (
                    tenant_id,
                    event_id,
                    now,
                    now,
                    json.dumps(
                        {
                            "bill_id": bill_id,
                            "number": "SYN-100",
                            "total_minor": 125_000,
                            "document_sha256": "a" * 64,
                        }
                    ),
                    json.dumps({"type": "bill_extraction", "key": source_key}),
                ),
            )

    result = bill_checks.duplicate_bill_check(conn, tenant_id, "bill_current", now=now)

    assert result is not None
    assert result["rule"] == "G-05"
    assert result["outcome"] == "block"
    assert result["audit"]["matched_bill_id"] == "bill_prior"
