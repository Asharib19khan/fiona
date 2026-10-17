"""Regression tests for deterministic reconciliation passes."""

import json
from datetime import UTC, date, datetime

from engine.ledger import db
from engine.ledger.reconcile import RUN_ID, _candidate_matches, findings, run


def _bank(id: str, narration: str, amount: int, *, day: int = 5, reference: str = ""):
    return {
        "id": id,
        "posted_on": date(2026, 10, day),
        "narration": narration,
        "reference": reference,
        "amount_minor": amount,
    }


def _event(id: str, kind: str, payload: dict, *, day: int = 4):
    return {
        "id": id,
        "type": kind,
        "business_date": date(2026, 10, day),
        "party_id": payload.get("party"),
        "payload": payload,
    }


def test_exact_supplier_payment_needs_reference_amount_and_date():
    events = [
        _event("evt_paid", "supplier_payment", {"amount_minor": 125_000, "payment_id": "pay_abc"}),
        _event(
            "evt_other", "supplier_payment", {"amount_minor": 125_000, "payment_id": "pay_else"}
        ),
    ]
    result = _candidate_matches(
        [_bank("bln_out", "IBFT TO SYNTHETIC SUPPLIER", -125_000, reference="FTabc")], events
    )

    assert [(match.pass_name, match.event_ids) for match in result] == [("exact", ("evt_paid",))]


def test_invoice_batch_requires_exact_total_for_one_to_many_match():
    events = [
        _event("evt_inv_a", "customer_invoice", {"total_minor": 70_000, "party": "cus_1"}),
        _event("evt_inv_b", "customer_invoice", {"total_minor": 30_000, "party": "cus_1"}),
    ]
    result = _candidate_matches([_bank("bln_in", "IBFT FROM CUSTOMER", 100_000)], events)

    assert [(match.pass_name, match.event_ids) for match in result] == [
        ("rule", ("evt_inv_a", "evt_inv_b"))
    ]


def test_pos_batch_only_matches_the_complete_method_and_branch_total():
    events = [
        _event(
            "evt_card",
            "sale",
            {"total_minor": 40_000, "branch": "BR01", "payment": {"method": "card"}},
        ),
        _event(
            "evt_cash",
            "sale",
            {"total_minor": 60_000, "branch": "BR01", "payment": {"method": "cash"}},
        ),
    ]
    result = _candidate_matches(
        [_bank("bln_settle", "POS CARD SETTL MID 448120 BATCH 1005", 40_000)], events
    )

    assert [(match.pass_name, match.event_ids) for match in result] == [
        ("one_to_many", ("evt_card",))
    ]


def test_run_persists_an_exact_match_as_a_proposal(conn):
    """The reconciliation run must store reviewable match rows, not only calculate them."""
    tenant_id = "ten_reconcile_test"
    now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into tenants (id, name, country, currency, framework, fiscal_year_start_month, timezone,"
            " cash_buffer_minor, created_at) values (%s, 'Reconcile test', 'PK', 'PKR', 'IFRS_SMES', 7,"
            " 'Asia/Karachi', 0, %s)",
            (tenant_id, now),
        )
        conn.execute(
            "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, currency, payload, source)"
            " values (%s, %s, 'supplier_payment', %s, '2026-10-20', %s, 'PKR', %s, %s)",
            (
                tenant_id,
                "evt_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                now,
                now,
                json.dumps({"amount_minor": 125_000, "payment_id": "pay_abc"}),
                json.dumps({"type": "manual", "key": "payment-abc"}),
            ),
        )
        conn.execute(
            "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, currency, payload, source)"
            " values (%s, %s, 'bank_line', %s, '2026-10-21', %s, 'PKR', %s, %s)",
            (
                tenant_id,
                "evt_01ARZ3NDEKTSV4RRFFQ69G5FAW",
                now,
                now,
                json.dumps({"amount_minor": -125_000}),
                json.dumps({"type": "bank_statement", "key": "line-1"}),
            ),
        )
        conn.execute(
            "insert into bank_lines (tenant_id, id, account_iban, line_no, posted_on, narration, reference,"
            " amount_minor, balance_minor, currency, event_id)"
            " values (%s, %s, 'PK00SYNTHETIC00000000001', 1, '2026-10-21', 'IBFT TO SYNTHETIC SUPPLIER',"
            " 'FTabc', -125000, 0, 'PKR', %s)",
            (tenant_id, "bln_01ARZ3NDEKTSV4RRFFQ69G5FAV", "evt_01ARZ3NDEKTSV4RRFFQ69G5FAW"),
        )

    result = run(conn, tenant_id, now=now)

    assert result == {
        "run_id": RUN_ID,
        "matched_bank_lines": 1,
        "exact": 1,
        "rule": 0,
        "one_to_many": 0,
        "fuzzy": 0,
        "unmatched_bank_lines": 0,
    }
    with db.tenant_session(conn, tenant_id):
        row = conn.execute(
            "select event_id, bank_line_id, pass, confidence, status from matches"
        ).fetchone()
    assert row == (
        "evt_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "bln_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "exact",
        1,
        "proposed",
    )
    with db.tenant_session(conn, tenant_id):
        conn.execute("update matches set status = 'confirmed'")

    run(conn, tenant_id, now=now)

    with db.tenant_session(conn, tenant_id):
        status = conn.execute("select status from matches").fetchone()[0]
    assert status == "confirmed"


def test_findings_publish_only_unmatched_bank_lines(conn):
    tenant_id = "ten_reconcile_findings"
    now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into tenants (id, name, country, currency, framework, fiscal_year_start_month, timezone,"
            " cash_buffer_minor, created_at) values (%s, 'Reconcile findings', 'PK', 'PKR', 'IFRS_SMES', 7,"
            " 'Asia/Karachi', 0, %s)",
            (tenant_id, now),
        )
        conn.execute(
            "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, currency, payload, source)"
            " values (%s, %s, 'bank_line', %s, '2026-10-21', %s, 'PKR', %s, %s)",
            (
                tenant_id,
                "evt_01ARZ3NDEKTSV4RRFFQ69G5FAX",
                now,
                now,
                json.dumps({"amount_minor": -80_000}),
                json.dumps({"type": "bank_statement", "key": "unmatched-line"}),
            ),
        )
        conn.execute(
            "insert into bank_lines (tenant_id, id, account_iban, line_no, posted_on, narration,"
            " amount_minor, balance_minor, currency, event_id)"
            " values (%s, %s, 'PK00SYNTHETIC00000000002', 1, '2026-10-21', 'UNRECOGNISED CHARGE',"
            " -80000, 0, 'PKR', %s)",
            (tenant_id, "bln_01ARZ3NDEKTSV4RRFFQ69G5FAW", "evt_01ARZ3NDEKTSV4RRFFQ69G5FAX"),
        )

    result = findings(conn, tenant_id, now=now)

    assert len(result) == 1
    assert result[0].type == "unmatched_bank_line"
    assert result[0].money_at_stake.minor == 80_000


def test_fuzzy_matching_pass_4_with_deterministic_amount_verification():
    """Pass 4 matches using fuzzy description/party/ref while enforcing exact integer settlement."""
    events = [
        _event(
            "evt_inv_fuz",
            "customer_invoice",
            {"total_minor": 95_500, "number": "INV-2026-9918", "party": "Acme Garments Ltd"},
            day=5,
        ),
        _event(
            "evt_inv_diff_amount",
            "customer_invoice",
            {"total_minor": 95_501, "number": "INV-2026-9919", "party": "Acme Garments Ltd"},
            day=5,
        ),
    ]

    # 1. Matching amount + fuzzy narration ("TRANSFER ACME GARMENTS 9918") matches on Pass 4
    bank_line = _bank("bln_fuz", "ONLINE TFR ACME GARMENTS 9918", 95_500, day=6)
    matches = _candidate_matches([bank_line], events)
    assert len(matches) == 1
    assert matches[0].pass_name == "fuzzy"
    assert matches[0].event_ids == ("evt_inv_fuz",)
    assert matches[0].confidence >= 0.65

    # 2. Mismatched amount (95_501 != 95_500) rejects even if narration is identical
    bad_bank_line = _bank("bln_bad_amt", "ONLINE TFR ACME GARMENTS 9919", 95_500, day=6)
    unmatched = _candidate_matches([bad_bank_line], events[1:])
    assert len(unmatched) == 0
