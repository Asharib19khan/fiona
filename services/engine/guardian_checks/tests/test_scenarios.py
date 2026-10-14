"""Scenario tests for the deterministic Guardian checks (D5), driven by rulebook/scenarios.yaml.

Every scenario and control in Abdullah's B3 file becomes a test case. Each case starts from one
clean, fully matched payment built from `common` and the persona mandate in
rulebook/mandates.yaml, then overlays the scenario's `given`. The test asserts every row of
`expected_checks` and the combined `expected_outcome`, so the expectations come from the
rulebook rather than from the code under test. DEMO-1 has no `given`: it is built from the real
seed-42 fixture rows (bill_2231, bill_2188, sup_017 and its bank change).
"""

from __future__ import annotations

import copy
import csv
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from engine.guardian_checks.combine import combine
from engine.guardian_checks.context import (
    BankDetailChangeContext,
    BillContext,
    BillLineContext,
    CheckContext,
    ForecastContext,
    ForecastWeek,
    GRNContext,
    GRNLineContext,
    PartyContext,
    POContext,
    POLineContext,
    PriorBillContext,
    TaxLineContext,
)
from engine.guardian_checks.run import run_deterministic_checks

REPO_ROOT = Path(__file__).resolve().parents[4]
SCENARIOS = yaml.safe_load((REPO_ROOT / "rulebook" / "scenarios.yaml").read_text(encoding="utf-8"))
MANDATES = yaml.safe_load((REPO_ROOT / "rulebook" / "mandates.yaml").read_text(encoding="utf-8"))
FIXTURES = REPO_ROOT / "data" / "fixtures" / "ten_karachi_apparel"
COMMON = SCENARIOS["common"]
TENANT = "ten_karachi_apparel"
NOW = "2026-10-22T09:00:00Z"
GST_BP = COMMON["gst_rate_bp"]
OUTCOMES = {"approve", "approve_with_conditions", "escalate", "block"}
MODEL_RULES = {"G-12"}  # adversarial review: a model, tested by fiona-19 (A6), not here


# ---------------------------------------------------------------- baseline pieces
def treasurer_mandate() -> dict[str, Any]:
    persona = MANDATES["persona_mandates"][TENANT]["mandates"]
    mandate = next(m for m in persona if m["agent"] == "treasurer")
    return {"tenant_id": TENANT, **copy.deepcopy(mandate), **COMMON["treasurer_mandate"]}


def forecast() -> ForecastContext:
    fc = COMMON["forecast_fixture"]
    weeks = [ForecastWeek(**w) for w in fc["weeks"]]
    return ForecastContext(id=fc["id"], as_of=fc["as_of"], weeks=weeks)


def week_of(day: str) -> int | None:
    starts = [w["start"] for w in COMMON["forecast_fixture"]["weeks"]]
    week = None
    for i, start in enumerate(starts, start=1):
        if day >= start:
            week = i
    return week


def split_total(total: int) -> tuple[int, int]:
    """Subtotal and tax for a GST-inclusive total; the tax is within 1 minor of the rate."""
    subtotal = total * 10_000 // (10_000 + GST_BP)
    return subtotal, total - subtotal


def bill_for(
    total: int, *, bill_id: str = "bill_x", supplier: str = "sup_x", due: str = "2026-10-26"
) -> BillContext:
    subtotal, tax = split_total(total)
    return BillContext(
        bill_id=bill_id,
        supplier_id=supplier,
        number="INV-500",
        subtotal_minor=subtotal,
        total_minor=total,
        tax_rate_bp=GST_BP,
        lines=[
            BillLineContext(sku="KRT-M-BLU", qty=1, unit_price_minor=subtotal, total_minor=subtotal)
        ],
        tax_lines=[
            TaxLineContext(code="GST", rate_bp=GST_BP, amount_minor=tax, base_minor=subtotal)
        ],
        document_sha256="ab" * 32,
        po_number="PO-1",
        po_id="po_1",
        grn_id="grn_1",
        category="inventory_supplier",
        due_date=due,
        issue_date="2026-10-12",
        created_by="svc_extraction",
        supplier_bank_iban="PK00SYNB0000000000000001",
        supplier_tax_id="4417023-6",
        in_baseline_week=week_of(due),
        outstanding_balance_minor=total,
    )


def matched_po_grn(bill: BillContext) -> tuple[POContext, GRNContext]:
    po = POContext(
        id=bill.po_id,
        number=bill.po_number,
        lines=[
            POLineContext(sku=ln.sku, qty=ln.qty or 0, unit_cost_minor=ln.unit_price_minor or 0)
            for ln in bill.lines
        ],
    )
    grn = GRNContext(
        id=bill.grn_id,
        po_id=bill.po_id,
        lines=[GRNLineContext(sku=ln.sku, qty_received=ln.qty or 0) for ln in bill.lines],
    )
    return po, grn


def baseline(amount: int = 9_500_000) -> dict[str, Any]:
    """One clean payment that every rule passes, as plain parts so `given` can overlay them."""
    bill = bill_for(amount)
    po, grn = matched_po_grn(bill)
    mandate = treasurer_mandate()
    return {
        "proposal": {
            "id": "prop_test",
            "tenant_id": TENANT,
            "agent": "treasurer",
            "type": "payment",
            "summary": "Pay supplier bill INV-500",
            "amount": {"minor": amount, "currency": "PKR"},
            "payload": {
                "payee_id": "sup_x",
                "bill_id": "bill_x",
                "pay_on": "2026-10-26",
                "channel": "wallet",
                "category": "inventory_supplier",
            },
            "evidence": [
                {"kind": "ledger_row", "ref": "bill_x"},
                {"kind": "document", "ref": "doc_x"},
            ],
            "reasoning": "The bill is due on its due date; cash stays above the buffer.",
            "mandate_ref": mandate["id"],
        },
        "mandate": mandate,
        "payee": PartyContext(
            party_id="sup_x",
            on_allow_list=True,
            bank_iban=bill.supplier_bank_iban,
            tax_id="4417023-6",
            tax_id_type="NTN",
        ),
        "bill": bill,
        "po": po,
        "grn": grn,
        "prior_bills": [],
        "forecast": forecast(),
        "paid_today_minor": 0,
        "approver_id": None,
        "evidence_index": {
            "bill_x": {"kind": "bill", "party_id": "sup_x", "amount_minor": amount},
            "doc_x": {"kind": "document", "party_id": "sup_x"},
        },
        "now": NOW,
    }


def set_amount(parts: dict[str, Any], amount: int, *, due: str | None = None) -> None:
    """Keep proposal, bill, PO, GRN and evidence consistent with a new amount."""
    payee = parts["proposal"]["payload"]["payee_id"]
    parts["proposal"]["amount"]["minor"] = amount
    bill = bill_for(
        amount, supplier=payee, due=due or parts["bill"].due_date if parts["bill"] else "2026-10-26"
    )
    parts["bill"] = bill
    parts["po"], parts["grn"] = matched_po_grn(bill)
    parts["evidence_index"]["bill_x"] = {"kind": "bill", "party_id": payee, "amount_minor": amount}


def set_payee(parts: dict[str, Any], payee: str) -> None:
    parts["proposal"]["payload"]["payee_id"] = payee
    parts["payee"].party_id = payee
    if parts["bill"] is not None:
        parts["bill"].supplier_id = payee
    for record in parts["evidence_index"].values():
        if "party_id" in record:
            record["party_id"] = payee


def bill_from_lines(
    parts: dict[str, Any],
    lines: list[dict[str, Any]],
    tax: list[dict] | None = None,
    subtotal: int | None = None,
    total: int | None = None,
) -> None:
    bill = parts["bill"]
    bill.lines = [
        BillLineContext(
            sku=ln.get("sku"),
            qty=ln.get("qty", 1),
            unit_price_minor=ln.get("unit_price_minor"),
            total_minor=ln.get("qty", 1) * ln.get("unit_price_minor", 0),
        )
        for ln in lines
    ]
    bill.subtotal_minor = (
        subtotal if subtotal is not None else sum(ln.total_minor or 0 for ln in bill.lines)
    )
    if tax is None:
        tax = [
            {
                "code": "GST",
                "rate_bp": GST_BP,
                "amount_minor": (bill.subtotal_minor * GST_BP + 5_000) // 10_000,
            }
        ]
    bill.tax_lines = [TaxLineContext(base_minor=bill.subtotal_minor, **t) for t in tax]
    bill.stated_tax_minor = sum(t["amount_minor"] for t in tax)
    bill.total_minor = total if total is not None else bill.subtotal_minor + bill.stated_tax_minor
    bill.outstanding_balance_minor = bill.total_minor
    bill.tax_rate_bp = GST_BP if bill.tax_lines else None  # e.g. rent bills carry no GST
    parts["proposal"]["amount"]["minor"] = bill.total_minor
    parts["evidence_index"][bill.bill_id]["amount_minor"] = bill.total_minor


# ---------------------------------------------------------------- `given` overlay
def apply_given(parts: dict[str, Any], given: dict[str, Any]) -> None:
    proposal = given.get("proposal", {})
    if "payee_id" in proposal:
        set_payee(parts, proposal["payee_id"])
    bill_given = given.get("bill") or {}
    if "due_date" in bill_given and bill_given["due_date"] is None:
        # An unplanned payment: no bill, so the proposal cites the obligation and a quote instead.
        parts["bill"], parts["po"], parts["grn"] = None, None, None
        parts["proposal"]["payload"]["bill_id"] = None
        parts["proposal"]["evidence"] = [
            {"kind": "ledger_row", "ref": "po_unplanned"},
            {"kind": "document", "ref": "doc_quote"},
        ]
        parts["evidence_index"] = {
            "po_unplanned": {"kind": "purchase_order"},
            "doc_quote": {"kind": "document"},
        }
    if "amount_minor" in proposal:
        if parts["bill"] is not None:
            set_amount(parts, proposal["amount_minor"], due=bill_given.get("due_date"))
        else:
            parts["proposal"]["amount"]["minor"] = proposal["amount_minor"]
    for key in ("agent", "type"):
        if key in proposal:
            parts["proposal"][key] = proposal[key]
    if "pay_on" in proposal:
        parts["proposal"]["payload"]["pay_on"] = proposal["pay_on"]
    if "payload" in proposal:
        parts["proposal"]["payload"].update(proposal["payload"])
        if "bill_id" in proposal["payload"]:
            parts["bill"], parts["po"], parts["grn"] = None, None, None
    if "evidence" in proposal:
        parts["proposal"]["evidence"] = proposal["evidence"]
    for ref, state in (given.get("ledger") or {}).items():
        if state == "absent":
            parts["evidence_index"].pop(ref, None)

    mandate = given.get("mandate")
    if mandate:
        if mandate.get("agent", "treasurer") != "treasurer":
            autonomy = mandate.get("autonomy", {})
            parts["mandate"] = {
                "id": f"mnd_{mandate['agent']}_v1",
                "tenant_id": TENANT,
                "agent": mandate["agent"],
                "version": 1,
                "currency": "PKR",
                "autonomy": autonomy,
                "allowed_action_types": [t for t, level in autonomy.items() if level != "advise"],
                **{k: v for k, v in mandate.items() if k not in ("agent", "autonomy")},
            }
            parts["proposal"]["mandate_ref"] = parts["mandate"]["id"]
        else:
            parts["mandate"].update(mandate)

    party = given.get("party") or {}
    payee = parts["payee"]
    for key in ("on_allow_list", "tax_id", "tax_id_type", "bank_account_changed_at"):
        if key in party:
            setattr(payee, key, party[key])
    if "tax_id" in party and parts["bill"] is not None:
        parts["bill"].supplier_tax_id = party["tax_id"]
    if "latest_change_confirmed_via" in party:
        payee.latest_bank_detail_change = BankDetailChangeContext(
            confirmed_via=party["latest_change_confirmed_via"],
            occurred_at=party.get("bank_account_changed_at"),
        )
    if "country_pack_pattern" in given:
        payee.country_pack_pattern = given["country_pack_pattern"]
    if "now" in given:
        parts["now"] = given["now"]
    if "paid_today_minor" in given:
        paid = given["paid_today_minor"]
        parts["paid_today_minor"] = sum(paid) if isinstance(paid, list) else paid

    bill = parts["bill"]
    if bill is not None:
        for key in ("created_by", "document_sha256", "number", "grn_id", "in_baseline_week"):
            if key in bill_given:
                setattr(bill, key, bill_given[key])
        if "supplier_id" in bill_given:
            set_payee(parts, bill_given["supplier_id"])
        if "total_minor" in bill_given:
            set_amount(parts, bill_given["total_minor"])
            for key in ("document_sha256", "number", "grn_id"):
                if key in bill_given:
                    setattr(parts["bill"], key, bill_given[key])
        if "bill_lines" in given:
            bill_from_lines(parts, given["bill_lines"])
        if "subtotal_minor" in given:
            bill_from_lines(
                parts,
                [{"qty": 1, "unit_price_minor": given["subtotal_minor"]}],
                tax=given["tax"],
                subtotal=given["subtotal_minor"],
                total=given["total_minor"],
            )
        if "po_lines" in given:
            parts["po"].lines = [POLineContext(**ln) for ln in given["po_lines"]]
        if "grn_lines" in given:
            parts["grn"].lines = [GRNLineContext(**ln) for ln in given["grn_lines"]]
    if "approval" in given:
        parts["approver_id"] = given["approval"]["user_id"]
    for prior in given.get("prior_bills", []):
        parts["prior_bills"].append(PriorBillContext(**prior))


def context(parts: dict[str, Any]) -> CheckContext:
    return CheckContext(country="PK", buffer_minor=COMMON["buffer_minor"], **parts)


# ---------------------------------------------------------------- controls (descriptive `given`)
def control_parts(control: dict[str, Any]) -> dict[str, Any]:
    given = control["given"]
    if control["id"] == "C-01":
        parts = baseline(given["amount_minor"])
    elif control["id"] == "C-02":
        amount = given["amounts_minor"][1]
        parts = baseline(amount)
        set_payee(parts, given["supplier"].split()[0])
        bill = parts["bill"]
        bill.number, bill.category, bill.contract_ref = (
            given["numbers"][1],
            given["category"],
            "lease_br01",
        )
        bill.po_number = bill.po_id = bill.grn_id = None
        parts["po"] = parts["grn"] = None
        bill_from_lines(parts, [{"qty": 1, "unit_price_minor": amount}], tax=[])
        parts["proposal"]["payload"]["category"] = given["category"]
        parts["prior_bills"] = [
            PriorBillContext(
                bill_id="bill_prev",
                supplier_id=parts["payee"].party_id,
                number=given["numbers"][0],
                total_minor=given["amounts_minor"][0],
                document_sha256="cd" * 32,
                issue_date="2026-09-01",
            )
        ]
    elif control["id"] == "C-03":
        parts = baseline()
        parts["payee"].bank_account_changed_at = "2026-09-12T09:00:00Z"
        parts["payee"].latest_bank_detail_change = BankDetailChangeContext(
            confirmed_via=given["confirmed_via"],
            confirmed_by=given["confirmed_by"],
            days_before_as_of=given["days_since_bank_change"],
        )
    elif control["id"] == "C-04":
        parts = baseline(given["amounts_minor"][1])
        parts["bill"].number, parts["bill"].grn_id = given["numbers"][1], given["grns"][1]
        parts["prior_bills"] = [
            PriorBillContext(
                bill_id="bill_prev",
                supplier_id="sup_x",
                number=given["numbers"][0],
                total_minor=given["amounts_minor"][0],
                grn_id=given["grns"][0],
                document_sha256="cd" * 32,
                issue_date="2026-10-05",
            )
        ]
    else:  # pragma: no cover - a new control needs a builder here
        raise AssertionError(f"no builder for control {control['id']}")
    return parts


# ---------------------------------------------------------------- DEMO-1 from the seed-42 fixtures
def demo_parts() -> dict[str, Any]:
    bills = {
        b["bill_id"]: b
        for b in json.loads((FIXTURES / "bills.json").read_text(encoding="utf-8"))["bills"]
    }
    resend = bills["bill_2231"]
    with (FIXTURES / "parties.csv").open(encoding="utf-8") as handle:
        party = next(p for p in csv.DictReader(handle) if p["party_id"] == resend["supplier_id"])
    events = [
        json.loads(line)
        for line in (FIXTURES / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    change = next(
        e for e in events if e["event"] == "bank_detail_change" and e["party"] == party["party_id"]
    )
    parts = baseline(resend["total_minor"])
    set_payee(parts, party["party_id"])
    parts["proposal"]["payload"].update(bill_id=resend["bill_id"], pay_on="2026-10-23")
    parts["proposal"]["evidence"] = [
        {"kind": "ledger_row", "ref": resend["bill_id"]},
        {"kind": "document", "ref": resend["document_id"]},
    ]
    parts["evidence_index"] = {
        resend["bill_id"]: {
            "kind": "bill",
            "party_id": party["party_id"],
            "amount_minor": resend["total_minor"],
        },
        resend["document_id"]: {"kind": "document", "party_id": party["party_id"]},
    }
    bill = parts["bill"]
    bill.bill_id, bill.number, bill.document_sha256 = (
        resend["bill_id"],
        resend["number"],
        resend["document_sha256"],
    )
    bill.supplier_bank_iban, bill.supplier_tax_id = (
        resend["supplier"]["bank_iban"],
        resend["supplier"]["tax_id"],
    )
    bill.notes = resend["notes"]
    bill_from_lines(
        parts,
        [
            {"sku": ln["sku"], "qty": ln["qty"], "unit_price_minor": ln["unit_price_minor"]}
            for ln in resend["lines"]
        ],
        tax=[{k: t[k] for k in ("code", "rate_bp", "amount_minor")} for t in resend["tax"]],
    )
    parts["po"], parts["grn"] = matched_po_grn(parts["bill"])
    parts["payee"].bank_iban = party["bank_iban"]
    parts["payee"].tax_id = party["tax_id"]
    parts["payee"].bank_account_changed_at = party["bank_account_changed_at"]
    parts["payee"].latest_bank_detail_change = BankDetailChangeContext(
        confirmed_via=change["confirmed_via"],
        confirmed_by=change["confirmed_by"],
        old_iban=change["old_iban"],
        new_iban=change["new_iban"],
        occurred_at=change["occurred_at"],
    )
    parts["prior_bills"] = [
        PriorBillContext(
            bill_id=b["bill_id"],
            supplier_id=b["supplier_id"],
            number=b["number"],
            total_minor=b["total_minor"],
            document_sha256=b["document_sha256"],
            issue_date=b["issue_date"],
        )
        for b in bills.values()
        if b["supplier_id"] == party["party_id"] and b["bill_id"] != "bill_2231"
    ]
    return parts


# ---------------------------------------------------------------- the tests
CASES = [pytest.param(s, id=s["id"]) for s in SCENARIOS["scenarios"]] + [
    pytest.param(c, id=c["id"]) for c in SCENARIOS["controls"]
]


def expected_outcome(case: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """The outcome and check rows a case expects. Controls describe theirs in prose."""
    outcome, rows = case.get("expected_outcome"), list(case.get("expected_checks") or [])
    if outcome in OUTCOMES:
        return outcome, rows
    overall = re.search(r"overall (\w+)", outcome or "")
    rows += [
        {"rule": rule, "result": "pass"} for rule in re.findall(r"(G-\d\d) pass", outcome or "")
    ]
    return (overall.group(1) if overall else "approve"), rows


@pytest.mark.parametrize("case", CASES)
def test_scenario(case: dict[str, Any]) -> None:
    rules = set(case.get("rules", []))
    if rules and rules <= MODEL_RULES:
        pytest.skip(
            "model-only rule (G-12 adversarial review); covered by the Guardian service tests (A6)"
        )
    if case["id"] == "DEMO-1":
        parts = demo_parts()
    elif case["id"].startswith("C-"):
        parts = control_parts(case)
    else:
        parts = baseline()
        apply_given(parts, case.get("given") or {})

    checks = run_deterministic_checks(context(parts))
    by_rule = {c.rule: c for c in checks}
    outcome, rows = expected_outcome(case)

    for row in rows:
        if row["rule"] in MODEL_RULES:
            continue
        assert row["rule"] in by_rule, f"{case['id']}: {row['rule']} did not run"
        check = by_rule[row["rule"]]
        assert check.result == row["result"], f"{case['id']} {row['rule']}: {check.detail}"
        if "outcome" in row:
            assert check.outcome == row["outcome"], f"{case['id']} {row['rule']}: {check.detail}"
        if "detail_contains" in row:
            assert row["detail_contains"] in check.detail, (
                f"{case['id']} {row['rule']}: {check.detail}"
            )
        if "match_signal" in row:
            assert (check.audit or {}).get("match_signal") == row["match_signal"], check.audit
        for condition in row.get("conditions", []):
            assert check.condition is not None and check.condition.model_dump() == condition

    combined, _ = combine(checks)
    failing = {c.rule: c.detail for c in checks if c.result == "fail"}
    assert combined == outcome, (
        f"{case['id']}: combined {combined}, expected {outcome}; failing rules: {failing}"
    )


def test_every_scenario_is_covered() -> None:
    ids = {s["id"] for s in SCENARIOS["scenarios"]} | {c["id"] for c in SCENARIOS["controls"]}
    assert {"DEMO-1", "S-01", "S-05b", "S-08a", "S-08b", "S-08c", "S-13", "C-01", "C-04"} <= ids
