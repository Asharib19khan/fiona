"""SIMULATED agent wallet (D6). Only this code moves (simulated) money, and only with a cleared verdict.

`execute_payment` loads everything it trusts from the database (never from the caller): the
stored proposal, the stored verdict and the recorded owner decisions. It pays only if all of
these hold, and otherwise refuses with a reason. Every attempt, paid or refused, is appended to
the tenant's hash-chained audit log.

1. The verdict exists, belongs to this proposal and is unmodified (verdict_hash recomputed from
   the stored body), and its outcome is approve, approve_with_conditions with every condition
   met now, or escalate with an owner decision by a user who is not the proposer.
2. The requested payee, amount and date match the stored proposal exactly.
3. Defence in depth, from the mandate and the rulebook: per-payment and daily caps (unless the
   owner released an escalation), payee on the allow-list, and no unconfirmed bank change.
4. The simulated balance never goes negative.

A payment writes the supplier_payment event, the balance update and the audit record in one
transaction. The event's source key is the proposal ID, so a retry can never pay twice.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from engine.ledger import db
from engine.ledger.ids import encode_ulid
from engine.wallet.audit import append
from fiona_contracts.hashing import verdict_hash

SIMULATED = "SIMULATED"


@dataclass(frozen=True)
class PaymentRequest:
    """What the caller asks to pay. It must match the stored proposal exactly."""

    proposal_id: str
    verdict_id: str
    payee_id: str
    amount_minor: int
    currency: str
    pay_on: str  # YYYY-MM-DD, the tenant's local business date of execution


@dataclass(frozen=True)
class PaymentResult:
    status: str  # "executed" | "refused" | "already_executed"
    reason: str | None = None
    payment_id: str | None = None
    wallet_ref: str | None = None
    event_id: str | None = None
    amount_minor: int | None = None
    label: str = SIMULATED


class Refusal(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _id(prefix: str, moment: datetime, key: str) -> str:
    """Deterministic ID for wallet records: the same proposal always gets the same IDs."""
    ms = (moment - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)
    digest = hashlib.sha256(f"{prefix}|{key}".encode()).digest()
    return f"{prefix}_{encode_ulid(ms, digest[:10])}"


def open_account(
    conn: psycopg.Connection,
    tenant_id: str,
    *,
    iban: str,
    currency: str,
    opening_balance_minor: int,
    now: datetime,
) -> str:
    """Create the tenant's simulated wallet account (demo data calls this once)."""
    account_id = _id("wal", now, f"{tenant_id}|{iban}")
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into wallet_accounts (tenant_id, id, iban, currency, balance_minor, created_at, updated_at)"
            " values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
            (tenant_id, account_id, iban, currency, opening_balance_minor, now, now),
        )
    return account_id


def _one(conn: psycopg.Connection, sql: str, params: tuple) -> tuple | None:
    return conn.execute(sql, params).fetchone()


def _check(
    conn: psycopg.Connection, tenant_id: str, req: PaymentRequest, now: datetime
) -> dict[str, Any]:
    """Every precondition; raises Refusal with the first failing reason."""
    tz = ZoneInfo(_one(conn, "select timezone from tenants where id = %s", (tenant_id,))[0])
    local_date = now.astimezone(tz).date().isoformat()

    proposal = _one(
        conn,
        "select agent, type, amount_minor, currency, payload, created_by from proposals where id = %s",
        (req.proposal_id,),
    )
    if proposal is None:
        raise Refusal("NO_PROPOSAL: no stored proposal with this ID")
    agent, ptype, amount, currency, payload, created_by = proposal
    if ptype != "payment":
        raise Refusal(f"NOT_A_PAYMENT: proposal type is {ptype}")
    if (payload.get("payee_id"), amount, currency, payload.get("pay_on")) != (
        req.payee_id,
        req.amount_minor,
        req.currency,
        req.pay_on,
    ):
        raise Refusal(
            "REQUEST_MISMATCH: payee, amount, currency or date differ from the stored proposal"
        )
    if local_date != req.pay_on:
        raise Refusal(
            f"WRONG_DATE: today is {local_date} in the tenant's time zone, the proposal pays on {req.pay_on}"
        )

    verdict = _one(
        conn,
        "select proposal_id, outcome, verdict_hash, body from verdicts where id = %s",
        (req.verdict_id,),
    )
    if verdict is None:
        raise Refusal("NO_VERDICT: no stored verdict with this ID")
    v_proposal, outcome, stored_hash, body = verdict
    if v_proposal != req.proposal_id:
        raise Refusal("WRONG_PROPOSAL: the verdict belongs to another proposal")
    latest = _one(
        conn,
        "select id from verdicts where proposal_id = %s and id not in"
        " (select previous_verdict_id from verdicts where previous_verdict_id is not null)",
        (req.proposal_id,),
    )
    if latest is None or latest[0] != req.verdict_id:
        raise Refusal("STALE_VERDICT: a newer verdict replaces this one")
    if (
        body is None
        or verdict_hash(body) != stored_hash
        or body.get("outcome") != outcome
        or body.get("proposal_id") != req.proposal_id
        or body.get("id") != req.verdict_id
    ):
        raise Refusal("TAMPERED_VERDICT: the stored verdict does not match its hash")

    released_by_owner = False
    if outcome == "block":
        raise Refusal(
            "VERDICT_BLOCKED: the Guardian blocked this proposal; no approval can release it"
        )
    if outcome == "approve_with_conditions":
        for condition in body.get("conditions", []):
            kind = condition["kind"]
            if kind == "pay_on" and condition["date"] != local_date:
                raise Refusal(
                    f"CONDITION_NOT_MET: must be paid on {condition['date']}, today is {local_date}"
                )
            if kind == "max_amount_minor" and req.amount_minor > int(condition["value"]):
                raise Refusal(f"CONDITION_NOT_MET: amount above {condition['value']}")
            if kind == "before_time" and now >= datetime.fromisoformat(
                condition["ts"].replace("Z", "+00:00")
            ):
                raise Refusal(f"CONDITION_NOT_MET: deadline {condition['ts']} has passed")
    elif outcome == "escalate":
        proposer = (created_by or {}).get("id")
        rows = conn.execute(
            "select decision, decided_by from decisions where proposal_id = %s and verdict_id = %s"
            " order by decided_at desc, id desc",  # the latest decision wins
            (req.proposal_id, req.verdict_id),
        ).fetchall()
        if not rows:
            raise Refusal("NEEDS_OWNER: escalated, and no owner decision is recorded")
        decision, decided_by = rows[0]
        if decision != "approve":
            raise Refusal("OWNER_REJECTED: the owner rejected this proposal")
        if decided_by == proposer:
            raise Refusal("SAME_ACTOR: the approver is the proposer (maker-checker, G-04)")
        released_by_owner = True
    elif outcome != "approve":
        raise Refusal(f"UNKNOWN_OUTCOME: {outcome}")

    mandate = _one(
        conn,
        "select per_payment_cap_minor, daily_cap_minor, allowed_action_types from mandates"
        " where agent = %s order by version desc limit 1",
        (agent,),
    )
    if mandate is None or "payment" not in mandate[2]:
        raise Refusal(f"OUTSIDE_MANDATE: {agent} has no mandate to pay")
    cap, daily_cap, _ = mandate
    if not released_by_owner:
        if req.amount_minor > cap:
            raise Refusal(f"OVER_CAP: {req.amount_minor} is above the per-payment cap {cap}")
        paid_today = _one(
            conn,
            "select coalesce(sum((payload->>'amount_minor')::bigint), 0) from events"
            " where type = 'supplier_payment' and source_type = 'wallet' and business_date = %s"
            " and payload->>'agent' = %s",
            (local_date, agent),
        )[0]
        if paid_today + req.amount_minor > daily_cap:
            raise Refusal(
                f"OVER_DAILY_CAP: {paid_today + req.amount_minor} would exceed the daily cap {daily_cap}"
            )

    party = _one(
        conn,
        "select on_allow_list, bank_iban, bank_account_changed_at from parties where id = %s",
        (req.payee_id,),
    )
    if party is None:
        raise Refusal("UNKNOWN_PAYEE")
    on_allow_list, payee_iban, changed_at = party
    if not on_allow_list:
        raise Refusal("NOT_ALLOW_LISTED: add the payee to the allow-list first (an owner action)")
    if changed_at is not None:
        change = _one(
            conn,
            "select payload->>'confirmed_via', payload->>'confirmed_by' from events"
            " where type = 'bank_detail_change' and party_id = %s order by occurred_at desc limit 1",
            (req.payee_id,),
        )
        phone_confirmed = (
            change is not None and change[0] == "phone" and str(change[1] or "").startswith("usr_")
        )
        # Imported here so that importing the API never needs the rulebook files (OpenAPI codegen).
        from engine.guardian_checks.rules import get_threshold

        cooling_days = int(get_threshold("T-G03-COOL")["value"])
        if not phone_confirmed:
            age = (now - changed_at).days
            raise Refusal(
                f"BANK_CHANGE_UNCONFIRMED: account changed {age} days ago (cooling-off {cooling_days} days),"
                " not confirmed by a phone call-back"
            )
    if not payee_iban:
        raise Refusal("NO_PAYEE_ACCOUNT")

    account = _one(
        conn,
        "select id, balance_minor, iban from wallet_accounts where currency = %s for update",
        (req.currency,),
    )
    if account is None:
        raise Refusal("NO_WALLET_ACCOUNT")
    if account[1] < req.amount_minor:
        raise Refusal(f"INSUFFICIENT_FUNDS: balance {account[1]} is below {req.amount_minor}")
    return {
        "agent": agent,
        "payload": payload,
        "payee_iban": payee_iban,
        "account": account,
        "local_date": local_date,
        "verdict_hash": stored_hash,
        "outcome": outcome,
    }


def execute_payment(
    conn: psycopg.Connection, tenant_id: str, req: PaymentRequest, *, now: datetime
) -> PaymentResult:
    """Pay one cleared proposal from the simulated wallet, or refuse. `now` comes from the engine clock."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    source_key = f"pay:{req.proposal_id}"
    with db.tenant_session(conn, tenant_id):
        existing = _one(
            conn,
            "select id, payload from events where source_type = 'wallet' and source_key = %s",
            (source_key,),
        )
        if existing is not None:
            return PaymentResult(
                status="already_executed",
                event_id=existing[0],
                payment_id=existing[1]["payment_id"],
                wallet_ref=existing[1]["wallet_ref"],
                amount_minor=existing[1]["amount_minor"],
            )
        try:
            facts = _check(conn, tenant_id, req, now)
        except Refusal as refusal:
            append(
                conn,
                tenant_id,
                {
                    "action": "payment_refused",
                    "label": SIMULATED,
                    "proposal_id": req.proposal_id,
                    "verdict_id": req.verdict_id,
                    "payee_id": req.payee_id,
                    "amount_minor": req.amount_minor,
                    "currency": req.currency,
                    "reason": refusal.reason,
                    "at": now.astimezone(UTC).isoformat(),
                },
                proposal_id=req.proposal_id,
                now=now,
            )
            return PaymentResult(
                status="refused", reason=refusal.reason, amount_minor=req.amount_minor
            )

        account_id, balance, from_iban = facts["account"]
        payment_id = _id("pay", now, source_key)
        wallet_ref = _id("wtx", now, source_key)
        event_id = _id("evt", now, source_key)
        conn.execute(
            "update wallet_accounts set balance_minor = %s, updated_at = %s where id = %s",
            (balance - req.amount_minor, now, account_id),
        )
        payload = {
            "party": req.payee_id,
            "payment_id": payment_id,
            "bill_id": facts["payload"].get("bill_id"),
            "amount_minor": req.amount_minor,
            "from_iban": from_iban,
            "to_iban": facts["payee_iban"],
            "method": "wallet",
            "wallet_ref": wallet_ref,
            "agent": facts["agent"],
            "proposal_id": req.proposal_id,
            "verdict_id": req.verdict_id,
            "label": SIMULATED,
        }
        conn.execute(
            "insert into events (tenant_id, id, type, occurred_at, business_date, recorded_at, party_id, currency,"
            " payload, source) values (%s, %s, 'supplier_payment', %s, %s, %s, %s, %s, %s, %s)",
            (
                tenant_id,
                event_id,
                now,
                facts["local_date"],
                now,
                req.payee_id,
                req.currency,
                json.dumps(payload),
                json.dumps({"type": "wallet", "key": source_key}),
            ),
        )
        append(
            conn,
            tenant_id,
            {
                "action": "payment_executed",
                "label": SIMULATED,
                "proposal_id": req.proposal_id,
                "verdict_id": req.verdict_id,
                "verdict_hash": facts["verdict_hash"],
                "outcome": facts["outcome"],
                "payment_id": payment_id,
                "event_id": event_id,
                "wallet_ref": wallet_ref,
                "payee_id": req.payee_id,
                "amount_minor": req.amount_minor,
                "currency": req.currency,
                "balance_after_minor": balance - req.amount_minor,
                "at": now.astimezone(UTC).isoformat(),
            },
            proposal_id=req.proposal_id,
            now=now,
        )
    return PaymentResult(
        status="executed",
        payment_id=payment_id,
        wallet_ref=wallet_ref,
        event_id=event_id,
        amount_minor=req.amount_minor,
    )
