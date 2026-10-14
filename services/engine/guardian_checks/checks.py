"""Deterministic Guardian check implementations (D5).

Implements individual rules G-01 to G-11, G-13 (Tier 1), and proposed G-14, G-15 (Tier 2).
Every rule function has signature `(ctx: CheckContext) -> Check | None`.
Returns None if the rule does not apply to the action type.
Fails closed with outcome='escalate' and detail='CHECK_ERROR: <reason>' on exceptions.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz

from engine.guardian_checks.context import CheckContext
from engine.guardian_checks.rules import (
    MATERIAL_DECISION_TYPES,
    PO_EXEMPT_CATEGORIES,
    STATUTORY_CATEGORIES,
    get_threshold,
    tax_id_pattern,
)
from fiona_contracts.models import Check, PayOnCondition


def _mask_iban(iban: str | None) -> str | None:
    if not iban:
        return None
    if len(iban) <= 8:
        return iban[:2] + "****" + iban[-2:]
    return iban[:4] + "****" + iban[-4:]


def _mask_tax_id(tax_id: str | None) -> str | None:
    if not tax_id:
        return None
    if len(tax_id) <= 4:
        return "****"
    return tax_id[:2] + "****" + tax_id[-2:]


def normalise_bill_number(s: str) -> str:
    """Normalise bill number per guardian.yaml G-05 specifications:

    1. Uppercase
    2. Strip leading zeros from each maximal digit run
    3. Remove every non-alphanumeric character
    """
    s = s.upper()

    def _strip_leading_zeros(m: re.Match[str]) -> str:
        stripped = m.group(0).lstrip("0")
        return stripped if stripped else "0"

    s = re.sub(r"\d+", _strip_leading_zeros, s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


# -----------------------------------------------------------------------------
# G-01: Per-payment cap
# -----------------------------------------------------------------------------
def g01_per_payment_cap(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type != "payment":
        return None

    try:
        amount_minor = ctx.get_amount_minor()
        if amount_minor is None:
            return Check(
                name="policy",
                rule="G-01",
                result="fail",
                outcome="escalate",
                detail="CHECK_ERROR: Proposal amount is missing.",
            )

        if ctx.mandate is None:
            return Check(
                name="policy",
                rule="G-01",
                result="fail",
                outcome="escalate",
                detail="CHECK_ERROR: Agent mandate is missing.",
            )

        cap_minor = getattr(ctx.mandate, "per_payment_cap_minor", None)
        if cap_minor is None and isinstance(ctx.mandate, dict):
            cap_minor = ctx.mandate.get("per_payment_cap_minor")
        if cap_minor is None:
            return Check(
                name="policy",
                rule="G-01",
                result="fail",
                outcome="escalate",
                detail="CHECK_ERROR: Mandate per_payment_cap_minor is missing.",
            )

        mandate_curr = getattr(ctx.mandate, "currency", None)
        if mandate_curr is None and isinstance(ctx.mandate, dict):
            mandate_curr = ctx.mandate.get("currency", "PKR")
        mandate_curr = str(mandate_curr or "PKR")

        prop_curr = ctx.get_currency()
        agent = ctx.get_agent() or "agent"
        mandate_id = getattr(ctx.mandate, "id", None) or (
            ctx.mandate.get("id") if isinstance(ctx.mandate, dict) else None
        )
        mandate_ver = getattr(ctx.mandate, "version", 1) or (
            ctx.mandate.get("version", 1) if isinstance(ctx.mandate, dict) else 1
        )

        audit: dict[str, Any] = {
            "amount_minor": amount_minor,
            "cap_minor": cap_minor,
            "mandate_id": mandate_id,
            "mandate_version": mandate_ver,
        }

        if prop_curr != mandate_curr:
            return Check(
                name="policy",
                rule="G-01",
                result="fail",
                outcome="escalate",
                detail=f"Payment currency {prop_curr} differs from mandate currency {mandate_curr}.",
                audit=audit,
            )

        if amount_minor > cap_minor:
            return Check(
                name="policy",
                rule="G-01",
                result="fail",
                outcome="escalate",
                detail=f"Payment of {amount_minor} is above the {agent}'s cap of {cap_minor} per payment.",
                audit=audit,
            )

        return Check(
            name="policy",
            rule="G-01",
            result="pass",
            outcome="approve",
            detail=f"Payment of {amount_minor} is within the {agent}'s cap of {cap_minor} per payment.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-01",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-02: Payee on allow-list
# -----------------------------------------------------------------------------
def g02_payee_allow_list(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type != "payment":
        return None

    try:
        payee_id = ctx.get_payee_id()
        on_allow_list = False
        allow_list_changed_at = None

        if ctx.payee is not None:
            on_allow_list = bool(ctx.payee.on_allow_list)
            allow_list_changed_at = ctx.payee.allow_list_changed_at
            if not payee_id:
                payee_id = ctx.payee.party_id

        audit: dict[str, Any] = {
            "payee_id": payee_id,
            "on_allow_list": on_allow_list,
            "allow_list_changed_at": str(allow_list_changed_at) if allow_list_changed_at else None,
        }

        if not payee_id or not on_allow_list:
            return Check(
                name="policy",
                rule="G-02",
                result="fail",
                outcome="escalate",
                detail=f"Payee {payee_id or 'unknown'} is not on the allow-list.",
                audit=audit,
            )

        return Check(
            name="policy",
            rule="G-02",
            result="pass",
            outcome="approve",
            detail=f"Payee {payee_id} is on the allow-list.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-02",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-03: Payee bank account changed within cooling-off or unconfirmed
# -----------------------------------------------------------------------------
def g03_bank_account_change(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type != "payment":
        return None

    try:
        cooling_off_threshold = get_threshold("T-G03-COOL")
        cooling_off_days = int(cooling_off_threshold["value"])

        party = ctx.payee
        now_dt = ctx.get_now_dt()

        party_id = party.party_id if party else (ctx.get_payee_id() or "unknown")
        bank_iban = party.bank_iban if party else None
        to_iban = ctx.get_to_iban()
        bill_iban = ctx.bill.supplier_bank_iban if ctx.bill else None

        changed_at = party.bank_account_changed_at if party else None
        change_event = party.latest_bank_detail_change if party else None

        confirmed_via = change_event.confirmed_via if change_event else None
        confirmed_by = change_event.confirmed_by if change_event else None
        old_iban = change_event.old_iban if change_event else None
        new_iban = change_event.new_iban if change_event else None

        days_since_change: int | None = None
        if change_event and change_event.days_before_as_of is not None:
            days_since_change = int(change_event.days_before_as_of)
        elif changed_at is not None:
            if isinstance(changed_at, str):
                s = changed_at[:-1] + "+00:00" if changed_at.endswith("Z") else changed_at
                change_dt = datetime.fromisoformat(s)
            else:
                change_dt = changed_at
            if change_dt.tzinfo is None:
                change_dt = change_dt.replace(tzinfo=UTC)
            days_since_change = max(0, (now_dt - change_dt).days)

        audit: dict[str, Any] = {
            "party_id": party_id,
            "old_iban_masked": _mask_iban(old_iban),
            "new_iban_masked": _mask_iban(new_iban or bank_iban),
            "changed_at": str(changed_at) if changed_at else None,
            "confirmed_via": confirmed_via,
            "confirmed_by": confirmed_by,
            "days_since_change": days_since_change,
        }

        # Check (c): Account discrepancy
        if to_iban and bank_iban and to_iban != bank_iban:
            return Check(
                name="policy",
                rule="G-03",
                result="fail",
                outcome="block",
                detail=f"Payment destination IBAN {to_iban} does not match IBAN on file {bank_iban}.",
                audit=audit,
            )
        if bill_iban and bank_iban and bill_iban != bank_iban:
            return Check(
                name="policy",
                rule="G-03",
                result="fail",
                outcome="block",
                detail=f"Bill IBAN {bill_iban} does not match IBAN on file {bank_iban}.",
                audit=audit,
            )

        # If there was a bank change:
        if changed_at is not None or change_event is not None:
            is_phone_or_in_person = confirmed_via == "phone" and str(confirmed_by or "").startswith(
                "usr_"
            )
            # (a) Changed within cooling-off period and not confirmed via phone
            if (
                days_since_change is not None
                and days_since_change < cooling_off_days
                and not is_phone_or_in_person
            ):
                return Check(
                    name="policy",
                    rule="G-03",
                    result="fail",
                    outcome="block",
                    detail=f"{party_id}'s bank account changed {days_since_change} days ago and has not been confirmed by phone.",
                    audit=audit,
                )
            # (b) Latest change was never confirmed out of band (confirmed_via in [email, none] or not confirmed), whatever its age
            if not is_phone_or_in_person:
                return Check(
                    name="policy",
                    rule="G-03",
                    result="fail",
                    outcome="block",
                    detail=f"{party_id}'s bank account change ({days_since_change or 'unknown'} days ago) has not been confirmed by phone.",
                    audit=audit,
                )

        return Check(
            name="policy",
            rule="G-03",
            result="pass",
            outcome="approve",
            detail=f"{party_id}'s bank details verified and consistent.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-03",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-04: Maker-checker (segregation of duties)
# -----------------------------------------------------------------------------
def g04_maker_checker(ctx: CheckContext) -> Check | None:
    try:
        proposer = ctx.proposer_id or ctx.get_agent()
        approver = ctx.approver_id
        bill_entered_by = ctx.bill_created_by or (ctx.bill.created_by if ctx.bill else None)

        audit: dict[str, Any] = {
            "proposer": proposer,
            "approver": approver,
            "bill_entered_by": bill_entered_by,
        }

        agent_names = {
            "treasurer",
            "controller",
            "cfo_strategist",
            "growth_analyst",
            "guardian",
            "guide",
        }

        if approver is not None:
            # An agent or Guardian cannot appear as approver
            if approver in agent_names or approver.lower() == "guardian":
                return Check(
                    name="policy",
                    rule="G-04",
                    result="fail",
                    outcome="block",
                    detail=f"Agent '{approver}' cannot approve actions (segregation of duties).",
                    audit=audit,
                )

            # Approver cannot be proposer
            if proposer and approver == proposer:
                return Check(
                    name="policy",
                    rule="G-04",
                    result="fail",
                    outcome="block",
                    detail=f"Approver '{approver}' cannot be the proposer '{proposer}' (maker-checker violation).",
                    audit=audit,
                )

            # Approver cannot be the user who entered the bill
            if bill_entered_by and approver == bill_entered_by:
                if ctx.single_person_business:
                    audit["single_person_business"] = True
                    return Check(
                        name="policy",
                        rule="G-04",
                        result="pass",
                        outcome="approve",
                        detail=f"Single-person business: owner '{approver}' entered and approved bill.",
                        audit=audit,
                    )
                return Check(
                    name="policy",
                    rule="G-04",
                    result="fail",
                    outcome="block",
                    detail=f"Approver '{approver}' entered the underlying bill (maker-checker violation).",
                    audit=audit,
                )

        return Check(
            name="policy",
            rule="G-04",
            result="pass",
            outcome="approve",
            detail="Maker-checker segregation of duties verified.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-04",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-05: Duplicate bill
# -----------------------------------------------------------------------------
def g05_duplicate_bill(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type not in ("bill_approval", "payment"):
        return None

    try:
        t_amt = get_threshold("T-G05-AMT")
        t_sim = get_threshold("T-G05-SIM")

        amt_tolerance_bp = int(t_amt["value_bp"])
        sim_threshold_bp = int(t_sim["value_bp"])

        bill = ctx.bill
        if bill is None:
            return Check(
                name="policy",
                rule="G-05",
                result="pass",
                outcome="approve",
                detail="No bill under review for duplicate check.",
            )

        bill_id = bill.bill_id or "current_bill"
        bill_num = bill.number or ""
        bill_hash = bill.document_sha256
        bill_total = bill.total_minor or ctx.get_amount_minor() or 0
        bill_supp = bill.supplier_id or ctx.get_payee_id()
        bill_grn = bill.grn_id

        norm_bill_num = normalise_bill_number(bill_num) if bill_num else ""

        # Test against every prior bill
        worst_check: Check | None = None

        for prior in ctx.prior_bills:
            prior_id = prior.bill_id or "prior_bill"
            prior_num = prior.number or ""
            prior_hash = prior.document_sha256
            prior_total = prior.total_minor or 0
            prior_supp = prior.supplier_id
            prior_grn = prior.grn_id

            # 1. Exact document hash duplicate
            if bill_hash and prior_hash and bill_hash == prior_hash:
                audit = {
                    "bill_id": bill_id,
                    "matched_bill_id": prior_id,
                    "match_signal": "same_document_hash",
                    "similarity_bp": 10000,
                    "amount_difference_bp": 0,
                    "hashes_equal": True,
                }
                return Check(
                    name="policy",
                    rule="G-05",
                    result="fail",
                    outcome="block",
                    detail=f"Bill document SHA-256 matches prior bill {prior_id}.",
                    audit=audit,
                )

            # Check supplier match
            same_supplier = (not bill_supp or not prior_supp) or (bill_supp == prior_supp)
            if not same_supplier:
                continue

            norm_prior_num = normalise_bill_number(prior_num) if prior_num else ""
            if not norm_bill_num or not norm_prior_num:
                continue

            # Rapidfuzz ratio on normalised number (0-100 float -> basis points 0-10000)
            similarity_bp = round(fuzz.ratio(norm_bill_num, norm_prior_num) * 100)

            # Amount difference in basis points
            diff = abs(bill_total - prior_total)
            base_amt = prior_total if prior_total > 0 else bill_total
            amount_diff_bp = round(diff * 10000 / base_amt) if base_amt > 0 else 0

            norm_equal = norm_bill_num == norm_prior_num

            audit = {
                "bill_id": bill_id,
                "matched_bill_id": prior_id,
                "similarity_bp": similarity_bp,
                "amount_difference_bp": amount_diff_bp,
                "hashes_equal": False,
            }

            # 2a. number_norm identical, amount diff <= T-G05-AMT -> block
            if norm_equal and amount_diff_bp <= amt_tolerance_bp:
                audit["match_signal"] = "normalised_number_equal"
                return Check(
                    name="policy",
                    rule="G-05",
                    result="fail",
                    outcome="block",
                    detail=f"Bill {bill_num} matches {prior_num} (normalised number equal, amount difference {amount_diff_bp} bp).",
                    audit=audit,
                )

            # 2b. number similarity >= T-G05-SIM, amount diff <= T-G05-AMT
            if similarity_bp >= sim_threshold_bp and amount_diff_bp <= amt_tolerance_bp:
                # distinct GRNs?
                if bill_grn and prior_grn and bill_grn != prior_grn:
                    audit["match_signal"] = "similar_number_distinct_grns"
                    chk = Check(
                        name="policy",
                        rule="G-05",
                        result="fail",
                        outcome="escalate",
                        detail=f"Bill {bill_num} similarity {similarity_bp} bp to {prior_num} with distinct GRNs.",
                        audit=audit,
                    )
                    if worst_check is None or worst_check.outcome == "approve":
                        worst_check = chk
                else:
                    audit["match_signal"] = "similar_number"
                    return Check(
                        name="policy",
                        rule="G-05",
                        result="fail",
                        outcome="block",
                        detail=f"Bill {bill_num} similarity {similarity_bp} bp to {prior_num} with amount difference {amount_diff_bp} bp.",
                        audit=audit,
                    )

            # 2c. number_norm identical, amount diff > T-G05-AMT -> escalate
            if norm_equal and amount_diff_bp > amt_tolerance_bp:
                audit["match_signal"] = "revised_bill_or_credit_note"
                chk = Check(
                    name="policy",
                    rule="G-05",
                    result="fail",
                    outcome="escalate",
                    detail=f"Bill {bill_num} matches {prior_num} but amount differs by {amount_diff_bp} bp (possible revision).",
                    audit=audit,
                )
                if worst_check is None or worst_check.outcome == "approve":
                    worst_check = chk

        if worst_check is not None:
            return worst_check

        return Check(
            name="policy",
            rule="G-05",
            result="pass",
            outcome="approve",
            detail=f"Bill {bill_num} has no duplicates in history.",
            audit={"bill_id": bill_id, "hashes_equal": False},
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-05",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-06: Three-way match
# -----------------------------------------------------------------------------
def g06_three_way_match(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type not in ("bill_approval", "payment"):
        return None

    try:
        t_tol = get_threshold("T-G06-TOL")
        tolerance_bp = int(t_tol["value_bp"])

        bill = ctx.bill
        category = bill.category if bill else ctx.get_category()

        # Check exempt categories
        if category in PO_EXEMPT_CATEGORIES:
            has_contract = bool(bill and bill.contract_ref)
            if has_contract:
                return Check(
                    name="policy",
                    rule="G-06",
                    result="pass",
                    outcome="approve",
                    detail=f"Category '{category}' is PO-exempt with contract ref '{bill.contract_ref}'.",
                    audit={
                        "category": category,
                        "contract_ref": bill.contract_ref,
                        "po_exempt": True,
                    },
                )
            return Check(
                name="policy",
                rule="G-06",
                result="fail",
                outcome="escalate",
                detail=f"Category '{category}' is PO-exempt but missing contract or recurring reference.",
                audit={
                    "category": category,
                    "missing_documents": ["contract_reference"],
                    "po_exempt": True,
                },
            )

        po = ctx.po
        grn = ctx.grn
        po_id = po.id if po else (bill.po_id if bill else None)
        grn_id = grn.id if grn else (bill.grn_id if bill else None)

        missing_docs = []
        if po is None:
            missing_docs.append("purchase_order")
        if grn is None:
            missing_docs.append("goods_received")

        if missing_docs:
            return Check(
                name="policy",
                rule="G-06",
                result="fail",
                outcome="escalate",
                detail=f"Three-way match failed: missing {', '.join(missing_docs)}.",
                audit={
                    "po_id": po_id,
                    "grn_id": grn_id,
                    "missing_documents": missing_docs,
                    "worst_line_variance_bp": None,
                },
            )

        # Check line variance
        worst_variance_bp = 0
        bill_lines = bill.lines if bill else []
        grn_lines = grn.lines if grn else []
        po_lines = po.lines if po else []

        for b_line in bill_lines:
            b_qty = b_line.qty or 0
            b_price = b_line.unit_price_minor or 0
            sku = b_line.sku or b_line.item

            # Match GRN line
            g_line = next((g for g in grn_lines if (g.sku or g.item) == sku), None)
            g_qty = (g_line.qty_received or g_line.qty or 0) if g_line else 0

            # Match PO line
            p_line = next((p for p in po_lines if (p.sku or p.item) == sku), None)
            p_cost = (p_line.unit_cost_minor or p_line.unit_price_minor or 0) if p_line else b_price

            # Quantity variance (qty billed vs qty received)
            if g_qty > 0:
                qty_var_bp = round(abs(b_qty - g_qty) * 10000 / g_qty)
            else:
                qty_var_bp = 10000 if b_qty > 0 else 0

            # Price variance (price billed vs price ordered)
            price_var_bp = round(abs(b_price - p_cost) * 10000 / p_cost) if p_cost > 0 else 0

            worst_variance_bp = max(worst_variance_bp, qty_var_bp, price_var_bp)

        audit = {
            "po_id": po_id,
            "grn_id": grn_id,
            "worst_line_variance_bp": worst_variance_bp,
            "missing_documents": [],
        }

        if worst_variance_bp > tolerance_bp:
            return Check(
                name="policy",
                rule="G-06",
                result="fail",
                outcome="escalate",
                detail=f"Three-way match variance of {worst_variance_bp} bp exceeds tolerance of {tolerance_bp} bp.",
                audit=audit,
            )

        return Check(
            name="policy",
            rule="G-06",
            result="pass",
            outcome="approve",
            detail=f"Three-way match verified (worst variance {worst_variance_bp} bp <= {tolerance_bp} bp).",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-06",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-07: Arithmetic & debits/credits
# -----------------------------------------------------------------------------
def g07_arithmetic(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type not in (
        "bill_approval",
        "payment",
        "journal_adjustment",
        "send_document",
    ):
        return None

    try:
        t_arith = get_threshold("T-G07-ARITH")
        tolerance_minor = int(t_arith["value_minor"])

        # 1. Journal entries
        if action_type == "journal_adjustment" or ctx.journal_lines:
            debits = sum(line.debit_minor for line in ctx.journal_lines)
            credits = sum(line.credit_minor for line in ctx.journal_lines)
            diff = abs(debits - credits)

            for line in ctx.journal_lines:
                if (line.debit_minor > 0 and line.credit_minor > 0) or (
                    line.debit_minor == 0 and line.credit_minor == 0
                ):
                    return Check(
                        name="arithmetic",
                        rule="G-07",
                        result="fail",
                        outcome="block",
                        detail=f"Journal line '{line.account}' must have exactly one of debit or credit positive.",
                        audit={
                            "debits_minor": debits,
                            "credits_minor": credits,
                            "difference_minor": diff,
                        },
                    )

            if diff > 0:
                return Check(
                    name="arithmetic",
                    rule="G-07",
                    result="fail",
                    outcome="block",
                    detail=f"Journal debits {debits} do not balance credits {credits} (difference {diff}).",
                    audit={
                        "debits_minor": debits,
                        "credits_minor": credits,
                        "difference_minor": diff,
                    },
                )

            return Check(
                name="arithmetic",
                rule="G-07",
                result="pass",
                outcome="approve",
                detail=f"Journal entries balanced: debits {debits} == credits {credits}.",
                audit={
                    "debits_minor": debits,
                    "credits_minor": credits,
                    "difference_minor": 0,
                },
            )

        # 2. Bills and invoices
        bill = ctx.bill
        if bill is not None:
            subtotal = bill.subtotal_minor
            total = bill.total_minor
            stated_tax = bill.stated_tax_minor
            tax_rate_bp = bill.tax_rate_bp

            recomputed_subtotal = subtotal
            recomputed_tax = stated_tax
            recomputed_total = total

            # Check lines add up to subtotal
            if bill.lines and subtotal is not None:
                lines_total = sum(
                    line_item.total_minor
                    if line_item.total_minor is not None
                    else (
                        (line_item.qty or 0)
                        * (line_item.unit_price_minor or line_item.unit_cost_minor or 0)
                        - line_item.discount_minor
                    )
                    for line_item in bill.lines
                )
                if abs(lines_total - subtotal) > tolerance_minor:
                    return Check(
                        name="arithmetic",
                        rule="G-07",
                        result="fail",
                        outcome="block",
                        detail=f"Line items total {lines_total} does not match subtotal {subtotal}.",
                        audit={
                            "recomputed_subtotal": lines_total,
                            "stated_subtotal": subtotal,
                            "difference_minor": abs(lines_total - subtotal),
                        },
                    )
                recomputed_subtotal = lines_total

            # Recompute tax
            if bill.tax_lines:
                computed_tax_sum = 0
                for tl in bill.tax_lines:
                    base = tl.base_minor if tl.base_minor is not None else (subtotal or 0)
                    rate = tl.rate_bp or 0
                    # Round half-up: (base * rate + 5000) // 10000
                    exp_tax = (base * rate + 5000) // 10000
                    computed_tax_sum += exp_tax
                    if (
                        tl.amount_minor is not None
                        and abs(tl.amount_minor - exp_tax) > tolerance_minor
                    ):
                        return Check(
                            name="arithmetic",
                            rule="G-07",
                            result="fail",
                            outcome="block",
                            detail=f"Stated tax {tl.amount_minor} differs from computed tax {exp_tax}.",
                            audit={
                                "recomputed_tax": exp_tax,
                                "stated_tax": tl.amount_minor,
                                "difference_minor": abs(tl.amount_minor - exp_tax),
                            },
                        )
                recomputed_tax = computed_tax_sum
            elif subtotal is not None and tax_rate_bp is not None:
                exp_tax = (subtotal * tax_rate_bp + 5000) // 10000
                recomputed_tax = exp_tax
                if stated_tax is not None and abs(stated_tax - exp_tax) > tolerance_minor:
                    return Check(
                        name="arithmetic",
                        rule="G-07",
                        result="fail",
                        outcome="block",
                        detail=f"Stated tax {stated_tax} differs from computed tax {exp_tax}.",
                        audit={
                            "recomputed_tax": exp_tax,
                            "stated_tax": stated_tax,
                            "difference_minor": abs(stated_tax - exp_tax),
                        },
                    )

            # Subtotal + tax == total check
            if subtotal is not None and total is not None:
                effective_tax = stated_tax if stated_tax is not None else (recomputed_tax or 0)
                expected_total = subtotal + effective_tax
                recomputed_total = expected_total
                if abs(expected_total - total) > tolerance_minor:
                    return Check(
                        name="arithmetic",
                        rule="G-07",
                        result="fail",
                        outcome="block",
                        detail=f"Subtotal {subtotal} + tax {effective_tax} does not equal total {total}.",
                        audit={
                            "recomputed_total": expected_total,
                            "stated_total": total,
                            "difference_minor": abs(expected_total - total),
                        },
                    )

            # 3. Payments: payment amount vs outstanding balance
            if action_type == "payment":
                amount_minor = ctx.get_amount_minor()
                if (
                    bill.outstanding_balance_minor is not None
                    and amount_minor is not None
                    and not bill.is_partial_payment
                    and abs(amount_minor - bill.outstanding_balance_minor) > tolerance_minor
                ):
                    return Check(
                        name="arithmetic",
                        rule="G-07",
                        result="fail",
                        outcome="block",
                        detail=f"Payment {amount_minor} does not match bill balance {bill.outstanding_balance_minor}.",
                        audit={
                            "amount_minor": amount_minor,
                            "balance_minor": bill.outstanding_balance_minor,
                            "difference_minor": abs(amount_minor - bill.outstanding_balance_minor),
                        },
                    )

            return Check(
                name="arithmetic",
                rule="G-07",
                result="pass",
                outcome="approve",
                detail="Arithmetic verified: lines, taxes, and totals match within tolerance.",
                audit={
                    "recomputed_subtotal": recomputed_subtotal,
                    "recomputed_tax": recomputed_tax,
                    "recomputed_total": recomputed_total,
                    "stated_total": total,
                    "difference_minor": 0,
                },
            )

        return Check(
            name="arithmetic",
            rule="G-07",
            result="pass",
            outcome="approve",
            detail="No arithmetic document to verify; passed.",
            audit={"difference_minor": 0},
        )
    except Exception as e:
        return Check(
            name="arithmetic",
            rule="G-07",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-08: Cash buffer / incremental forecast
# -----------------------------------------------------------------------------
def _get_week_for_date(d_str: str, week_starts: list[datetime]) -> int:
    """Return 1-indexed week number for a YYYY-MM-DD string."""
    d = datetime.fromisoformat(d_str[:10]).replace(tzinfo=UTC)
    if d < week_starts[0]:
        return 1  # a payment before the horizon affects every week
    for i in range(len(week_starts) - 1):
        if week_starts[i] <= d < week_starts[i + 1]:
            return i + 1
    if d < week_starts[-1] + timedelta(days=7):
        return len(week_starts)
    return len(week_starts) + 1  # after the horizon: no forecast week changes


def g08_cash_buffer(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type != "payment":
        return None

    try:
        if ctx.forecast is None or not ctx.forecast.weeks:
            return Check(
                name="policy",
                rule="G-08",
                result="fail",
                outcome="escalate",
                detail="CHECK_ERROR: 13-week forecast baseline missing.",
            )

        weeks = ctx.forecast.weeks
        buffer_minor = ctx.buffer_minor
        amount = ctx.get_amount_minor() or 0
        pay_on = ctx.get_pay_on()
        due_date = str(ctx.bill.due_date)[:10] if (ctx.bill and ctx.bill.due_date) else None
        in_baseline_week = ctx.bill.in_baseline_week if ctx.bill else None

        week_starts = [datetime.fromisoformat(w.start[:10]).replace(tzinfo=UTC) for w in weeks]

        if pay_on is None:
            pay_on = ctx.get_now_dt().strftime("%Y-%m-%d")

        w_proposed = _get_week_for_date(pay_on, week_starts)
        w_due = _get_week_for_date(due_date, week_starts) if due_date else None

        # Determine baseline week
        w_baseline = in_baseline_week
        if w_baseline is None and due_date and (ctx.bill and in_baseline_week is not False):
            # If bill has due date and not explicitly marked unplanned, it defaults to due date week
            w_baseline = w_due

        base = [w.closing_minor for w in weeks]

        def _calc_scen(w_pay: int) -> list[int]:
            scen = list(base)
            for idx in range(len(scen)):
                w_num = idx + 1
                if w_baseline is not None and w_num >= w_baseline:
                    scen[idx] += amount
                if w_num >= w_pay:
                    scen[idx] -= amount
            return scen

        def _has_violation(scen: list[int]) -> bool:
            return any(scen[i] < buffer_minor and scen[i] < base[i] for i in range(len(scen)))

        # Incremental test on proposed date
        scen_proposed = _calc_scen(w_proposed)
        violation = _has_violation(scen_proposed)

        min_base = min(base)
        min_scen = min(scen_proposed)
        week_of_min = scen_proposed.index(min_scen) + 1

        audit: dict[str, Any] = {
            "forecast_run_id": ctx.forecast.id or "fc_baseline",
            "forecast_as_of": str(ctx.forecast.as_of) if ctx.forecast.as_of else None,
            "buffer_minor": buffer_minor,
            "min_scen_minor": min_scen,
            "min_base_minor": min_base,
            "week_of_min": week_of_min,
            "safe_date": None,
        }

        # 1. No violation
        if not violation:
            pre_existing_dips = [w.w for w in weeks if w.closing_minor < buffer_minor]
            detail = f"Payment of {amount} leaves cash above buffer."
            if pre_existing_dips:
                detail += f" (pre-existing dip in week {pre_existing_dips[0]}, not caused by this payment)."
            return Check(
                name="policy",
                rule="G-08",
                result="pass",
                outcome="approve",
                detail=detail,
                audit=audit,
            )

        # 2. Violation at proposed date: Search dates from pay_on to latest permitted date, latest first
        w_max = w_due if w_due is not None else len(weeks)

        # Search week-by-week descending from w_max down to w_proposed
        safe_week: int | None = None
        safe_date: str | None = None

        for w_cand in range(w_max, w_proposed - 1, -1):
            cand_scen = _calc_scen(w_cand)
            if not _has_violation(cand_scen):
                safe_week = w_cand
                if safe_week == w_due and due_date:
                    safe_date = due_date
                else:
                    # Latest date of the safe week (rule: latest safe date first).
                    week_end = week_starts[safe_week - 1] + timedelta(days=6)
                    safe_date = week_end.strftime("%Y-%m-%d")
                break

        category = ctx.get_category() or (ctx.bill.category if ctx.bill else None)
        if safe_date is not None and category not in STATUTORY_CATEGORIES:
            audit["safe_date"] = safe_date
            return Check(
                name="policy",
                rule="G-08",
                result="fail",
                outcome="approve_with_conditions",
                detail=f"Payment on {pay_on} breaches cash buffer; approved with condition to pay on {safe_date}.",
                condition=PayOnCondition(kind="pay_on", date=safe_date),
                audit=audit,
            )

        # 3. No safe date exists
        return Check(
            name="policy",
            rule="G-08",
            result="fail",
            outcome="escalate",
            detail=f"Payment of {amount} takes cash below the buffer ({buffer_minor}) on every permitted date within the horizon.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-08",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-09: Claim has no evidence reference
# -----------------------------------------------------------------------------
def g09_evidence_check(ctx: CheckContext) -> Check | None:
    try:
        action_type = ctx.get_action_type()
        evidence_list = ctx.get_evidence()
        _ = ctx.get_reasoning()

        required_kinds_map = {
            "payment": ["ledger_row", "document"],
            "bill_approval": ["document", "purchase_order", "goods_received"],
            "journal_adjustment": ["source_event", "document"],
            "send_document": ["document", "source_event"],
            "purchase_order": ["inventory_analysis", "owner_request"],
            "reconciliation_match": ["bank_line", "event"],
        }

        # Check PO-exempt for bill_approval
        if (
            action_type == "bill_approval"
            and ctx.bill
            and ctx.bill.category in PO_EXEMPT_CATEGORIES
        ):
            required_kinds = ["document", "contract"]
        else:
            required_kinds = required_kinds_map.get(action_type, ["ledger_row", "document"])

        present_kinds = {e.get("kind") for e in evidence_list if isinstance(e, dict)}
        ledger_kinds = {"ledger_row", "ledger_event", "bill"}

        missing_kinds = []
        if action_type == "payment":
            if not (ledger_kinds & present_kinds):
                missing_kinds.append("ledger_row")
            if "document" not in present_kinds:
                missing_kinds.append("document")
        elif action_type == "bill_approval":
            if "document" not in present_kinds:
                missing_kinds.append("document")
            if not ({"purchase_order", "contract"} & present_kinds):
                missing_kinds.append("purchase_order_or_contract")
            if (
                ctx.bill
                and ctx.bill.category not in PO_EXEMPT_CATEGORIES
                and "goods_received" not in present_kinds
            ):
                missing_kinds.append("goods_received")

        if ctx.evidence_index is None:
            return Check(
                name="evidence",
                rule="G-09",
                result="fail",
                outcome="escalate",
                detail="CHECK_ERROR: no evidence resolver was supplied, so references cannot be verified.",
            )

        unresolved_refs: list[str] = []
        contradictions: list[str] = []
        payee = ctx.get_payee_id()
        amount = ctx.get_amount_minor()
        cited_amounts: set[int] = set()
        for e in evidence_list:
            if not isinstance(e, dict):
                continue
            ref = str(e.get("ref", ""))
            record = ctx.evidence_index.get(ref)
            if record is None:
                unresolved_refs.append(ref)
                continue
            party = record.get("party_id")
            if payee and party and party != payee:
                contradictions.append(f"{ref} belongs to {party}, the payload says {payee}")
            rec_amount = record.get("amount_minor")
            if rec_amount is not None:
                cited_amounts.add(int(rec_amount))
                if (
                    action_type == "payment"
                    and e.get("kind") in ledger_kinds
                    and amount is not None
                    and int(rec_amount) != amount
                ):
                    contradictions.append(f"{ref} is for {rec_amount}, the proposal pays {amount}")

        # Figures quoted in the reasoning must match a cited value (free text is read conservatively).
        unmatched_values: list[int] = []
        for match in re.finditer(r"PKR\s*([0-9][0-9,]*)(?:\.([0-9]{1,2}))?", ctx.get_reasoning()):
            major = int(match.group(1).replace(",", ""))
            cents = int((match.group(2) or "0").ljust(2, "0"))
            value = major * 100 + cents
            if value not in cited_amounts and value != amount:
                unmatched_values.append(value)

        audit: dict[str, Any] = {
            "required_kinds": required_kinds,
            "missing_kinds": missing_kinds,
            "unresolved_refs": unresolved_refs,
            "contradictions": contradictions,
            "unmatched_reasoning_values": unmatched_values,
        }

        if missing_kinds or unresolved_refs or contradictions:
            reasons = []
            if missing_kinds:
                reasons.append(f"missing evidence {', '.join(missing_kinds)}")
            if unresolved_refs:
                reasons.append(f"evidence reference {', '.join(unresolved_refs)} does not resolve")
            if contradictions:
                reasons.append(f"contradictions: {', '.join(contradictions)}")
            return Check(
                name="evidence",
                rule="G-09",
                result="fail",
                outcome="block",
                detail=f"Evidence verification failed: {'; '.join(reasons)}.",
                audit=audit,
            )

        if unmatched_values:
            return Check(
                name="evidence",
                rule="G-09",
                result="fail",
                outcome="escalate",
                detail=f"The reasoning quotes {', '.join(map(str, unmatched_values))} minor, which no cited record supports.",
                audit=audit,
            )

        return Check(
            name="evidence",
            rule="G-09",
            result="pass",
            outcome="approve",
            detail="Required evidence present and verified.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="evidence",
            rule="G-09",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-10: Daily cap
# -----------------------------------------------------------------------------
def g10_daily_cap(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type != "payment":
        return None

    try:
        amount_minor = ctx.get_amount_minor() or 0
        paid_today_minor = ctx.paid_today_minor

        daily_cap_minor = getattr(ctx.mandate, "daily_cap_minor", None)
        if daily_cap_minor is None and isinstance(ctx.mandate, dict):
            daily_cap_minor = ctx.mandate.get("daily_cap_minor")
        if daily_cap_minor is None:
            return Check(
                name="policy",
                rule="G-10",
                result="fail",
                outcome="escalate",
                detail="CHECK_ERROR: Mandate daily_cap_minor missing.",
            )

        total_today = paid_today_minor + amount_minor
        business_date = ctx.get_now_dt().strftime("%Y-%m-%d")

        audit: dict[str, Any] = {
            "payments_today_minor": total_today,
            "daily_cap_minor": daily_cap_minor,
            "business_date": business_date,
        }

        if total_today > daily_cap_minor:
            return Check(
                name="policy",
                rule="G-10",
                result="fail",
                outcome="escalate",
                detail=f"Payments today ({total_today}) including this payment exceed daily cap of {daily_cap_minor}.",
                audit=audit,
            )

        return Check(
            name="policy",
            rule="G-10",
            result="pass",
            outcome="approve",
            detail=f"Payments today ({total_today}) are within daily cap of {daily_cap_minor}.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-10",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-11: Supplier tax registration missing or malformed
# -----------------------------------------------------------------------------
def g11_supplier_tax_id(ctx: CheckContext) -> Check | None:
    action_type = ctx.get_action_type()
    if action_type not in ("bill_approval", "payment"):
        return None

    try:
        party = ctx.payee
        tax_id = party.tax_id if party else None
        tax_id_type = (party.tax_id_type if party else None) or "NTN"
        if party and party.country_pack_pattern:
            pattern = party.country_pack_pattern
        elif ctx.country:
            pattern = tax_id_pattern(ctx.country, tax_id_type)
        else:
            raise ValueError("tenant country unknown, so no tax-ID pattern can be loaded")

        bill_tax_id = ctx.bill.supplier_tax_id if ctx.bill else None

        audit: dict[str, Any] = {
            "tax_id_on_file_masked": _mask_tax_id(tax_id),
            "tax_id_on_bill_masked": _mask_tax_id(bill_tax_id),
            "pattern_id": tax_id_type,
        }

        # 1. Missing tax ID
        if not tax_id:
            return Check(
                name="policy",
                rule="G-11",
                result="fail",
                outcome="escalate",
                detail="Supplier tax registration ID is missing.",
                audit=audit,
            )

        # 2. Malformed pattern
        if not re.match(pattern, tax_id):
            return Check(
                name="policy",
                rule="G-11",
                result="fail",
                outcome="escalate",
                detail=f"Supplier tax ID '{tax_id}' does not match {tax_id_type} format pattern '{pattern}'.",
                audit=audit,
            )

        # 3. Discrepancy between bill and file
        if bill_tax_id and bill_tax_id != tax_id:
            return Check(
                name="policy",
                rule="G-11",
                result="fail",
                outcome="escalate",
                detail=f"Tax ID on bill '{bill_tax_id}' differs from on-file tax ID '{tax_id}'.",
                audit=audit,
            )

        return Check(
            name="policy",
            rule="G-11",
            result="pass",
            outcome="approve",
            detail=f"Supplier tax registration '{tax_id}' verified.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-11",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-13: Action type or category outside agent's mandate (Final, Tier 1)
# -----------------------------------------------------------------------------
def g13_mandate_permission(ctx: CheckContext) -> Check | None:
    try:
        agent = ctx.get_agent()
        action_type = ctx.get_action_type()
        category = ctx.get_category() or (ctx.bill.category if ctx.bill else None)

        mandate_id = getattr(ctx.mandate, "id", None) or (
            ctx.mandate.get("id") if isinstance(ctx.mandate, dict) else None
        )
        mandate_ver = getattr(ctx.mandate, "version", 1) or (
            ctx.mandate.get("version", 1) if isinstance(ctx.mandate, dict) else 1
        )

        audit: dict[str, Any] = {
            "agent": agent,
            "type": action_type,
            "category": category,
            "mandate_id": mandate_id,
            "mandate_version": mandate_ver,
        }

        # Material decision types can never be executed by agents -> block
        if action_type in MATERIAL_DECISION_TYPES:
            return Check(
                name="policy",
                rule="G-13",
                result="fail",
                outcome="block",
                detail=f"Action type '{action_type}' is a material decision never executable by agents.",
                audit=audit,
            )

        if ctx.mandate is None:
            return Check(
                name="policy",
                rule="G-13",
                result="fail",
                outcome="block",
                detail=f"{agent} has no mandate, so no action type is permitted.",
                audit=audit,
            )
        mandate_agent = getattr(ctx.mandate, "agent", None)
        if mandate_agent is None and isinstance(ctx.mandate, dict):
            mandate_agent = ctx.mandate.get("agent")
        mandate_agent = getattr(mandate_agent, "value", mandate_agent)
        if mandate_agent is not None and str(mandate_agent) != agent:
            return Check(
                name="policy",
                rule="G-13",
                result="fail",
                outcome="block",
                detail=f"Mandate belongs to {mandate_agent}, not to the proposing agent {agent}.",
                audit=audit,
            )
        if True:
            # Check allowed action types
            allowed_types = getattr(ctx.mandate, "allowed_action_types", None)
            if allowed_types is None and isinstance(ctx.mandate, dict):
                allowed_types = ctx.mandate.get("allowed_action_types")
                if allowed_types is None and "autonomy" in ctx.mandate:
                    allowed_types = list(ctx.mandate["autonomy"].keys())
            elif allowed_types is None and hasattr(ctx.mandate, "autonomy"):
                allowed_types = list(ctx.mandate.autonomy.keys())

            if allowed_types is not None and action_type not in allowed_types:
                return Check(
                    name="policy",
                    rule="G-13",
                    result="fail",
                    outcome="block",
                    detail=f"Action type '{action_type}' is outside {agent}'s mandate allowed action types.",
                    audit=audit,
                )

            # Check allowed categories
            allowed_categories = getattr(ctx.mandate, "allowed_categories", None)
            if allowed_categories is None and isinstance(ctx.mandate, dict):
                allowed_categories = ctx.mandate.get("allowed_categories")
            if allowed_categories is not None and category:
                allowed_cat_names = [
                    c.root if hasattr(c, "root") else str(c) for c in allowed_categories
                ]
                if category not in allowed_cat_names:
                    return Check(
                        name="policy",
                        rule="G-13",
                        result="fail",
                        outcome="escalate",
                        detail=f"Payment category '{category}' is outside {agent}'s allowed categories.",
                        audit=audit,
                    )

            # Check payment windows
            windows = getattr(ctx.mandate, "payment_windows", None)
            if windows is None and isinstance(ctx.mandate, dict):
                windows = ctx.mandate.get("payment_windows")
            if windows is not None:
                requested = ctx.get_pay_on() or ctx.get_now_dt().strftime("%Y-%m-%d")
                requested_day = datetime.fromisoformat(requested[:10])
                day_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][
                    requested_day.weekday()
                ]
                allowed_days = (
                    getattr(windows, "days", None)
                    if not isinstance(windows, dict)
                    else windows.get("days")
                )
                if allowed_days and day_abbr not in allowed_days:
                    return Check(
                        name="policy",
                        rule="G-13",
                        result="fail",
                        outcome="escalate",
                        detail=f"Execution day '{day_abbr}' is outside {agent}'s payment window days.",
                        audit=audit,
                    )

        return Check(
            name="policy",
            rule="G-13",
            result="pass",
            outcome="approve",
            detail=f"Action '{action_type}' is within {agent}'s mandate permissions.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-13",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-14: Inputs missing, stale or inconsistent (Proposed, Tier 2)
# -----------------------------------------------------------------------------
def g14_stale_inputs(ctx: CheckContext) -> Check | None:
    if not ctx.enable_proposed:
        return None

    action_type = ctx.get_action_type()
    if action_type not in ("payment", "bill_approval"):
        return None

    try:
        t_stale = get_threshold("T-G14-STALE")
        limits = t_stale["values"]
        max_fc_hours = int(limits.get("forecast_run_hours", 24))

        now_dt = ctx.get_now_dt()
        fc_age_hours = 0
        if ctx.forecast and ctx.forecast.as_of:
            as_of_str = str(ctx.forecast.as_of)
            s = as_of_str[:-1] + "+00:00" if as_of_str.endswith("Z") else as_of_str
            fc_dt = datetime.fromisoformat(s)
            if fc_dt.tzinfo is None:
                fc_dt = fc_dt.replace(tzinfo=UTC)
            fc_age_hours = max(0, int((now_dt - fc_dt).total_seconds() / 3600))

        audit = {
            "forecast_age_hours": fc_age_hours,
            "balance_age_hours": 0,
            "low_confidence_fields": [],
            "conflicts": [],
        }

        if fc_age_hours > max_fc_hours:
            return Check(
                name="evidence",
                rule="G-14",
                result="fail",
                outcome="escalate",
                detail=f"Forecast baseline age ({fc_age_hours}h) exceeds freshness limit ({max_fc_hours}h).",
                audit=audit,
            )

        return Check(
            name="evidence",
            rule="G-14",
            result="pass",
            outcome="approve",
            detail="Inputs are fresh and consistent.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="evidence",
            rule="G-14",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )


# -----------------------------------------------------------------------------
# G-15: Payee account linked to insider (Proposed, Tier 2)
# -----------------------------------------------------------------------------
def g15_insider_payee(ctx: CheckContext) -> Check | None:
    if not ctx.enable_proposed:
        return None

    action_type = ctx.get_action_type()
    if action_type != "payment":
        return None

    try:
        is_insider = bool(ctx.payee and ctx.payee.insider_account_matches)
        audit = {"matched_party_kind": "insider_employee" if is_insider else None}

        if is_insider:
            return Check(
                name="policy",
                rule="G-15",
                result="fail",
                outcome="escalate",
                detail="Payee destination account matches an internal employee or insider account.",
                audit=audit,
            )

        return Check(
            name="policy",
            rule="G-15",
            result="pass",
            outcome="approve",
            detail="Payee account is not linked to any insider.",
            audit=audit,
        )
    except Exception as e:
        return Check(
            name="policy",
            rule="G-15",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {e}",
        )
