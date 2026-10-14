"""Regression tests for the D5 review fixes (fail closed, no literals, rulebook semantics)."""

from __future__ import annotations

import pytest

from engine.guardian_checks import rules
from engine.guardian_checks.checks import (
    g03_bank_account_change,
    g05_duplicate_bill,
    g08_cash_buffer,
    g09_evidence_check,
    g13_mandate_permission,
)
from engine.guardian_checks.context import BankDetailChangeContext, CheckContext, PriorBillContext
from engine.guardian_checks.tests.test_scenarios import baseline, context


def test_g09_without_a_resolver_fails_closed() -> None:
    parts = baseline()
    parts["evidence_index"] = None
    check = g09_evidence_check(context(parts))
    assert (check.result, check.outcome) == ("fail", "escalate")
    assert check.detail.startswith("CHECK_ERROR")


def test_g09_blocks_evidence_that_contradicts_the_payload() -> None:
    parts = baseline()
    parts["evidence_index"]["bill_x"]["party_id"] = "sup_other"
    check = g09_evidence_check(context(parts))
    assert (check.result, check.outcome) == ("fail", "block")
    assert "sup_other" in check.detail


def test_g09_escalates_a_reasoning_figure_no_record_supports() -> None:
    parts = baseline()
    parts["proposal"]["reasoning"] = "Pay PKR 75,000 today."
    check = g09_evidence_check(context(parts))
    assert (check.result, check.outcome) == ("fail", "escalate")


def test_g13_blocks_an_agent_without_a_mandate() -> None:
    parts = baseline()
    parts["mandate"] = None
    check = g13_mandate_permission(context(parts))
    assert (check.result, check.outcome) == ("fail", "block")


def test_g13_blocks_a_mandate_that_belongs_to_another_agent() -> None:
    parts = baseline()
    parts["proposal"]["agent"] = "controller"
    check = g13_mandate_permission(context(parts))
    assert (check.result, check.outcome) == ("fail", "block")


def test_g13_window_uses_the_requested_pay_date() -> None:
    parts = baseline()
    parts["proposal"]["payload"]["pay_on"] = "2026-10-25"  # a Sunday; the window is Mon..Sat
    check = g13_mandate_permission(context(parts))
    assert (check.result, check.outcome) == ("fail", "escalate")


def test_g03_requires_a_phone_confirmation_recorded_by_a_user() -> None:
    parts = baseline()
    parts["payee"].bank_account_changed_at = "2026-09-01T09:00:00Z"
    parts["payee"].latest_bank_detail_change = BankDetailChangeContext(
        confirmed_via="phone", confirmed_by="supplier email", days_before_as_of=51
    )
    assert g03_bank_account_change(context(parts)).outcome == "block"
    parts["payee"].latest_bank_detail_change.confirmed_by = "usr_owner"
    assert g03_bank_account_change(context(parts)).outcome == "approve"


def test_g08_payment_before_the_horizon_counts_from_week_one() -> None:
    parts = baseline(170_000_000)
    parts["proposal"]["payload"]["pay_on"] = "2026-10-01"  # before week 1 (19 Oct)
    parts["bill"].in_baseline_week = None
    parts["bill"].due_date = None
    check = g08_cash_buffer(context(parts))
    assert check.outcome == "escalate"


def test_g08_never_delays_a_statutory_payment() -> None:
    parts = baseline(14_000_000)
    parts["proposal"]["payload"].update(pay_on="2026-12-01", category="taxes_and_duties")
    parts["bill"].due_date, parts["bill"].in_baseline_week = "2026-12-08", 8
    assert g08_cash_buffer(context(parts)).outcome == "escalate"


def test_missing_threshold_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    thresholds = dict(rules.THRESHOLDS)
    thresholds["T-G05-SIM"] = {"id": "T-G05-SIM"}  # value removed from the rulebook
    monkeypatch.setattr(rules, "THRESHOLDS", thresholds)
    parts = baseline()
    parts["prior_bills"] = [
        PriorBillContext(bill_id="bill_p", supplier_id="sup_x", number="INV-501", total_minor=1)
    ]
    check = g05_duplicate_bill(context(parts))
    assert (check.result, check.outcome) == ("fail", "escalate")
    assert check.detail.startswith("CHECK_ERROR")


def test_buffer_is_required() -> None:
    parts = baseline()
    with pytest.raises(ValueError):
        CheckContext(country="PK", **parts)
