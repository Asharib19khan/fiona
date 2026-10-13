"""D2a done-when: the fixtures are reproducible by seed and internally coherent.

Run from the repo root:  python -m pytest data/generator/tests
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from functools import cache

import pytest
from data.generator import core, load_mandates, load_persona
from data.generator.build import generate
from data.generator.write import render_files

SEED, PERSONA, MONTHS = 42, "karachi_apparel", 2
ULID = re.compile(r"^(evt|bln)_[0-9A-HJKMNP-TV-Z]{26}$")


@cache
def files() -> dict[str, bytes]:
    persona = load_persona(PERSONA)
    mandates, source = load_mandates(persona["tenant"]["id"])
    return render_files(generate(persona, SEED, MONTHS, mandates), source)


def rows(name: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(files()[name].decode("utf-8"))))


def obj(name: str) -> dict:
    return json.loads(files()[name])


def events() -> list[dict]:
    return [json.loads(line) for line in files()["events.jsonl"].decode("utf-8").splitlines()]


def test_same_seed_gives_byte_identical_files() -> None:
    persona = load_persona(PERSONA)
    mandates, source = load_mandates(persona["tenant"]["id"])
    again = render_files(generate(persona, SEED, MONTHS, mandates), source)
    first = {k: hashlib.sha256(v).hexdigest() for k, v in files().items()}
    second = {k: hashlib.sha256(v).hexdigest() for k, v in again.items()}
    assert first == second


def test_a_different_seed_gives_different_data() -> None:
    persona = load_persona(PERSONA)
    mandates, source = load_mandates(persona["tenant"]["id"])
    other = render_files(generate(persona, SEED + 1, MONTHS, mandates), source)
    assert other["pos_sales.csv"] != files()["pos_sales.csv"]


def test_files_are_utf8_lf_and_marked_synthetic() -> None:
    for name, content in files().items():
        assert b"\r\n" not in content, name
        assert content.endswith(b"\n"), name
        content.decode("utf-8")
        if name.endswith(".json"):
            assert json.loads(content)["synthetic"] is True, name
        if name.startswith("documents/"):
            assert content.startswith(b"SYNTHETIC DOCUMENT"), name


def test_bank_statement_balances_chain() -> None:
    lines = rows("bank_statement.csv")
    opening = obj("tenant.json")["bank_accounts"][0]["opening_balance_minor"]
    balance = opening
    for i, line in enumerate(lines, start=1):
        assert int(line["line_no"]) == i
        balance += int(line["amount_minor"])
        assert int(line["balance_minor"]) == balance
        assert balance >= 0


def test_every_matched_bank_line_equals_its_events() -> None:
    by_id = {e["id"]: e for e in events()}
    bank = {int(r["line_no"]): int(r["amount_minor"]) for r in rows("bank_statement.csv")}
    key = obj("answer_key.json")
    for match in key["matches"]:
        evs = [by_id[i] for i in match["event_ids"]]
        if match["kind"] == "supplier_payment":
            total = -sum(e["amount_minor"] for e in evs)
        elif match["kind"] == "cash_deposit":
            total = sum(e["total_minor"] for e in evs) + match["over_short_minor"]
        else:  # pos_settlement, customer_receipt
            total = sum(e["total_minor"] for e in evs)
        assert bank[match["line_no"]] == total, match
    matched = {m["line_no"] for m in key["matches"]} | {
        u["line_no"] for u in key["unmatched_bank_lines"]
    }
    assert matched == set(bank), "every bank line is either matched or explained"


def test_every_settled_sale_is_banked_once() -> None:
    key = obj("answer_key.json")
    banked = Counter(i for m in key["matches"] for i in m["event_ids"])
    assert max(banked.values()) == 1
    as_of = obj("tenant.json")["as_of"]
    late = [
        e for e in events() if e["event"] == "sale" and e["txn"] != "void" and e["id"] not in banked
    ]
    # Only the last few days' sales can still be waiting for settlement or deposit.
    assert all(e["date"] >= "2026-10-19" for e in late), sorted({e["date"] for e in late})
    assert as_of == "2026-10-22"


def test_bills_add_up_and_documents_hash() -> None:
    for bill in obj("bills.json")["bills"]:
        assert sum(ln["line_total_minor"] for ln in bill["lines"]) == bill["subtotal_minor"]
        for ln in bill["lines"]:
            assert ln["qty"] * ln["unit_price_minor"] == ln["line_total_minor"]
        tax = sum(t["amount_minor"] for t in bill["tax"])
        assert bill["subtotal_minor"] + tax == bill["total_minor"]
        assert tax == core.tax_on(bill["subtotal_minor"], 1800)
        doc = files()[f"documents/{bill['document_id']}.txt"]
        assert hashlib.sha256(doc).hexdigest() == bill["document_sha256"]


def test_three_way_match_data_is_complete_for_clean_bills() -> None:
    pos = {p["number"]: p for p in obj("purchase_orders.json")["purchase_orders"]}
    grns = {g["po_id"]: g for g in obj("goods_received.json")["goods_received"]}
    for bill in obj("bills.json")["bills"]:
        po = pos[bill["po_number"]]
        assert po["supplier_id"] == bill["supplier_id"]
        assert po["po_id"] in grns


def test_pos_rows_and_z_reports_agree() -> None:
    cash: Counter = Counter()
    for r in rows("pos_sales.csv"):
        assert int(r["qty"]) * int(r["unit_price_minor"]) - int(r["discount_minor"]) == int(
            r["line_total_minor"]
        )
        assert r["sku"] and "cost" not in r
        if r["payment_method"] == "cash" and r["txn_type"] != "void":
            cash[(r["business_date"], r["register_id"])] += int(r["line_total_minor"])
    for z in rows("pos_z_reports.csv"):
        key = (z["business_date"], z["register_id"])
        assert int(z["cash_sales_minor"]) + int(z["cash_refunds_minor"]) == cash[key]
        assert int(z["counted_cash_minor"]) - int(z["expected_cash_minor"]) == int(
            z["over_short_minor"]
        )


def test_events_have_valid_unique_ids_and_known_parties() -> None:
    evs = events()
    ids = [e["id"] for e in evs]
    assert len(ids) == len(set(ids))
    assert all(ULID.match(i) for i in ids)
    assert [(e["occurred_at"], e["id"]) for e in evs] == sorted(
        (e["occurred_at"], e["id"]) for e in evs
    )
    parties = {r["party_id"] for r in rows("parties.csv")}
    assert all(e.get("party") in parties for e in evs if e.get("party"))


def test_ids_match_the_engine_rule() -> None:
    engine_ids = pytest.importorskip("engine.ledger.ids")
    moment = core.local_time(
        core.days(core.add_months(core.date(2026, 10, 22), -1), core.date(2026, 10, 22))[0],
        600,
        5,
        5,
    )
    for args in (("evt", "pos_export", "R1-000001"), ("bln", "bank_statement", "PK00SYNA#7")):
        prefix, source_type, key = args
        assert core.source_ulid(
            prefix, moment, "ten_x", source_type, key
        ) == engine_ids.source_ulid(prefix, moment, "ten_x", source_type, key)


def test_ibans_are_well_formed_and_synthetic() -> None:
    ibans = [r["bank_iban"] for r in rows("parties.csv") if r["bank_iban"]]
    ibans.append(obj("tenant.json")["bank_accounts"][0]["iban"])
    for value in ibans:
        assert len(value) == 24 and core.iban_is_valid(value), value
        assert value[4:7] == "SYN", value


def test_demo_threads_are_planted() -> None:
    bills = {b["bill_id"]: b for b in obj("bills.json")["bills"]}
    resend, original = bills["bill_2231"], bills["bill_2188"]
    assert (resend["number"], resend["document_id"], resend["supplier_id"]) == (
        "INV-2231",
        "doc_88",
        "sup_017",
    )
    assert resend["total_minor"] == original["total_minor"] == 18_450_000
    assert original["number"] == "INV 2231" and resend["po_number"] == original["po_number"]
    party = next(r for r in rows("parties.csv") if r["party_id"] == "sup_017")
    assert party["bank_account_changed_at"] == "2026-10-20T06:30:00Z"
    assert resend["supplier"]["bank_iban"] != original["supplier"]["bank_iban"]
    change = next(e for e in events() if e["event"] == "bank_detail_change")
    assert change["confirmed_via"] == "email" and change["new_iban"] == party["bank_iban"]
    paid = [
        e
        for e in events()
        if e["event"] == "supplier_payment" and e["bill_id"] in ("bill_2188", "bill_2231")
    ]
    assert [p["bill_id"] for p in paid] == ["bill_2188"]
    cap = next(m for m in obj("mandates.json")["mandates"] if m["agent"] == "treasurer")[
        "per_payment_cap_minor"
    ]
    assert bills["bill_2240"]["total_minor"] > cap
    scenarios = {s["id"]: s for s in obj("answer_key.json")["scenarios"]}
    assert scenarios["DEMO-1"]["expected_outcome"] == "block"
    assert scenarios["S-01"]["expected_outcome"] == "escalate"
    assert "bill_2231" not in obj("answer_key.json")["clean_bill_ids"]


def test_stock_never_goes_negative() -> None:
    stock = {r["sku"]: int(r["opening_stock_qty"]) for r in rows("items.csv")}
    for e in events():
        if e["event"] == "stock_movement":
            stock[e["item"]] += e["qty"]
        elif e["event"] == "sale" and e["txn"] != "void":
            for ln in e["lines"]:
                stock[ln["item"]] -= ln["qty"]
        elif e["event"] == "customer_invoice":
            for ln in e["lines"]:
                stock[ln["sku"]] -= ln["qty"]
        assert min(stock.values()) >= 0, e["id"]
