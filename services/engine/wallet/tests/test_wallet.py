"""D6 done-when: the wallet refuses every unsafe payment, pays a cleared one exactly once, and audits
every attempt in a chain that verifies."""

from __future__ import annotations

import itertools

import psycopg
import pytest

from engine.ledger import db
from engine.wallet.audit import verify
from engine.wallet.tests.conftest import (
    CAP,
    DAILY_CAP,
    NOW,
    OPENING_BALANCE,
    TODAY,
    seed_wallet_tenant,
    store_decision,
    store_proposal,
    store_verdict,
)
from engine.wallet.wallet import PaymentRequest, execute_payment

_tenants = itertools.count(1)


def new_tenant(conn: psycopg.Connection, balance: int = OPENING_BALANCE) -> str:
    tenant = f"ten_wallet_{next(_tenants)}"
    seed_wallet_tenant(conn, tenant, opening_balance_minor=balance)
    return tenant


def request(
    proposal_id: str, verdict_id: str, *, amount: int, payee: str = "sup_001", pay_on: str = TODAY
) -> PaymentRequest:
    return PaymentRequest(
        proposal_id=proposal_id,
        verdict_id=verdict_id,
        payee_id=payee,
        amount_minor=amount,
        currency="PKR",
        pay_on=pay_on,
    )


def balance(conn: psycopg.Connection, tenant: str) -> int:
    with db.tenant_session(conn, tenant):
        return conn.execute("select balance_minor from wallet_accounts").fetchone()[0]


def audit_actions(conn: psycopg.Connection, tenant: str) -> list[str]:
    with db.tenant_session(conn, tenant):
        return [r[0] for r in conn.execute("select record->>'action' from audit_log order by seq")]


def test_cleared_payment_executes_once_and_is_audited(conn: psycopg.Connection) -> None:
    tenant = new_tenant(conn)
    store_proposal(conn, tenant, "prop_ok", amount=9_500_000)
    verdict = store_verdict(conn, tenant, "prop_ok", "approve")
    first = execute_payment(conn, tenant, request("prop_ok", verdict, amount=9_500_000), now=NOW)
    assert first.status == "executed" and first.label == "SIMULATED"
    assert balance(conn, tenant) == OPENING_BALANCE - 9_500_000
    retry = execute_payment(conn, tenant, request("prop_ok", verdict, amount=9_500_000), now=NOW)
    assert retry.status == "already_executed" and retry.payment_id == first.payment_id
    assert balance(conn, tenant) == OPENING_BALANCE - 9_500_000  # never paid twice
    with db.tenant_session(conn, tenant):
        event = conn.execute(
            "select payload from events where type = 'supplier_payment'"
        ).fetchone()[0]
        assert verify(conn, tenant).ok
    assert event["to_iban"] == "PK00SYNB0000000000000001" and event["method"] == "wallet"
    assert audit_actions(conn, tenant) == ["payment_executed"]


def test_escalated_payment_needs_an_owner_who_is_not_the_proposer(conn: psycopg.Connection) -> None:
    tenant = new_tenant(conn)
    store_proposal(conn, tenant, "prop_esc", amount=CAP + 13_036_800, created_by="usr_finance_01")
    verdict = store_verdict(conn, tenant, "prop_esc", "escalate")
    req = request("prop_esc", verdict, amount=CAP + 13_036_800)
    assert execute_payment(conn, tenant, req, now=NOW).reason.startswith("NEEDS_OWNER")
    store_decision(conn, tenant, "prop_esc", verdict, decided_by="usr_finance_01")
    assert execute_payment(conn, tenant, req, now=NOW).reason.startswith("SAME_ACTOR")
    store_decision(
        conn, tenant, "prop_esc", verdict, decided_by="usr_owner", decided_at="2026-10-22T09:05:00Z"
    )
    assert (
        execute_payment(conn, tenant, req, now=NOW).status == "executed"
    )  # owner releases the cap escalation


def test_conditions_are_checked_at_execution(conn: psycopg.Connection) -> None:
    tenant = new_tenant(conn)
    store_proposal(conn, tenant, "prop_cond", amount=9_000_000)
    verdict = store_verdict(
        conn,
        tenant,
        "prop_cond",
        "approve_with_conditions",
        conditions=[{"kind": "pay_on", "date": "2026-12-08"}],
    )
    result = execute_payment(conn, tenant, request("prop_cond", verdict, amount=9_000_000), now=NOW)
    assert result.reason.startswith("CONDITION_NOT_MET")


def _setup_and_request(conn: psycopg.Connection, case: str) -> tuple[str, PaymentRequest]:
    tenant = new_tenant(
        conn, balance=5_000_000 if case == "insufficient_funds" else OPENING_BALANCE
    )
    amount, payee = 9_000_000, "sup_001"
    if case == "over_cap":
        amount = CAP + 1
    if case in ("not_allow_listed", "bank_change_email"):
        payee = {"not_allow_listed": "sup_018", "bank_change_email": "sup_017"}[case]
    store_proposal(conn, tenant, "prop_x", amount=amount, payee=payee)
    outcome = {"blocked": "block", "escalated_without_owner": "escalate"}.get(case, "approve")
    verdict = store_verdict(conn, tenant, "prop_x", outcome)
    req = request("prop_x", verdict, amount=amount, payee=payee)
    if case == "no_verdict":
        req = request("prop_x", "vrd_missing", amount=amount)
    if case == "no_proposal":
        req = request("prop_missing", verdict, amount=amount)
    if case == "wrong_proposal":
        store_proposal(conn, tenant, "prop_other", amount=amount)
        req = request("prop_other", verdict, amount=amount)
    if case == "tampered_verdict":
        # An attacker with database access edits the stored verdict (bypassing the append-only trigger).
        conn.execute("alter table verdicts disable trigger verdicts_append_only")
        conn.execute(
            "update verdicts set body = jsonb_set(body, '{checks,0,detail}', '\"edited\"')"
            " where tenant_id = %s",
            (tenant,),
        )
        conn.execute("alter table verdicts enable trigger verdicts_append_only")
    if case == "stale_verdict":
        store_verdict(conn, tenant, "prop_x", "approve", verdict_id="vrd_x2", previous=verdict)
    if case == "amount_mismatch":
        req = request("prop_x", verdict, amount=amount - 1)
    if case == "payee_mismatch":
        req = request("prop_x", verdict, amount=amount, payee="sup_003")
    if case == "wrong_date":
        store_proposal(conn, tenant, "prop_late", amount=amount, pay_on="2026-10-23")
        late = store_verdict(conn, tenant, "prop_late", "approve")
        req = request("prop_late", late, amount=amount, pay_on="2026-10-23")
    if case == "over_daily_cap":
        for n, part in enumerate((CAP, CAP, DAILY_CAP - 2 * CAP)):
            store_proposal(conn, tenant, f"prop_day{n}", amount=part)
            v = store_verdict(conn, tenant, f"prop_day{n}", "approve")
            assert (
                execute_payment(
                    conn, tenant, request(f"prop_day{n}", v, amount=part), now=NOW
                ).status
                == "executed"
            )
    return tenant, req


REFUSALS: dict[str, str] = {
    "no_proposal": "NO_PROPOSAL",
    "no_verdict": "NO_VERDICT",
    "wrong_proposal": "WRONG_PROPOSAL",
    "tampered_verdict": "TAMPERED_VERDICT",
    "stale_verdict": "STALE_VERDICT",
    "blocked": "VERDICT_BLOCKED",
    "escalated_without_owner": "NEEDS_OWNER",
    "amount_mismatch": "REQUEST_MISMATCH",
    "payee_mismatch": "REQUEST_MISMATCH",
    "wrong_date": "WRONG_DATE",
    "over_cap": "OVER_CAP",
    "over_daily_cap": "OVER_DAILY_CAP",
    "not_allow_listed": "NOT_ALLOW_LISTED",
    "bank_change_email": "BANK_CHANGE_UNCONFIRMED",
    "insufficient_funds": "INSUFFICIENT_FUNDS",
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_wallet_refuses(conn: psycopg.Connection, case: str) -> None:
    tenant, req = _setup_and_request(conn, case)
    before = balance(conn, tenant)
    result = execute_payment(conn, tenant, req, now=NOW)
    assert result.status == "refused"
    assert result.reason.startswith(REFUSALS[case]), result.reason
    assert balance(conn, tenant) == before
    assert audit_actions(conn, tenant)[-1] == "payment_refused"
    with db.tenant_session(conn, tenant):
        assert verify(conn, tenant).ok


def test_phone_confirmed_bank_change_is_paid(conn: psycopg.Connection) -> None:
    tenant = new_tenant(conn)
    store_proposal(conn, tenant, "prop_c03", amount=9_000_000, payee="sup_003")
    verdict = store_verdict(conn, tenant, "prop_c03", "approve")
    result = execute_payment(
        conn, tenant, request("prop_c03", verdict, amount=9_000_000, payee="sup_003"), now=NOW
    )
    assert result.status == "executed"


def test_naive_clock_is_rejected(conn: psycopg.Connection) -> None:
    tenant = new_tenant(conn)
    with pytest.raises(ValueError):
        execute_payment(
            conn, tenant, request("prop_x", "vrd_x", amount=1), now=NOW.replace(tzinfo=None)
        )
