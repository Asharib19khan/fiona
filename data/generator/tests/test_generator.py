"""D2 done-when: the same seed rebuilds identical data, the data is coherent, every B3 scenario is
planted with real rows, and the calibration truths hold (cash dip, FY cash flows, bill sizes).

Run from the repo root:  python -m pytest data/generator/tests
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date
from functools import cache

import pytest
from data.generator import core, load_mandates, load_persona, load_scenarios
from data.generator.build import generate
from data.generator.write import render_files, render_holdout

SEED, PERSONA, MONTHS = 42, "karachi_apparel", 24
ULID = re.compile(r"^(evt|bln)_[0-9A-HJKMNP-TV-Z]{26}$")


def _generate() -> dict:
    persona = load_persona(PERSONA)
    mandates, source = load_mandates(persona["tenant"]["id"])
    return generate(persona, SEED, MONTHS, mandates, load_scenarios(), source)


@cache
def output() -> dict:
    return _generate()


@cache
def files() -> dict[str, bytes]:
    return render_files(output())


def rows(name: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(files()[name].decode("utf-8"))))


def obj(name: str) -> dict:
    return json.loads(files()[name])


@cache
def events() -> list[dict]:
    return [json.loads(line) for line in files()["events.jsonl"].decode("utf-8").splitlines()]


def key() -> dict:
    return obj("answer_key.json")


def bills() -> dict[str, dict]:
    return {b["bill_id"]: b for b in obj("bills.json")["bills"]}


# ---------------------------------------------------------------- reproducibility and format
def test_same_seed_gives_byte_identical_files() -> None:
    again = _generate()
    first = {k: hashlib.sha256(v).hexdigest() for k, v in files().items()}
    second = {k: hashlib.sha256(v).hexdigest() for k, v in render_files(again).items()}
    assert first == second
    assert render_holdout(output()) == render_holdout(again)


def test_files_are_utf8_lf_and_marked_synthetic() -> None:
    for name, content in files().items():
        if name.endswith(".pdf"):
            assert content.startswith(b"%PDF-1.4\n% SYNTHETIC DOCUMENT"), name
            continue
        assert b"\r\n" not in content and content.endswith(b"\n"), name
        content.decode("utf-8")
        if name.endswith(".json"):
            assert json.loads(content)["synthetic"] is True, name
        if name.startswith("documents/"):
            assert content.startswith(b"SYNTHETIC DOCUMENT"), name


def test_history_covers_whole_fiscal_years() -> None:
    period = obj("tenant.json")["period"]
    assert period["start"] == "2024-07-01" and period["end"] == "2026-10-22"
    assert all(e["date"] <= period["end"] for e in events())


# ---------------------------------------------------------------- coherence
def test_bank_statement_balances_chain_and_never_go_negative() -> None:
    balance = obj("tenant.json")["bank_accounts"][0]["opening_balance_minor"]
    for i, line in enumerate(rows("bank_statement.csv"), start=1):
        assert int(line["line_no"]) == i
        balance += int(line["amount_minor"])
        assert int(line["balance_minor"]) == balance >= 0


def test_every_bank_line_is_matched_or_explained() -> None:
    by_id = {e["id"]: e for e in events()}
    bank = {int(r["line_no"]): int(r["amount_minor"]) for r in rows("bank_statement.csv")}
    for match in key()["matches"]:
        evs = [by_id[i] for i in match["event_ids"]]
        if match["kind"] == "supplier_payment":
            total = -sum(e["amount_minor"] for e in evs)
        elif match["kind"] == "cash_deposit":
            total = sum(e["total_minor"] for e in evs) + match["over_short_minor"]
        else:
            total = sum(e["total_minor"] for e in evs)
        assert bank[match["line_no"]] == total, match
    explained = {m["line_no"] for m in key()["matches"]} | {
        u["line_no"] for u in key()["unmatched_bank_lines"]
    }
    assert explained == set(bank)
    assert Counter(i for m in key()["matches"] for i in m["event_ids"]).most_common(1)[0][1] == 1


def test_bills_add_up_and_documents_hash() -> None:
    stated_wrong = {"bill_2250"}  # S-07 plants a wrong tax line on purpose
    for bill in bills().values():
        assert sum(ln["line_total_minor"] for ln in bill["lines"]) == bill["subtotal_minor"]
        tax = sum(t["amount_minor"] for t in bill["tax"])
        assert bill["subtotal_minor"] + tax == bill["total_minor"]
        if bill["bill_id"] not in stated_wrong and bill["tax"]:
            assert tax == core.tax_on(bill["subtotal_minor"], 1800), bill["bill_id"]
        assert hashlib.sha256(files()[bill["document_path"]]).hexdigest() == bill["document_sha256"]


def test_bill_documents_include_about_twenty_pdfs() -> None:
    pdfs = [b for b in bills().values() if b["document_path"].endswith(".pdf")]
    assert 15 <= len(pdfs) <= 30


def test_purchase_costs_rise_over_time() -> None:
    costs: dict[int, list[int]] = {}
    for po in obj("purchase_orders.json")["purchase_orders"]:
        for line in po["lines"]:
            if line["sku"] == "KRT-M-BLK":
                costs.setdefault(int(po["ordered_on"][:4]), []).append(line["unit_cost_minor"])
    assert max(costs[2024]) < min(costs[2026])


def test_pos_rows_and_z_reports_agree() -> None:
    cash: Counter = Counter()
    for r in rows("pos_sales.csv"):
        assert int(r["qty"]) * int(r["unit_price_minor"]) - int(r["discount_minor"]) == int(
            r["line_total_minor"]
        )
        if r["payment_method"] == "cash" and r["txn_type"] != "void":
            cash[(r["business_date"], r["register_id"])] += int(r["line_total_minor"])
    for z in rows("pos_z_reports.csv"):
        assert (
            int(z["cash_sales_minor"]) + int(z["cash_refunds_minor"])
            == cash[(z["business_date"], z["register_id"])]
        )


def test_events_have_valid_unique_ids_and_known_parties() -> None:
    evs = events()
    ids = [e["id"] for e in evs]
    assert len(ids) == len(set(ids)) and all(ULID.match(i) for i in ids)
    assert [(e["occurred_at"], e["id"]) for e in evs] == sorted(
        (e["occurred_at"], e["id"]) for e in evs
    )
    parties = {r["party_id"] for r in rows("parties.csv")}
    assert all(e.get("party") in parties for e in evs if e.get("party"))


def test_events_validate_against_the_contract() -> None:
    contracts = pytest.importorskip("fiona_contracts")
    for event in events()[::50] + [e for e in events() if e["event"] != "sale"][::20]:
        contracts.LedgerEvent.model_validate(event)


def test_ids_match_the_engine_rule() -> None:
    engine_ids = pytest.importorskip("engine.ledger.ids")
    moment = core.local_time(date(2026, 10, 3), 600, 5, 5)
    for prefix, source_type, source_key in (
        ("evt", "pos_export", "R1-000001"),
        ("bln", "bank_statement", "PK#7"),
    ):
        assert core.source_ulid(
            prefix, moment, "ten_x", source_type, source_key
        ) == engine_ids.source_ulid(prefix, moment, "ten_x", source_type, source_key)


def test_ibans_are_well_formed_and_synthetic() -> None:
    ibans = [r["bank_iban"] for r in rows("parties.csv") if r["bank_iban"]]
    for value in [*ibans, obj("tenant.json")["bank_accounts"][0]["iban"]]:
        assert len(value) == 24 and core.iban_is_valid(value) and value[4:7] == "SYN", value


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


# ---------------------------------------------------------------- planted scenarios (B3)
def test_every_b3_scenario_has_an_answer_key_entry() -> None:
    scenarios = load_scenarios()
    expected = {s["id"] for s in scenarios["scenarios"] + scenarios["controls"]}
    entries = {s["id"]: s for s in key()["scenarios"]}
    assert expected == set(entries)
    for sid, entry in entries.items():
        for bill_id in entry["refs"]["bill_ids"]:
            assert bill_id in bills(), (sid, bill_id)


def test_scenario_rows_carry_the_planted_facts() -> None:
    b, parties = bills(), {p["party_id"]: p for p in rows("parties.csv")}
    assert (b["bill_2231"]["number"], b["bill_2231"]["total_minor"]) == ("INV-2231", 18_450_000)
    assert b["bill_2188"]["number"] == "INV 2231" and b["bill_2240"]["total_minor"] == 28_036_800
    assert (
        parties["sup_018"]["on_allow_list"] == "false"
        and b["bill_2244"]["total_minor"] == 8_500_000
    )
    assert parties["sup_011"]["bank_account_changed_at"] == "2026-10-10T08:00:00Z"
    assert b["bill_2246"]["entered_by"] == "usr_finance_01"
    assert b["bill_2247"]["document_sha256"] == b["bill_2101"]["document_sha256"]  # S-05: same file
    assert (b["bill_2150"]["number"], b["bill_2248"]["number"]) == ("HDC/412", "HDC/0412")
    assert b["bill_2248"]["total_minor"] == 10_060_000
    po_id = next(
        p["po_id"]
        for p in obj("purchase_orders.json")["purchase_orders"]
        if p["number"] == b["bill_2249"]["po_number"]
    )
    grn = next(g for g in obj("goods_received.json")["goods_received"] if g["po_id"] == po_id)
    assert (grn["lines"][0]["qty_received"], b["bill_2249"]["lines"][0]["qty"]) == (40, 50)  # S-06
    assert (
        b["bill_2250"]["tax"][0]["amount_minor"] == 2_914_407
        and b["bill_2250"]["total_minor"] == 18_550_000
    )
    assert parties["sup_013"]["tax_id"] == "441702-36"  # S-11
    assert "ignore previous checks" in b["bill_2258"]["notes"]  # S-12
    s10 = [b[i]["total_minor"] for i in ("bill_2253", "bill_2254", "bill_2255", "bill_2256")]
    assert s10 == [15_000_000, 14_800_000, 14_950_001, 900_000]
    assert all(
        b[i]["due_date"] == "2026-10-23"
        for i in ("bill_2253", "bill_2254", "bill_2255", "bill_2256")
    )
    assert (b["bill_2260"]["number"], b["bill_2261"]["number"]) == (
        "KAC-2026-0010",
        "KAC-2026-0011",
    )
    rent = [x for x in b.values() if x["number"] in ("RNT-2026-09", "RNT-2026-10")]
    assert len(rent) == 2 and {x["total_minor"] for x in rent} == {35_000_000}
    phone = [e for e in events() if e["event"] == "bank_detail_change" and e["party"] == "sup_003"]
    assert phone[0]["confirmed_via"] == "phone" and phone[0]["confirmed_by"] == "usr_owner"  # C-03


def test_scenario_proposals_are_contract_shaped() -> None:
    contracts = pytest.importorskip("fiona_contracts")
    proposals = [p["proposal"] for s in key()["scenarios"] for p in s["proposals"]]
    assert len(proposals) >= 20
    for proposal in proposals:
        if proposal[
            "evidence"
        ]:  # S-08c has none: rejected at intake by design (evidence minItems 1)
            contracts.validate("ProposalDraft", proposal)


def test_clean_bills_exclude_every_planted_problem() -> None:
    clean = set(key()["clean_bill_ids"])
    assert len(clean) >= 20
    assert not clean & {
        "bill_2231",
        "bill_2247",
        "bill_2248",
        "bill_2249",
        "bill_2250",
        "bill_2257",
        "bill_2258",
    }


# ---------------------------------------------------------------- calibration truths for other lanes
def test_cash_dip_is_first_below_the_buffer_in_week_seven() -> None:
    dip = key()["other_lanes"]["cash_dip"]
    closings = [w["closing_minor"] for w in dip["weekly_closing_minor"]]
    assert dip["first_week_below_buffer"] == 7 and dip["week_of_min"] == 7
    assert all(c >= dip["buffer_minor"] for c in closings[:6])
    assert closings[6] < dip["buffer_minor"]


def test_fiscal_years_read_as_growth_then_shake_out() -> None:
    fy = {y["fiscal_year"]: y for y in key()["other_lanes"]["fiscal_year_cash_flows"]}
    assert (
        fy["FY25"]["cfo_minor"] > 0 and fy["FY25"]["cfi_minor"] < 0 and fy["FY25"]["cff_minor"] > 0
    )
    assert fy["FY26"]["cfo_minor"] * 100 < -2 * fy["FY26"]["revenue_ex_tax_minor"]
    assert fy["FY26"]["cfi_minor"] < 0 and fy["FY26"]["cff_minor"] < 0
    assert fy["FY26"]["revenue_ex_tax_minor"] > fy["FY25"]["revenue_ex_tax_minor"]


def test_most_bills_fit_the_treasurer_cap() -> None:
    assert 8_500 <= key()["bill_size"]["share_within_cap_bp"] <= 9_200


def test_other_lane_truths_are_present() -> None:
    lanes = key()["other_lanes"]
    assert lanes["dead_stock"] or lanes["slow_stock"]
    assert len(lanes["nrv_events"]) == 2
    spike = next(a for a in lanes["pos_anomalies"] if a["kind"] == "refund_spike")
    assert (
        spike["measured_refunds"] * 1000 >= 40 * spike["measured_receipts"]
    )  # far above the 1 % norm


def test_holdout_is_separate_and_after_as_of() -> None:
    weeks = json.loads(render_holdout(output())["cash_weekly.json"])["weeks"]
    assert weeks[0]["start"] == "2026-10-23" and len(weeks) == 13
    assert all(r["business_date"] <= "2026-10-22" for r in rows("pos_sales.csv"))
