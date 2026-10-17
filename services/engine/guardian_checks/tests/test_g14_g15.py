"""Tier 2 / Task: Guardian Rules G-14 & G-15 Activation and Validation.

Rules tested:
- G-14: Freshness of financial state and OCR/extraction consistency (forecast <= 24h, bank balance <= 48h).
- G-15: Insider payee fraud detection (payee account linked to employee / insider).
"""

from __future__ import annotations

from engine.guardian_checks.combine import combine
from engine.guardian_checks.context import (
    BillContext,
    CheckContext,
    ForecastContext,
    ForecastWeek,
    PartyContext,
)
from engine.guardian_checks.run import run_deterministic_checks

NOW = "2026-10-22T10:00:00Z"
TENANT = "ten_karachi_apparel"


def _base_ctx(
    *,
    forecast_as_of: str | None = None,
    bank_balance_as_of: str | None = None,
    extraction_confidence: dict[str, str] | None = None,
    insider_account: bool = False,
    action_type: str = "payment",
) -> CheckContext:
    mandate = {
        "id": "mnd_treasurer_v1",
        "tenant_id": TENANT,
        "agent": "treasurer",
        "version": 1,
        "status": "active",
        "currency": "PKR",
        "autonomy": {"payment": "act_within_mandate", "bill_approval": "act_within_mandate"},
        "allowed_action_types": ["payment", "bill_approval"],
        "per_payment_cap_minor": 5_000_000_00,
        "daily_cap_minor": 15_000_000_00,
        "effective_from": "2026-01-01",
        "approved_by": "usr_owner",
        "created_at": NOW,
    }
    proposal = {
        "id": "prop_test_01",
        "tenant_id": TENANT,
        "agent": "treasurer",
        "type": action_type,
        "created_at": NOW,
        "summary": "Vendor settlement",
        "amount": {"minor": 500_000_00, "currency": "PKR"},
        "payload": {"payee_id": "sup_001", "bill_id": "bill_001", "pay_on": "2026-10-23"},
        "evidence": [{"kind": "ledger_row", "ref": "bill_001"}],
        "mandate_ref": "mnd_treasurer_v1",
    }
    payee = PartyContext(
        party_id="sup_001",
        on_allow_list=True,
        tax_id="1234567-8",
        tax_id_type="NTN",
        insider_account_matches=insider_account,
    )
    bill = BillContext(
        bill_id="bill_001",
        supplier_id="sup_001",
        number="INV-2026-001",
        subtotal_minor=500_000_00,
        total_minor=500_000_00,
        currency="PKR",
        supplier_tax_id="1234567-8",
    )
    forecast = ForecastContext(
        as_of=forecast_as_of or NOW,
        weeks=[
            ForecastWeek(w=1, start="2026-10-22", closing_minor=10_000_000_00),
            ForecastWeek(w=2, start="2026-10-29", closing_minor=9_500_000_00),
        ],
    )
    evidence_index = {
        "bill_001": {"kind": "bill", "party_id": "sup_001", "amount_minor": 500_000_00},
    }

    return CheckContext(
        proposal=proposal,
        mandate=mandate,
        tenant_id=TENANT,
        country="PK",
        currency="PKR",
        buffer_minor=500_000_00,
        payee=payee,
        bill=bill,
        forecast=forecast,
        bank_balance_as_of=bank_balance_as_of or NOW,
        extraction_confidence=extraction_confidence or {},
        evidence_index=evidence_index,
        now=NOW,
    )


def test_proposed_rules_disabled_by_default():
    """G-14 and G-15 do not run when enable_proposed is False."""
    ctx = _base_ctx()
    checks = run_deterministic_checks(ctx, enable_proposed=False)
    rule_ids = {c.rule for c in checks}
    assert "G-14" not in rule_ids
    assert "G-15" not in rule_ids


def test_g14_fresh_inputs_pass():
    """When financial snapshots are fresh (forecast <= 24h, balance <= 48h), G-14 passes."""
    ctx = _base_ctx()
    checks = run_deterministic_checks(ctx, enable_proposed=True)
    g14 = next(c for c in checks if c.rule == "G-14")
    assert g14.result == "pass"
    assert g14.outcome == "approve"


def test_g14_stale_forecast_escalates():
    """When the 13-week forecast baseline is older than 24 hours, G-14 fails closed with escalate."""
    stale_fc_time = "2026-10-20T10:00:00Z"  # 48 hours before NOW
    ctx = _base_ctx(forecast_as_of=stale_fc_time)
    checks = run_deterministic_checks(ctx, enable_proposed=True)
    g14 = next(c for c in checks if c.rule == "G-14")
    assert g14.result == "fail"
    assert g14.outcome == "escalate"
    assert "Forecast baseline age" in g14.detail
    assert "exceeds freshness limit" in g14.detail

    outcome, _ = combine(checks)
    assert outcome in ("escalate", "block")


def test_g14_stale_bank_balance_escalates():
    """When the bank balance snapshot is older than 48 hours, G-14 escalates."""
    stale_bank_time = "2026-10-19T08:00:00Z"  # 74 hours before NOW
    ctx = _base_ctx(bank_balance_as_of=stale_bank_time)
    checks = run_deterministic_checks(ctx, enable_proposed=True)
    g14 = next(c for c in checks if c.rule == "G-14")
    assert g14.result == "fail"
    assert g14.outcome == "escalate"
    assert "Bank balance snapshot age" in g14.detail


def test_g14_low_extraction_confidence_escalates():
    """When bill extraction fields have low confidence, G-14 escalates to require human eyes."""
    ctx = _base_ctx(extraction_confidence={"total_amount": "low", "iban": "low"})
    checks = run_deterministic_checks(ctx, enable_proposed=True)
    g14 = next(c for c in checks if c.rule == "G-14")
    assert g14.result == "fail"
    assert g14.outcome == "escalate"
    assert "Low confidence extracted fields" in g14.detail


def test_g15_clean_payee_passes():
    """A regular verified payee whose bank details do not match insider accounts passes G-15."""
    ctx = _base_ctx(insider_account=False)
    checks = run_deterministic_checks(ctx, enable_proposed=True)
    g15 = next(c for c in checks if c.rule == "G-15")
    assert g15.result == "pass"
    assert g15.outcome == "approve"


def test_g15_insider_payee_escalates():
    """When payee bank account matches an internal director/employee account, G-15 escalates."""
    ctx = _base_ctx(insider_account=True)
    checks = run_deterministic_checks(ctx, enable_proposed=True)
    g15 = next(c for c in checks if c.rule == "G-15")
    assert g15.result == "fail"
    assert g15.outcome == "escalate"
    assert "insider" in g15.detail.lower()

    outcome, _ = combine(checks)
    assert outcome in ("escalate", "block")


def test_g15_not_applicable_for_non_payment():
    """G-15 applies strictly to payment execution, not general bill approvals."""
    ctx = _base_ctx(insider_account=True, action_type="bill_approval")
    checks = run_deterministic_checks(ctx, enable_proposed=True)
    assert not any(c.rule == "G-15" for c in checks)
