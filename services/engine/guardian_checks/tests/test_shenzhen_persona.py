"""Tier 2 / Task D7: Shenzhen persona & Chinese Accounting Standards (CAS) scenarios.

Verifies:
- CN-S-01: Duplicate fapiao from the same supplier triggers Rule G-05 block.
- CN-S-02: Malformed Unified Social Credit Code (USCC != 18 chars) triggers Rule G-11 escalate under CN country pack.
- Valid 18-character USCC under Chinese country pack passes G-11.
"""

from __future__ import annotations

from engine.guardian_checks.combine import combine
from engine.guardian_checks.context import (
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

TENANT_SHENZHEN = "ten_shenzhen_electronics"
NOW = "2026-10-22T09:00:00Z"


def _shenzhen_baseline(
    *,
    bill_number: str = "FP-20261022-8801",
    supplier_uscc: str = "91440300MA5F88888X",
    prior_bills: list[PriorBillContext] | None = None,
) -> CheckContext:
    mandate = {
        "id": "mnd_treasurer_sz_v1",
        "tenant_id": TENANT_SHENZHEN,
        "agent": "treasurer",
        "version": 1,
        "status": "active",
        "currency": "CNY",
        "autonomy": {"payment": "act_within_mandate", "bill_approval": "act_within_mandate"},
        "allowed_action_types": ["payment", "bill_approval"],
        "per_payment_cap_minor": 500_000_00,  # 500,000 CNY cap
        "daily_cap_minor": 2_000_000_00,
        "effective_from": "2026-01-01",
        "approved_by": "usr_owner",
        "created_at": NOW,
    }
    proposal = {
        "id": "prop_sz_01",
        "tenant_id": TENANT_SHENZHEN,
        "agent": "treasurer",
        "type": "payment",
        "created_at": NOW,
        "summary": "Payment for electronics microcontrollers to Shenzhen supplier",
        "amount": {"minor": 150_000_00, "currency": "CNY"},
        "payload": {"payee_id": "sup_sz_001", "bill_id": "bill_sz_8801", "pay_on": "2026-10-23"},
        "evidence": [{"kind": "ledger_row", "ref": "bill_sz_8801"}],
        "reasoning": "Due in 15 days; cash buffer in CNY remains safe.",
        "mandate_ref": "mnd_treasurer_sz_v1",
    }
    payee = PartyContext(
        party_id="sup_sz_001",
        on_allow_list=True,
        tax_id=supplier_uscc,
        tax_id_type="USCC",
    )
    bill = BillContext(
        bill_id="bill_sz_8801",
        supplier_id="sup_sz_001",
        number=bill_number,
        subtotal_minor=132_743_36,
        total_minor=150_000_00,
        outstanding_balance_minor=150_000_00,
        currency="CNY",
        supplier_tax_id=supplier_uscc,
        po_id="po_sz_001",
        po_number="PO-SZ-001",
        grn_id="grn_sz_001",
        lines=[
            BillLineContext(
                sku="MCU-32-ARM",
                item="32-bit ARM Cortex Microcontroller",
                qty=10_000,
                unit_price_minor=13_27,
                total_minor=132_743_36,
            )
        ],
        tax_lines=[
            TaxLineContext(code="VAT", rate_bp=1300, amount_minor=17_256_64, base_minor=132_743_36)
        ],
    )
    po = POContext(
        id="po_sz_001",
        number="PO-SZ-001",
        lines=[POLineContext(sku="MCU-32-ARM", qty=10_000, unit_price_minor=13_27)],
    )
    grn = GRNContext(
        id="grn_sz_001",
        po_id="po_sz_001",
        lines=[GRNLineContext(sku="MCU-32-ARM", qty_received=10_000)],
    )
    forecast = ForecastContext(
        weeks=[
            ForecastWeek(w=1, start="2026-10-22", closing_minor=4_800_000_00),
            ForecastWeek(w=2, start="2026-10-29", closing_minor=4_500_000_00),
            ForecastWeek(w=3, start="2026-11-05", closing_minor=4_200_000_00),
        ]
    )
    evidence_index = {
        "bill_sz_8801": {"kind": "bill", "party_id": "sup_sz_001", "amount_minor": 150_000_00},
    }

    return CheckContext(
        proposal=proposal,
        mandate=mandate,
        country="CN",
        currency="CNY",
        buffer_minor=250_000_00,
        payee=payee,
        bill=bill,
        po=po,
        grn=grn,
        prior_bills=prior_bills or [],
        forecast=forecast,
        paid_today_minor=0,
        evidence_index=evidence_index,
        now=NOW,
    )


def test_shenzhen_cn_s01_duplicate_fapiao_is_blocked():
    """Scenario CN-S-01: Duplicate fapiao number from same supplier triggers Rule G-05 block."""
    fapiao_no = "FP-20261022-8801"
    prior_bill = PriorBillContext(
        bill_id="bill_sz_earlier",
        supplier_id="sup_sz_001",
        number=fapiao_no,
        total_minor=150_000_00,
    )
    ctx = _shenzhen_baseline(bill_number=fapiao_no, prior_bills=[prior_bill])
    checks = run_deterministic_checks(ctx)

    g05 = next(c for c in checks if c.rule == "G-05")
    assert g05.result == "fail"
    assert g05.outcome == "block"
    assert "matches" in g05.detail.lower() or "duplicate" in g05.detail.lower()

    outcome, _ = combine(checks)
    assert outcome == "block"


def test_shenzhen_cn_s02_malformed_uscc_is_escalated():
    """Scenario CN-S-02: Malformed USCC (not 18 characters) triggers Rule G-11 escalate."""
    # USCC with only 15 characters (old business license number format)
    malformed_uscc = "91440300MA5F888"
    ctx = _shenzhen_baseline(supplier_uscc=malformed_uscc)
    checks = run_deterministic_checks(ctx)

    g11 = next(c for c in checks if c.rule == "G-11")
    assert g11.result == "fail"
    assert g11.outcome == "escalate"
    assert "pattern" in g11.detail.lower() or "match" in g11.detail.lower()


def test_shenzhen_valid_uscc_passes_g11():
    """Valid 18-character Chinese USCC passes Rule G-11 under CN country pack."""
    valid_uscc = "91440300MA5FB1234X"
    ctx = _shenzhen_baseline(supplier_uscc=valid_uscc)
    checks = run_deterministic_checks(ctx)

    g11 = next(c for c in checks if c.rule == "G-11")
    assert g11.result == "pass"
