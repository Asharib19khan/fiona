from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from engine.analysis import api as analysis_api
from engine.analysis.ledger_adapter import ledger_windows
from engine.app.main import create_app
from engine.ledger import db

TENANT = "ten_analysis_test"


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    name = f"fiona_analysis_{uuid4().hex[:20]}"
    db.create_database(name)
    try:
        with db.connect(name, autocommit=True) as connection:
            db.apply_migrations(connection)
            _seed(connection)
            yield connection
    finally:
        db.drop_database(name)


def _seed(conn: psycopg.Connection) -> None:
    with db.tenant_session(conn, TENANT):
        conn.execute(
            "insert into tenants (id, name, country, currency, framework, fiscal_year_start_month, timezone, created_at) "
            "values (%s, 'Analysis test', 'PK', 'PKR', 'IFRS_SMES', 7, 'Asia/Karachi', %s)",
            (TENANT, datetime(2024, 1, 1, tzinfo=UTC)),
        )
        with conn.cursor() as cursor:
            cursor.executemany(
                "insert into accounts (tenant_id, code, name, class, neutral_class) values (%s, %s, %s, %s, %s)",
                [
                    (TENANT, "1000", "Bank", "asset", "cash"),
                    (TENANT, "2200", "Loan", "liability", "borrowings"),
                    (TENANT, "3000", "Equity", "equity", "equity"),
                    (TENANT, "4000", "Sales", "income", "revenue"),
                    (TENANT, "5000", "Cost of sales", "expense", "cost_of_sales"),
                    (TENANT, "6000", "Payroll", "expense", "payroll"),
                ],
            )
        entries = [
            (date(2024, 10, 21), [("1000", 1_000_000, 0), ("3000", 0, 1_000_000)]),
            (date(2024, 11, 1), [("1000", 800_000, 0), ("4000", 0, 800_000)]),
            (date(2025, 8, 1), [("6000", 300_000, 0), ("1000", 0, 300_000)]),
            (date(2025, 10, 21), [("1000", 900_000, 0), ("4000", 0, 900_000)]),
            (date(2026, 8, 1), [("6000", 350_000, 0), ("1000", 0, 350_000)]),
            (date(2026, 10, 20), [("1000", 1_100_000, 0), ("4000", 0, 1_100_000)]),
        ]
        for index, (business_date, lines) in enumerate(entries):
            event_id = f"evt_{index:026d}"
            conn.execute(
                "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, currency, payload, source) "
                "values (%s, %s, 'journal_adjustment', %s, %s, %s, 'PKR', '{}'::jsonb, %s::jsonb)",
                (
                    TENANT,
                    event_id,
                    datetime.combine(business_date, datetime.min.time(), tzinfo=UTC),
                    business_date,
                    datetime(2026, 10, 22, tzinfo=UTC),
                    '{"type":"test","key":"' + event_id + '"}',
                ),
            )
            with conn.cursor() as cursor:
                cursor.executemany(
                    "insert into journal_lines (tenant_id, journal_id, line_no, event_id, account_code, debit_minor, credit_minor, currency, business_date, posted_at) "
                    "values (%s, %s, %s, %s, %s, %s, %s, 'PKR', %s, %s)",
                    [
                        (
                            TENANT,
                            f"jnl_{index}",
                            line_no,
                            event_id,
                            account,
                            debit,
                            credit,
                            business_date,
                            datetime(2026, 10, 22, tzinfo=UTC),
                        )
                        for line_no, (account, debit, credit) in enumerate(lines, start=1)
                    ],
                )


def test_adapter_builds_rolling_statement_windows_from_posted_lines(conn: psycopg.Connection):
    latest, prior = ledger_windows(conn, TENANT)

    assert latest.label == "Last 12 months to 2026-10-20"
    assert latest.income.revenue == 2_000_000
    assert latest.income.operating_expenses == 350_000
    assert latest.cash_flows.cfo == 1_650_000
    assert latest.closing.cash == 3_150_000
    assert latest.months_of_data == 12
    assert prior is not None
    assert prior.income.revenue == 800_000
    assert prior.cash_flows.cfo == 500_000


def test_get_analysis_endpoints_use_ledger_data(conn: psycopg.Connection):
    app = create_app(modules=["analysis"])

    def override() -> Iterator[psycopg.Connection]:
        yield conn

    app.dependency_overrides[analysis_api.get_conn] = override
    client = TestClient(app)
    headers = {"X-Fiona-Tenant": TENANT}

    stage = client.get("/v1/stage", headers=headers)
    ratios = client.get("/v1/analysis/ratios", headers=headers)
    health = client.get("/v1/analysis/health", headers=headers)

    assert stage.status_code == ratios.status_code == health.status_code == 200
    assert stage.json()["data_source"] == ratios.json()["data_source"] == "ledger"
    assert any(figure["metric_id"] == "profit.ebitda" for figure in ratios.json()["figures"])
