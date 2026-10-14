"""Scenario tests for deterministic Guardian checks (D5).

Validates DEMO-1, S-01 to S-13 (including S-05b and S-08a/b/c), and controls C-01 to C-04
against the authoritative rulebook/scenarios.yaml specifications.
"""

from __future__ import annotations

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
)
from engine.guardian_checks.run import run_deterministic_checks

REPO_ROOT = Path(__file__).resolve().parents[4]
SCENARIOS_PATH = REPO_ROOT / "rulebook" / "scenarios.yaml"


@pytest.fixture(scope="session")
def scenarios_data() -> dict[str, Any]:
    with open(SCENARIOS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_forecast_context(fc_dict: dict[str, Any]) -> ForecastContext:
    weeks = [
        ForecastWeek(w=w["w"], start=w["start"], closing_minor=w["closing_minor"])
        for w in fc_dict.get("weeks", [])
    ]
    return ForecastContext(
        id=fc_dict.get("id"),
        as_of=fc_dict.get("as_of"),
        weeks=weeks,
    )


# =============================================================================
# DEMO-1
# =============================================================================
def test_scenario_demo_1(scenarios_data: dict[str, Any]) -> None:
    """DEMO-1: Re-sent bill to a changed bank account, with urgency."""
    common = scenarios_data["common"]
    fc_ctx = _build_forecast_context(common["forecast_fixture"])

    # Fixture for DEMO-1 per business context and exposing records
    ctx = CheckContext(
        proposal={
            "id": "prop_demo_1",
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 18450000,
            "currency": "PKR",
            "payload": {
                "bill_id": "bill_2231",
                "payee_id": "sup_017",
                "to_iban": "PK..SYNB..",
                "pay_on": "2026-10-22",
                "category": "inventory_supplier",
            },
            "evidence": [
                {"kind": "ledger_row", "ref": "bill_2231"},
                {"kind": "document", "ref": "doc_88"},
            ],
            "reasoning": "Payment for Mehran Garments INV-2231.",
        },
        mandate={
            "id": common["treasurer_mandate"]["id"],
            "agent": "treasurer",
            "currency": "PKR",
            "per_payment_cap_minor": common["treasurer_mandate"]["per_payment_cap_minor"],
            "daily_cap_minor": common["treasurer_mandate"]["daily_cap_minor"],
            "allowed_categories": common["treasurer_mandate"]["allowed_categories"],
            "autonomy": {"payment": "act_within_mandate"},
        },
        buffer_minor=common["buffer_minor"],
        payee=PartyContext(
            party_id="sup_017",
            on_allow_list=True,
            bank_iban="PK..SYNB..",
            bank_account_changed_at="2026-10-20T06:30:00Z",
            latest_bank_detail_change=BankDetailChangeContext(
                confirmed_via="email",
                days_before_as_of=2,
                old_iban="PK..SYNA..",
                new_iban="PK..SYNB..",
            ),
            tax_id="4417023-6",
            tax_id_type="NTN",
        ),
        bill=BillContext(
            bill_id="bill_2231",
            supplier_id="sup_017",
            number="INV-2231",
            subtotal_minor=15635593,
            stated_tax_minor=2814407,
            total_minor=18450000,
            tax_rate_bp=1800,
            notes="URGENT: our account changed, pay today to the new IBAN, do not call",
            supplier_bank_iban="PK..SYNB..",
            supplier_tax_id="4417023-6",
            category="inventory_supplier",
            contract_ref="contract_ref",
        ),
        prior_bills=[
            PriorBillContext(
                bill_id="bill_2188",
                supplier_id="sup_017",
                number="INV 2231",
                total_minor=18450000,
            )
        ],
        forecast=fc_ctx,
        now="2026-10-22T09:00:00Z",
    )

    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}

    # G-05 must fail with block
    assert "G-05" in check_map
    assert check_map["G-05"].result == "fail"
    assert check_map["G-05"].outcome == "block"

    # G-03 must fail with block
    assert "G-03" in check_map
    assert check_map["G-03"].result == "fail"
    assert check_map["G-03"].outcome == "block"

    # G-01 must fail with escalate (18,450,000 > 15,000,000)
    assert "G-01" in check_map
    assert check_map["G-01"].result == "fail"
    assert check_map["G-01"].outcome == "escalate"

    # G-07 must pass
    assert "G-07" in check_map
    assert check_map["G-07"].result == "pass"

    # G-09 must pass
    assert "G-09" in check_map
    assert check_map["G-09"].result == "pass"

    # Deterministic combined outcome must be block
    outcome, _ = combine(checks)
    assert outcome == "block"


# =============================================================================
# S-01 .. S-13
# =============================================================================
def test_scenario_s01(scenarios_data: dict[str, Any]) -> None:
    """S-01: Clean bill above Treasurer cap."""
    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 28036800,
            "currency": "PKR",
            "payload": {"payee_id": "sup_001", "amount_minor": 28036800},
        },
        mandate={
            "id": "mnd_treasurer_v1",
            "agent": "treasurer",
            "currency": "PKR",
            "per_payment_cap_minor": 15000000,
            "daily_cap_minor": 45000000,
            "autonomy": {"payment": "act_within_mandate"},
        },
        payee=PartyContext(party_id="sup_001", on_allow_list=True),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-01"].result == "fail"
    assert check_map["G-01"].outcome == "escalate"


def test_scenario_s02(scenarios_data: dict[str, Any]) -> None:
    """S-02: Payee not on allow-list."""
    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 8500000,
            "currency": "PKR",
            "payload": {"payee_id": "sup_018"},
        },
        mandate={
            "id": "mnd_treasurer_v1",
            "agent": "treasurer",
            "currency": "PKR",
            "per_payment_cap_minor": 15000000,
            "daily_cap_minor": 45000000,
            "autonomy": {"payment": "act_within_mandate"},
        },
        payee=PartyContext(party_id="sup_018", on_allow_list=False),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-02"].result == "fail"
    assert check_map["G-02"].outcome == "escalate"
    assert check_map["G-01"].result == "pass"


def test_scenario_s03(scenarios_data: dict[str, Any]) -> None:
    """S-03: Bank change never confirmed out of band."""
    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 9600000,
            "currency": "PKR",
            "payload": {"payee_id": "sup_fabric"},
        },
        mandate={
            "id": "mnd_treasurer_v1",
            "agent": "treasurer",
            "currency": "PKR",
            "per_payment_cap_minor": 15000000,
            "daily_cap_minor": 45000000,
            "autonomy": {"payment": "act_within_mandate"},
        },
        payee=PartyContext(
            party_id="sup_fabric",
            bank_account_changed_at="2026-10-10T08:00:00Z",
            latest_bank_detail_change=BankDetailChangeContext(
                confirmed_via="email",
                days_before_as_of=12,
            ),
        ),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-03"].result == "fail"
    assert check_map["G-03"].outcome == "block"
    assert "not been confirmed by phone" in check_map["G-03"].detail


def test_scenario_s04(scenarios_data: dict[str, Any]) -> None:
    """S-04: Same person enters the bill and approves its payment."""
    ctx = CheckContext(
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 5000000},
        bill=BillContext(created_by="usr_finance_01"),
        bill_created_by="usr_finance_01",
        approver_id="usr_finance_01",
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-04"].result == "fail"
    assert check_map["G-04"].outcome == "block"


def test_scenario_s05(scenarios_data: dict[str, Any]) -> None:
    """S-05: Same bill file uploaded twice under a new bill record."""
    ctx = CheckContext(
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 6420000},
        bill=BillContext(
            bill_id="bill_2102",
            supplier_id="sup_005",
            number="BH-7781",
            total_minor=6420000,
            document_sha256="aaaa...same",
        ),
        prior_bills=[
            PriorBillContext(
                bill_id="bill_2101",
                supplier_id="sup_005",
                number="BH-7781",
                total_minor=6420000,
                document_sha256="aaaa...same",
            )
        ],
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-05"].result == "fail"
    assert check_map["G-05"].outcome == "block"
    assert check_map["G-05"].audit["match_signal"] == "same_document_hash"


def test_scenario_s05b(scenarios_data: dict[str, Any]) -> None:
    """S-05b: Re-sent bill with reformatted number and 0.6% higher amount."""
    ctx = CheckContext(
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 10060000},
        bill=BillContext(
            supplier_id="sup_005",
            number="HDC/0412",
            total_minor=10060000,
            grn_id="grn_1201",
        ),
        prior_bills=[
            PriorBillContext(
                bill_id="bill_2150",
                supplier_id="sup_005",
                number="HDC/412",
                total_minor=10000000,
                grn_id="grn_1201",
            )
        ],
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-05"].result == "fail"
    assert check_map["G-05"].outcome == "block"
    assert check_map["G-05"].audit["match_signal"] == "normalised_number_equal"


def test_scenario_s06(scenarios_data: dict[str, Any]) -> None:
    """S-06: Bill charges for more than was received (2500 bp variance)."""
    ctx = CheckContext(
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 6000000},
        po=POContext(lines=[POLineContext(sku="SHW-OS-MRN", qty=50, unit_cost_minor=120000)]),
        grn=GRNContext(lines=[GRNLineContext(sku="SHW-OS-MRN", qty_received=40)]),
        bill=BillContext(
            lines=[
                BillLineContext(
                    sku="SHW-OS-MRN",
                    qty=50,
                    unit_price_minor=120000,
                    total_minor=6000000,
                )
            ]
        ),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-06"].result == "fail"
    assert check_map["G-06"].outcome == "escalate"


def test_scenario_s07(scenarios_data: dict[str, Any]) -> None:
    """S-07: Tax on the bill is wrong."""
    ctx = CheckContext(
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 18550000},
        bill=BillContext(
            subtotal_minor=15635593,
            stated_tax_minor=2914407,
            tax_rate_bp=1800,
            total_minor=18550000,
        ),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-07"].result == "fail"
    assert check_map["G-07"].outcome == "block"


def test_scenario_s08a(scenarios_data: dict[str, Any]) -> None:
    """S-08a: Routine payment on due date with pre-existing dip -> approve."""
    common = scenarios_data["common"]
    fc_ctx = _build_forecast_context(common["forecast_fixture"])

    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 12000000,
            "currency": "PKR",
            "payload": {"pay_on": "2026-11-10"},
        },
        mandate={"per_payment_cap_minor": 15000000, "daily_cap_minor": 45000000},
        buffer_minor=common["buffer_minor"],
        forecast=fc_ctx,
        bill=BillContext(due_date="2026-11-10", in_baseline_week=4),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-08"].result == "pass"
    assert check_map["G-08"].outcome == "approve"
    assert "pre-existing dip in week 7" in check_map["G-08"].detail


def test_scenario_s08b(scenarios_data: dict[str, Any]) -> None:
    """S-08b: Early payment into week 7 dip -> approve_with_conditions (pay on 2026-12-08)."""
    common = scenarios_data["common"]
    fc_ctx = _build_forecast_context(common["forecast_fixture"])

    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 14000000,
            "currency": "PKR",
            "payload": {"pay_on": "2026-12-01"},
        },
        mandate={"per_payment_cap_minor": 15000000, "daily_cap_minor": 45000000},
        buffer_minor=common["buffer_minor"],
        forecast=fc_ctx,
        bill=BillContext(due_date="2026-12-08", in_baseline_week=8),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-08"].result == "fail"
    assert check_map["G-08"].outcome == "approve_with_conditions"
    assert check_map["G-08"].condition is not None
    assert check_map["G-08"].condition.date == "2026-12-08"


def test_scenario_s08c(scenarios_data: dict[str, Any]) -> None:
    """S-08c: Unplanned payment breaches buffer whenever paid -> escalate."""
    common = scenarios_data["common"]
    fc_ctx = _build_forecast_context(common["forecast_fixture"])

    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 170000000,
            "currency": "PKR",
            "payload": {"pay_on": "2026-10-23"},
        },
        mandate={"per_payment_cap_minor": 15000000, "daily_cap_minor": 45000000},
        buffer_minor=common["buffer_minor"],
        forecast=fc_ctx,
        bill=BillContext(due_date=None, in_baseline_week=None),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-08"].result == "fail"
    assert check_map["G-08"].outcome == "escalate"
    assert check_map["G-01"].result == "fail"
    assert check_map["G-01"].outcome == "escalate"


def test_scenario_s09(scenarios_data: dict[str, Any]) -> None:
    """S-09: Proposal cites an unresolvable bill -> block."""
    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 7500000,
            "payload": {"bill_id": "bill_9999", "payee_id": "sup_003"},
            "evidence": [
                {"kind": "ledger_row", "ref": "bill_9999"},
                {"kind": "document", "ref": "doc_999"},
            ],
            "reasoning": "Payment for bill 9999",
        },
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-09"].result == "fail"
    assert check_map["G-09"].outcome == "block"
    assert "does not resolve" in check_map["G-09"].detail


def test_scenario_s10(scenarios_data: dict[str, Any]) -> None:
    """S-10: Many small payments exceed daily cap."""
    # Paid today: 15,000,000 + 14,800,000 + 14,950,000 = 44,750,000
    ctx = CheckContext(
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 900000},
        mandate={"daily_cap_minor": 45000000, "per_payment_cap_minor": 15000000},
        paid_today_minor=44750000,
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-10"].result == "fail"
    assert check_map["G-10"].outcome == "escalate"
    assert check_map["G-01"].result == "pass"


def test_scenario_s11(scenarios_data: dict[str, Any]) -> None:
    """S-11: Malformed tax registration pattern -> escalate."""
    ctx = CheckContext(
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 5000000},
        payee=PartyContext(
            party_id="sup_013",
            tax_id="441702-36",
            tax_id_type="NTN",
            country_pack_pattern="^[0-9]{7}-[0-9]$",
        ),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-11"].result == "fail"
    assert check_map["G-11"].outcome == "escalate"


def test_scenario_s13(scenarios_data: dict[str, Any]) -> None:
    """S-13: Action type outside agent mandate -> block."""
    ctx = CheckContext(
        proposal={"agent": "cfo_strategist", "type": "payment", "amount_minor": 5000000},
        mandate={
            "agent": "cfo_strategist",
            "autonomy": {"decision_memo": "advise"},
            "allowed_action_types": ["decision_memo"],
        },
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-13"].result == "fail"
    assert check_map["G-13"].outcome == "block"


# =============================================================================
# Controls C-01 .. C-04
# =============================================================================
def test_control_c01(scenarios_data: dict[str, Any]) -> None:
    """C-01: Routine, fully matched bill within mandate -> approve."""
    common = scenarios_data["common"]
    fc_ctx = _build_forecast_context(common["forecast_fixture"])

    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 9500000,
            "currency": "PKR",
            "payload": {
                "payee_id": "sup_001",
                "to_iban": "PK..SYNA..",
                "pay_on": "2026-10-22",
                "category": "inventory_supplier",
            },
            "evidence": [
                {"kind": "ledger_row", "ref": "bill_clean_01"},
                {"kind": "document", "ref": "doc_clean_01"},
            ],
        },
        mandate={
            "agent": "treasurer",
            "currency": "PKR",
            "per_payment_cap_minor": 15000000,
            "daily_cap_minor": 45000000,
            "allowed_categories": ["inventory_supplier"],
            "autonomy": {"payment": "act_within_mandate"},
        },
        buffer_minor=common["buffer_minor"],
        payee=PartyContext(
            party_id="sup_001",
            on_allow_list=True,
            bank_iban="PK..SYNA..",
            tax_id="4417023-6",
            country_pack_pattern="^[0-9]{7}-[0-9]$",
        ),
        bill=BillContext(
            number="INV-CLEAN-01",
            subtotal_minor=8050847,
            stated_tax_minor=1449153,
            total_minor=9500000,
            tax_rate_bp=1800,
            due_date="2026-10-22",
            in_baseline_week=1,
            supplier_bank_iban="PK..SYNA..",
            supplier_tax_id="4417023-6",
            category="inventory_supplier",
        ),
        po=POContext(lines=[POLineContext(sku="ITEM-01", qty=10, unit_price_minor=950000)]),
        grn=GRNContext(lines=[GRNLineContext(sku="ITEM-01", qty_received=10)]),
        forecast=fc_ctx,
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    outcome, _ = combine(checks)
    assert outcome == "approve"


def test_control_c02(scenarios_data: dict[str, Any]) -> None:
    """C-02: Monthly rent recurring: G-05 passes, never block.

    Minimum fixture added for C-02: evidence and forecast baseline, so G-09 and G-08
    do not fail closed, testing specifically that G-05 passes and G-01 escalates.
    """
    common = scenarios_data["common"]
    fc_ctx = _build_forecast_context(common["forecast_fixture"])

    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 35000000,
            "currency": "PKR",
            "payload": {"payee_id": "pty_001", "category": "rent", "pay_on": "2026-10-22"},
            "evidence": [
                {"kind": "ledger_row", "ref": "bill_rent_10"},
                {"kind": "document", "ref": "doc_rent_10"},
            ],
        },
        mandate={
            "agent": "treasurer",
            "currency": "PKR",
            "per_payment_cap_minor": 15000000,
            "daily_cap_minor": 45000000,
            "allowed_categories": ["rent"],
            "autonomy": {"payment": "act_within_mandate"},
        },
        payee=PartyContext(
            party_id="pty_001",
            on_allow_list=True,
            bank_iban="PK..SYNB..",
            tax_id="4417023-6",
            country_pack_pattern="^[0-9]{7}-[0-9]$",
        ),
        bill=BillContext(
            supplier_id="pty_001",
            number="RNT-2026-10",
            total_minor=35000000,
            category="rent",
            contract_ref="LEASE-2026",
            supplier_bank_iban="PK..SYNB..",
            supplier_tax_id="4417023-6",
            due_date="2026-10-22",
            in_baseline_week=1,
        ),
        prior_bills=[
            PriorBillContext(
                supplier_id="pty_001",
                number="RNT-2026-09",
                total_minor=35000000,
            )
        ],
        forecast=fc_ctx,
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    # G-05 must pass
    assert check_map["G-05"].result == "pass"
    assert check_map["G-05"].outcome == "approve"

    # Overall outcome escalates only because 35m > 15m (G-01), but NEVER block
    outcome, _ = combine(checks)
    assert outcome != "block"
    assert outcome == "escalate"


def test_control_c03(scenarios_data: dict[str, Any]) -> None:
    """C-03: Bank change confirmed by phone 40 days ago -> approve."""
    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 5000000,
            "payload": {"payee_id": "sup_002", "to_iban": "PK..SYNB.."},
        },
        mandate={"per_payment_cap_minor": 15000000, "daily_cap_minor": 45000000},
        payee=PartyContext(
            party_id="sup_002",
            on_allow_list=True,
            bank_iban="PK..SYNB..",
            bank_account_changed_at="2026-09-12T08:00:00Z",
            latest_bank_detail_change=BankDetailChangeContext(
                confirmed_via="phone",
                confirmed_by="usr_owner",
                days_before_as_of=40,
                new_iban="PK..SYNB..",
            ),
        ),
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-03"].result == "pass"
    assert check_map["G-03"].outcome == "approve"


def test_control_c04(scenarios_data: dict[str, Any]) -> None:
    """C-04: Sequential invoice numbers, distinct deliveries -> approve.

    Minimum fixture added for C-04: evidence and forecast baseline, so G-09 and G-08
    do not fail closed, verifying G-05 passes and overall outcome is approve.
    """
    common = scenarios_data["common"]
    fc_ctx = _build_forecast_context(common["forecast_fixture"])

    ctx = CheckContext(
        proposal={
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 7400000,
            "currency": "PKR",
            "payload": {
                "payee_id": "sup_005",
                "to_iban": "PK..SYNA..",
                "pay_on": "2026-10-22",
                "category": "inventory_supplier",
            },
            "evidence": [
                {"kind": "ledger_row", "ref": "bill_kac_11"},
                {"kind": "document", "ref": "doc_kac_11"},
            ],
        },
        mandate={
            "agent": "treasurer",
            "currency": "PKR",
            "per_payment_cap_minor": 15000000,
            "daily_cap_minor": 45000000,
            "allowed_categories": ["inventory_supplier"],
            "autonomy": {"payment": "act_within_mandate"},
        },
        buffer_minor=common["buffer_minor"],
        payee=PartyContext(
            party_id="sup_005",
            on_allow_list=True,
            bank_iban="PK..SYNA..",
            tax_id="4417023-6",
            country_pack_pattern="^[0-9]{7}-[0-9]$",
        ),
        bill=BillContext(
            supplier_id="sup_005",
            number="KAC-2026-0011",
            total_minor=7400000,
            grn_id="grn_1102",
            due_date="2026-10-22",
            in_baseline_week=1,
            supplier_bank_iban="PK..SYNA..",
            supplier_tax_id="4417023-6",
            category="inventory_supplier",
        ),
        prior_bills=[
            PriorBillContext(
                supplier_id="sup_005",
                number="KAC-2026-0010",
                total_minor=6200000,
                grn_id="grn_1101",
            )
        ],
        po=POContext(lines=[POLineContext(sku="ITEM-KAC", qty=10, unit_price_minor=740000)]),
        grn=GRNContext(lines=[GRNLineContext(sku="ITEM-KAC", qty_received=10)]),
        forecast=fc_ctx,
        now="2026-10-22T09:00:00Z",
    )
    checks = run_deterministic_checks(ctx)
    check_map = {c.rule: c for c in checks}
    assert check_map["G-05"].result == "pass"
    assert check_map["G-05"].outcome == "approve"
    outcome, _ = combine(checks)
    assert outcome == "approve"
