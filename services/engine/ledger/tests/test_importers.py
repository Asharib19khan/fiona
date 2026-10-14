"""D3 done-when: one command loads the full dataset into a fresh database; importers are idempotent,
report bad rows, and reproduce the generator's events; the posted ledger balances and ties to the bank."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from engine.ledger import db, demo, importers, seed

FIXTURES = seed.DEFAULT_FIXTURES / "ten_karachi_apparel"
TENANT = "ten_karachi_apparel"
IMPORTED = ("bank_statement", "pos_export", "bill_extraction")


@pytest.fixture(scope="module")
def loaded(migrated_db: str) -> Iterator[dict]:
    with db.connect(migrated_db, autocommit=True) as conn:
        yield demo.load_tenant(conn, FIXTURES)


def _generator_events() -> list[dict]:
    return importers.events_from_jsonl((FIXTURES / "events.jsonl").read_text(encoding="utf-8"))


def test_full_dataset_loads_with_no_row_errors(loaded: dict) -> None:
    for step in ("bank", "pos", "bills", "other_events"):
        assert loaded[step]["errors"] == [], step
    total = sum(loaded[s]["inserted"] for s in ("bank", "pos", "bills", "other_events"))
    assert total == len(_generator_events())
    assert loaded["journal_lines"] > 0


def test_imported_events_equal_the_generators(loaded: dict, conn: psycopg.Connection) -> None:
    expected = {e["id"]: e for e in _generator_events()}
    with db.tenant_session(conn, TENANT):
        rows = conn.execute(
            "select id, type, business_date, currency, payload, source from events where source_type = any(%s)",
            (list(IMPORTED),),
        ).fetchall()
    assert len(rows) == sum(1 for e in expected.values() if e["source"]["type"] in IMPORTED)
    for event_id, kind, business_date, currency, payload, source in rows:
        want = expected[event_id]
        assert (kind, business_date.isoformat(), currency, source) == (
            want["event"],
            want["date"],
            want["currency"],
            want["source"],
        )
        if (
            kind == "sale"
        ):  # the POS export has no cost; the importer joins the item cost (FORMATS 3.11)
            payload["lines"] = [
                {k: v for k, v in ln.items() if k != "cost_minor"} for ln in payload["lines"]
            ]
            want = {
                **want,
                "lines": [
                    {k: v for k, v in ln.items() if k != "cost_minor"} for ln in want["lines"]
                ],
            }
        for field, value in payload.items():
            assert want[field] == value, (event_id, field)


def test_reimporting_adds_nothing(loaded: dict, conn: psycopg.Connection) -> None:
    again = demo.load_tenant(conn, FIXTURES)
    for step in ("bank", "pos", "bills", "other_events"):
        assert again[step]["inserted"] == 0 and again[step]["skipped"] > 0, step
    assert again["journal_lines"] == 0


def test_ledger_balances_and_ties_to_the_bank(loaded: dict, conn: psycopg.Connection) -> None:
    with db.tenant_session(conn, TENANT):
        debits, credits = conn.execute(
            "select sum(debit_minor), sum(credit_minor) from journal_lines"
        ).fetchone()
        cash = conn.execute(
            "select coalesce(sum(debit_minor - credit_minor), 0) from journal_lines"
            " where account_code = '1000'"
        ).fetchone()[0]
        closing = conn.execute(
            "select balance_minor from bank_lines order by line_no desc limit 1"
        ).fetchone()[0]
        suspense = conn.execute(
            "select count(*) from journal_lines where account_code = '1990'"
        ).fetchone()[0]
        unbalanced = conn.execute(
            "select count(*) from (select journal_id from journal_lines group by journal_id"
            " having sum(debit_minor) <> sum(credit_minor)) j"
        ).fetchone()[0]
    assert debits == credits and unbalanced == 0
    assert cash == closing  # every bank movement is posted exactly once
    assert suspense == 0  # every bank line is explained by a book event or a narration rule


def test_bad_rows_are_reported_by_row(loaded: dict, conn: psycopg.Connection) -> None:
    now = demo.DEMO_CLOCK
    bank = (
        "account_iban,line_no,posted_on,value_date,narration,reference,amount_minor,balance_minor,currency\n"
        "PK00SYNZTEST,1,2026-10-01,2026-10-01,TEST CREDIT,,1000,1000,PKR\n"
        "PK00SYNZTEST,2,2026-10-01,2026-10-01,TEST BROKEN,,500,9999,PKR\n"
        "PK00SYNZTEST,3,2026-10-01,2026-10-01,TEST CURRENCY,,1,1,USD\n"
    )
    result = importers.import_bank_csv(conn, TENANT, bank, now=now)
    assert [e["row"] for e in result.errors] == [2, 3] and result.inserted == 1
    header = (
        "receipt_no,line_no,txn_type,original_receipt_no,occurred_at,business_date,branch_id,register_id,"
        "cashier_id,customer_code,sku,qty,unit_price_minor,discount_minor,line_total_minor,tax_minor,"
        "payment_method,payment_status,currency\n"
    )
    pos = (
        header
        + "T9-000001,1,sale,,2026-10-01T06:00:00Z,2026-10-01,BR01,R1,CSH-01,,NOPE,1,100,0,100,15,cash,settled,PKR\n"
        + "T9-000002,1,sale,,2026-10-01T06:00:00Z,2026-10-01,BR01,R1,CSH-01,,KRT-M-BLU,2,100,0,999,15,cash,"
        "settled,PKR\n"
    )
    result = importers.import_pos_csv(conn, TENANT, pos, now=now)
    assert [e["row"] for e in result.errors] == [1, 2] and result.inserted == 0
    assert "unknown SKU" in result.errors[0]["reason"]
    bill = json.loads((FIXTURES / "bills.json").read_text(encoding="utf-8"))["bills"][0]
    result = importers.import_bills(
        conn,
        TENANT,
        [{**bill, "bill_id": "bill_9998"}],
        {bill["document_path"]: b"edited bytes"},
        storage_prefix="x",
        now=now,
    )
    assert result.errors and "sha256" in result.errors[0]["reason"]


def test_demo_data_is_one_command() -> None:
    assert '"demo-data"' in Path(db.__file__).read_text(encoding="utf-8")
