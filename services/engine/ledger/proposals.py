"""Proposals and decisions engine module (D6/A5).

Provides persistent storage and lifecycle for agent proposals, Guardian verdicts,
and owner decisions over PostgreSQL, backed by the hash-chained audit log.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from engine.app.errors import ApiError
from engine.guardian_checks.combine import build_verdict
from engine.guardian_checks.context import (
    BankDetailChangeContext,
    BillContext,
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
from engine.ledger import db
from engine.ledger.ids import encode_ulid
from engine.wallet.audit import append
from fiona_contracts.hashing import verdict_hash
from fiona_contracts.models import DecisionRequest, Mandate, ProposalDraft, Verdict

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    s = str(dt)
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s


def _ulid(prefix: str, moment: datetime, key: str | None = None) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    ms = (moment - EPOCH) // timedelta(milliseconds=1)
    if key is not None:
        randomness = hashlib.sha256(f"{prefix}|{key}".encode()).digest()[:10]
    else:
        randomness = secrets.token_bytes(10)
    return f"{prefix}_{encode_ulid(ms, randomness)}"


EXECUTE_ALONE = "act_within_mandate"


def _compute_status(
    *,
    payment_event_id: str | None,
    decision: str | None,
    outcome: str | None,
    autonomy: str | None = None,
) -> str:
    """Project proposal status from wallet events, decisions, verdicts and autonomy.

    A cleared verdict is only "cleared" (executable without a person) when the agent acts within
    its mandate for this action type. At prepare or advise, or with no autonomy recorded, the
    owner still approves, so the proposal waits as needs_owner (fail closed).
    """
    if payment_event_id:
        return "executed"
    if decision:
        return "approved" if decision == "approve" else "rejected"
    if outcome:
        if outcome == "block":
            return "blocked"
        if outcome == "escalate":
            return "needs_owner"
        if outcome in ("approve", "approve_with_conditions"):
            return "cleared" if autonomy == EXECUTE_ALONE else "needs_owner"
    return "submitted"


def _format_proposal_dict(
    row: tuple, decisions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    (
        pid,
        agent,
        ptype,
        created_at,
        summary,
        amount_minor,
        currency,
        payload,
        evidence,
        reasoning,
        mandate_ref,
        created_by,
        verdict_id,
        outcome,
        checks,
        conditions,
        v_decided_at,
        v_hash,
        v_body,
        _dec_id,
        dec_decision,
        _dec_note,
        _dec_by,
        dec_at,
        _dec_passkey,
        payment_event_id,
        autonomy,
    ) = row

    status = _compute_status(
        payment_event_id=payment_event_id,
        decision=dec_decision,
        outcome=outcome,
        autonomy=autonomy,
    )

    amount = None
    if amount_minor is not None and currency is not None:
        amount = {"minor": amount_minor, "currency": currency}

    verdict = None
    if verdict_id and v_body:
        verdict = v_body
    elif verdict_id and outcome:
        verdict = {
            "id": verdict_id,
            "proposal_id": pid,
            "outcome": outcome,
            "checks": checks if isinstance(checks, list) else [],
            "conditions": conditions if isinstance(conditions, list) else [],
            "decided_at": _iso(v_decided_at),
            "verdict_hash": v_hash,
        }

    proposal_dict = {
        "id": pid,
        "agent": agent,
        "type": ptype,
        "created_at": _iso(created_at),
        "updated_at": _iso(dec_at or v_decided_at or created_at),
        "summary": summary,
        "amount": amount,
        "payload": payload if isinstance(payload, dict) else {},
        "evidence": evidence if isinstance(evidence, list) else [],
        "reasoning": reasoning,
        "mandate_ref": mandate_ref,
        "created_by": created_by
        if isinstance(created_by, dict)
        else {"kind": "agent", "id": agent},
        "status": status,
        "verdict_id": verdict_id,
        "verdict": verdict,
    }
    if decisions is not None:
        proposal_dict["decisions"] = decisions
    return proposal_dict


def list_proposals(
    conn: psycopg.Connection,
    tenant_id: str,
    *,
    needs_owner: bool = False,
) -> list[dict[str, Any]]:
    """List proposals for tenant, projected with current status and latest verdict."""
    with db.tenant_session(conn, tenant_id):
        rows = conn.execute(
            """
            select
                p.id, p.agent, p.type, p.created_at, p.summary, p.amount_minor, p.currency,
                p.payload, p.evidence, p.reasoning, p.mandate_ref, p.created_by,
                v.id as verdict_id, v.outcome, v.checks, v.conditions, v.decided_at as v_decided_at,
                v.verdict_hash, v.body as v_body,
                d.id as dec_id, d.decision as dec_decision, d.note as dec_note, d.decided_by as dec_by,
                d.decided_at as dec_at, d.passkey_verified as dec_passkey,
                w.id as payment_event_id, m.autonomy
            from proposals p
            left join lateral (
                select id, outcome, checks, conditions, decided_at, verdict_hash, body
                from verdicts
                where tenant_id = p.tenant_id and proposal_id = p.id
                  and id not in (
                      select previous_verdict_id from verdicts
                      where tenant_id = p.tenant_id and previous_verdict_id is not null
                  )
                order by decided_at desc, id desc
                limit 1
            ) v on true
            left join lateral (
                select id, decision, note, decided_by, decided_at, passkey_verified
                from decisions
                where tenant_id = p.tenant_id and proposal_id = p.id and verdict_id = v.id
                order by decided_at desc, id desc
                limit 1
            ) d on true
            left join lateral (
                select id from events
                where tenant_id = p.tenant_id and type = 'supplier_payment' and (payload->>'proposal_id' = p.id or source->>'key' = p.id)
                limit 1
            ) w on true
            left join lateral (
                select policy->'autonomy'->>p.type as autonomy
                from mandates
                where tenant_id = p.tenant_id and agent = p.agent
                order by version desc
                limit 1
            ) m on true
            where p.tenant_id = %s
            order by p.created_at desc, p.id desc
            """,
            (tenant_id,),
        ).fetchall()

    proposals = [_format_proposal_dict(row) for row in rows]
    if needs_owner:
        proposals = [p for p in proposals if p["status"] in ("needs_owner", "blocked")]
    return proposals


def get_proposal(
    conn: psycopg.Connection,
    tenant_id: str,
    proposal_id: str,
) -> dict[str, Any] | None:
    """Get single proposal with its verdict and decision history."""
    with db.tenant_session(conn, tenant_id):
        row = conn.execute(
            """
            select
                p.id, p.agent, p.type, p.created_at, p.summary, p.amount_minor, p.currency,
                p.payload, p.evidence, p.reasoning, p.mandate_ref, p.created_by,
                v.id as verdict_id, v.outcome, v.checks, v.conditions, v.decided_at as v_decided_at,
                v.verdict_hash, v.body as v_body,
                d.id as dec_id, d.decision as dec_decision, d.note as dec_note, d.decided_by as dec_by,
                d.decided_at as dec_at, d.passkey_verified as dec_passkey,
                w.id as payment_event_id, m.autonomy
            from proposals p
            left join lateral (
                select id, outcome, checks, conditions, decided_at, verdict_hash, body
                from verdicts
                where tenant_id = p.tenant_id and proposal_id = p.id
                  and id not in (
                      select previous_verdict_id from verdicts
                      where tenant_id = p.tenant_id and previous_verdict_id is not null
                  )
                order by decided_at desc, id desc
                limit 1
            ) v on true
            left join lateral (
                select id, decision, note, decided_by, decided_at, passkey_verified
                from decisions
                where tenant_id = p.tenant_id and proposal_id = p.id and verdict_id = v.id
                order by decided_at desc, id desc
                limit 1
            ) d on true
            left join lateral (
                select id from events
                where tenant_id = p.tenant_id and type = 'supplier_payment' and (payload->>'proposal_id' = p.id or source->>'key' = p.id)
                limit 1
            ) w on true
            left join lateral (
                select policy->'autonomy'->>p.type as autonomy
                from mandates
                where tenant_id = p.tenant_id and agent = p.agent
                order by version desc
                limit 1
            ) m on true
            where p.tenant_id = %s and p.id = %s
            """,
            (tenant_id, proposal_id),
        ).fetchone()

        if not row:
            return None

        dec_rows = conn.execute(
            """
            select id, decision, note, decided_by, decided_at, passkey_verified
            from decisions
            where tenant_id = %s and proposal_id = %s
            order by decided_at desc, id desc
            """,
            (tenant_id, proposal_id),
        ).fetchall()

    decisions = [
        {
            "id": r[0],
            "decision": r[1],
            "note": r[2],
            "decided_by": r[3],
            "decided_at": _iso(r[4]),
            "passkey_verified": r[5],
        }
        for r in dec_rows
    ]
    return _format_proposal_dict(row, decisions=decisions)


_FORECAST_CACHE: dict[tuple[str, str], tuple[float, ForecastContext]] = {}
_FORECAST_TTL_SECONDS = 60.0


def _ledger_forecast(
    conn: psycopg.Connection, tenant_id: str, today: Any, now: datetime
) -> ForecastContext | None:
    """The tenant's 13-week forecast from its posted ledger, cached for a minute so a batch of
    proposals does not recompute it. None when the ledger has no bank history yet."""
    import time

    from engine.forecast.cash.engine import forecast_cash
    from engine.forecast.ledger_source import load_ledger_snapshot

    key = (tenant_id, str(today))
    cached = _FORECAST_CACHE.get(key)
    if cached and time.monotonic() - cached[0] < _FORECAST_TTL_SECONDS:
        return cached[1]
    try:
        snapshot = load_ledger_snapshot(conn, tenant_id, today, in_tenant_session=True)
        if not snapshot.bank_lines:
            return None
        cash = forecast_cash(snapshot, weeks=13, mode="live", generated_at=now)
    except Exception:  # G-08 then sees the flat fallback, never no forecast
        return None
    context = ForecastContext(
        id=cash.run_id,
        as_of=_iso(now),
        weeks=[
            ForecastWeek(w=w.week, start=w.start.isoformat(), closing_minor=w.closing.minor)
            for w in cash.weeks
        ],
    )
    _FORECAST_CACHE[key] = (time.monotonic(), context)
    return context


def _resolve_evidence(
    conn: psycopg.Connection, tenant_id: str, evidence: dict[str, Any]
) -> dict[str, Any] | None:
    """What the ledger itself says a piece of evidence is: its party and amount."""
    ref, kind = str(evidence.get("ref", "")), evidence.get("kind")
    if kind in ("ledger_row", "ledger_event", "bill") and ref.startswith("bill_"):
        row = conn.execute(
            "select party_id, payload from events where tenant_id = %s and type = 'purchase_bill'"
            " and payload->>'bill_id' = %s order by business_date desc limit 1",
            (tenant_id, ref),
        ).fetchone()
        if row:
            p = row[1] or {}
            return {
                "kind": kind,
                "party_id": p.get("party") or p.get("supplier_id") or row[0],
                "amount_minor": p.get("total_minor"),
            }
    if kind == "document" and ref.startswith("doc_"):
        row = conn.execute(
            "select extracted from documents where tenant_id = %s and id = %s",
            (tenant_id, ref),
        ).fetchone()
        if row:
            extracted = row[0] or {}
            return {
                "kind": "document",
                "party_id": extracted.get("supplier_id") or extracted.get("party"),
                "amount_minor": extracted.get("total_minor"),
            }
    return None


def _build_guardian_context(
    conn: psycopg.Connection,
    tenant_id: str,
    proposal: dict[str, Any],
    now: datetime,
) -> CheckContext:
    """Assemble CheckContext from tenant database state and proposal."""
    session_ctx = (
        db.tenant_session(conn, tenant_id)
        if conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        else nullcontext(conn)
    )
    with session_ctx:
        # 1. Tenant info & buffer
        tenant_row = conn.execute(
            "select cash_buffer_minor, timezone, currency, country from tenants where id = %s",
            (tenant_id,),
        ).fetchone()
        cash_buffer_minor = tenant_row[0] if tenant_row and tenant_row[0] is not None else 0
        tz_str = tenant_row[1] if tenant_row and tenant_row[1] else "Asia/Karachi"
        currency = tenant_row[2] if tenant_row and tenant_row[2] else "PKR"
        country = tenant_row[3] if tenant_row and tenant_row[3] else "PK"
        tz = ZoneInfo(tz_str)
        today_date = now.astimezone(tz).date()

        # 2. Mandate
        agent = proposal["agent"]
        mandate_row = conn.execute(
            """
            select id, version, currency, per_payment_cap_minor, daily_cap_minor,
                   allowed_action_types, effective_from, policy
            from mandates
            where tenant_id = %s and agent = %s
            order by version desc
            limit 1
            """,
            (tenant_id, agent),
        ).fetchone()

        mandate = None
        if mandate_row:
            allowed_actions = mandate_row[5] or []
            stored = (mandate_row[7] or {}).get("autonomy") or {}
            # The owner's recorded level per action; an allowed action with no level recorded
            # falls back to prepare (the owner approves), never to acting alone.
            autonomy = {action: stored.get(action, "prepare") for action in allowed_actions}
            mandate = Mandate(
                id=mandate_row[0],
                tenant_id=tenant_id,
                agent=agent,
                version=mandate_row[1],
                status="active",
                currency=mandate_row[2],
                autonomy=autonomy,
                per_payment_cap_minor=mandate_row[3],
                daily_cap_minor=mandate_row[4],
                allowed_action_types=allowed_actions,
                effective_from=str(mandate_row[6]),
                approved_by="usr_owner",
                created_at=_iso(now),
            )

        # 3. Payee info (if payment)
        payee_ctx = None
        payload = proposal.get("payload") or {}
        payee_id = payload.get("payee_id")
        if payee_id:
            p_row = conn.execute(
                """
                select id, on_allow_list, bank_iban, bank_account_changed_at, tax_id, tax_id_type
                from parties
                where tenant_id = %s and id = %s
                """,
                (tenant_id, payee_id),
            ).fetchone()
            if p_row:
                # Check for bank detail change event
                bdc_row = conn.execute(
                    """
                    select payload, occurred_at from events
                    where tenant_id = %s and type = 'bank_detail_change' and party_id = %s
                    order by occurred_at desc limit 1
                    """,
                    (tenant_id, payee_id),
                ).fetchone()
                latest_bdc = None
                if bdc_row:
                    bdc_payload = bdc_row[0] if isinstance(bdc_row[0], dict) else {}
                    latest_bdc = BankDetailChangeContext(
                        confirmed_via=bdc_payload.get("confirmed_via"),
                        confirmed_by=bdc_payload.get("confirmed_by"),
                        old_iban=bdc_payload.get("old_iban"),
                        new_iban=bdc_payload.get("new_iban"),
                        occurred_at=bdc_row[1],
                    )

                payee_ctx = PartyContext(
                    party_id=p_row[0],
                    on_allow_list=p_row[1],
                    bank_iban=p_row[2],
                    bank_account_changed_at=p_row[3],
                    latest_bank_detail_change=latest_bdc,
                    tax_id=p_row[4],
                    tax_id_type=p_row[5] or "NTN",
                )

        # 4. Prior bills (from purchase_bill events)
        bill_events = conn.execute(
            """
            select party_id, payload, business_date
            from events
            where tenant_id = %s and type = 'purchase_bill'
            order by business_date desc, id desc
            limit 100
            """,
            (tenant_id,),
        ).fetchall()
        prior_bills = []
        for party_id, payload, bdate in bill_events:
            if not isinstance(payload, dict):
                continue
            b_id = payload.get("bill_id") or payload.get("id")
            prior_bills.append(
                PriorBillContext(
                    bill_id=str(b_id) if b_id else None,
                    supplier_id=party_id or payload.get("supplier_id"),
                    number=payload.get("number") or payload.get("bill_number"),
                    total_minor=payload.get("total_minor") or payload.get("amount_minor"),
                    document_sha256=payload.get("document_sha256") or payload.get("sha256"),
                    issue_date=payload.get("issue_date")
                    or payload.get("date")
                    or (bdate.isoformat() if bdate else None),
                    paid=payload.get("paid"),
                    status=payload.get("status"),
                )
            )

        # 5. Payments today minor
        spent_row = conn.execute(
            """
            select coalesce(sum((payload->>'amount_minor')::bigint), 0)
            from events
            where tenant_id = %s and type = 'supplier_payment' and business_date = %s
            """,
            (tenant_id, today_date),
        ).fetchone()
        payments_today = int(spent_row[0]) if spent_row and spent_row[0] is not None else 0

        # 6. Forecast context: the real 13-week forecast from the ledger (G-08 checks a payment
        # against the weeks it lands in). A tenant with no ledger history yet falls back to its
        # wallet balance held flat, which is all that is known about its cash.
        forecast_ctx = _ledger_forecast(conn, tenant_id, today_date, now)
        if forecast_ctx is None:
            bal_row = conn.execute(
                "select coalesce(balance_minor, 350000000) from wallet_accounts where tenant_id = %s limit 1",
                (tenant_id,),
            ).fetchone()
            current_balance = bal_row[0] if bal_row and bal_row[0] is not None else 350_000_000
            forecast_ctx = ForecastContext(
                id=f"fc_{tenant_id}",
                as_of=_iso(now),
                weeks=[
                    ForecastWeek(
                        w=i,
                        start=(today_date + timedelta(weeks=i - 1)).isoformat(),
                        closing_minor=current_balance,
                    )
                    for i in range(1, 14)
                ],
            )

        # 7. Evidence index
        amount_val = proposal.get("amount")
        amt_minor = (
            amount_val.get("minor")
            if isinstance(amount_val, dict)
            else (proposal.get("amount_minor") or 0)
        )
        evidence_index: dict[str, dict[str, Any]] = {}
        for ev in proposal.get("evidence", []):
            if isinstance(ev, dict) and "ref" in ev:
                ref = ev["ref"]
                # The ledger's own record when it has one, so G-09 compares the claim with the
                # evidence's real party and amount; otherwise the reference as stated.
                evidence_index[ref] = _resolve_evidence(conn, tenant_id, ev) or {
                    "kind": ev.get("kind", "document"),
                    "party_id": payee_id,
                    "amount_minor": amt_minor,
                }

        # 8. Bill, PO, GRN contexts
        bill_ctx = None
        po_ctx = None
        grn_ctx = None

        raw_bill = payload.get("bill")
        b_data = {}
        if payload.get("bill_id"):
            b_evt = conn.execute(
                """
                select payload from events
                where tenant_id = %s and type = 'purchase_bill' and payload->>'bill_id' = %s
                order by business_date desc, id desc limit 1
                """,
                (tenant_id, payload.get("bill_id")),
            ).fetchone()
            if b_evt and isinstance(b_evt[0], dict):
                b_data = b_evt[0]

        if isinstance(raw_bill, dict):
            bill_ctx = BillContext(**raw_bill)
        elif payload.get("bill_id"):
            category = payload.get("category") or b_data.get("category") or "inventory_supplier"
            contract_ref = payload.get("contract_ref") or b_data.get("contract_ref")
            bill_ctx = BillContext(
                bill_id=payload.get("bill_id"),
                supplier_id=payee_id or b_data.get("supplier_id") or "sup_unknown",
                category=category,
                contract_ref=contract_ref,
                total_minor=amt_minor,
                due_date=str(b_data.get("due_date") or today_date),
            )

        raw_po = payload.get("po")
        po_id = payload.get("po_id") or b_data.get("po_id")
        po_number = payload.get("po_number") or b_data.get("po_number")
        if not po_id and po_number:
            # Imported bills cite the PO by its printed number, not its ID.
            po_match = conn.execute(
                "select id from purchase_orders where tenant_id = %s and number = %s"
                " order by id limit 1",
                (tenant_id, po_number),
            ).fetchone()
            po_id = po_match[0] if po_match else None
        if isinstance(raw_po, dict):
            po_ctx = POContext(**raw_po)
        elif po_id:
            po_row = conn.execute(
                "select id, number, lines from purchase_orders where tenant_id = %s and id = %s",
                (tenant_id, po_id),
            ).fetchone()
            if po_row:
                po_lines = [
                    POLineContext(
                        sku=line.get("sku"),
                        qty=line.get("qty", 0),
                        unit_cost_minor=line.get("unit_cost_minor", 0),
                    )
                    for line in (po_row[2] or [])
                ]
                po_ctx = POContext(id=po_row[0], number=po_row[1], lines=po_lines)

        raw_grn = payload.get("grn")
        grn_id = payload.get("grn_id") or b_data.get("grn_id")
        if not grn_id and po_id:
            grn_match = conn.execute(
                "select id from goods_received where tenant_id = %s and po_id = %s"
                " order by received_on desc, id desc limit 1",
                (tenant_id, po_id),
            ).fetchone()
            grn_id = grn_match[0] if grn_match else None
        if isinstance(raw_grn, dict):
            grn_ctx = GRNContext(**raw_grn)
        elif grn_id:
            grn_row = conn.execute(
                "select id, po_id, lines from goods_received where tenant_id = %s and id = %s",
                (tenant_id, grn_id),
            ).fetchone()
            if grn_row:
                grn_lines = [
                    GRNLineContext(
                        sku=line.get("sku"),
                        qty_received=line.get("qty_received", line.get("qty", 0)),
                    )
                    for line in (grn_row[2] or [])
                ]
                grn_ctx = GRNContext(id=grn_row[0], po_id=grn_row[1], lines=grn_lines)

    return CheckContext(
        proposal=proposal,
        mandate=mandate,
        buffer_minor=cash_buffer_minor,
        currency=currency,
        country=country,
        payee=payee_ctx,
        bill=bill_ctx,
        po=po_ctx,
        grn=grn_ctx,
        prior_bills=prior_bills,
        forecast=forecast_ctx,
        evidence_index=evidence_index,
        paid_today_minor=payments_today,
        now=now,
    )


def create_proposal(
    conn: psycopg.Connection,
    tenant_id: str,
    draft: dict[str, Any] | ProposalDraft,
    *,
    now: datetime,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Store proposal, run Guardian evaluation, insert Verdict, and append to audit log."""
    raw = draft.root.model_dump(mode="json") if isinstance(draft, ProposalDraft) else dict(draft)

    # Validate essential fields
    for field in ("agent", "type", "summary", "payload", "evidence", "reasoning"):
        if field not in raw:
            raise ApiError(
                422, "validation_error", f"ProposalDraft missing required field: {field}"
            )

    # Check for existing proposal with this ID or idempotency
    proposal_id = raw.get("id") or _ulid("prop", now)

    amount = raw.get("amount") or {}
    amount_minor = amount.get("minor") if isinstance(amount, dict) else None
    currency = amount.get("currency") if isinstance(amount, dict) else None

    mandate_ref = raw.get("mandate_ref")
    created_by = raw.get("created_by") or {"kind": "agent", "id": raw["agent"]}

    # Assemble proposal for storage
    proposal_stored = {
        "id": proposal_id,
        "tenant_id": tenant_id,
        "agent": raw["agent"],
        "type": raw["type"],
        "created_at": _iso(now),
        "summary": raw["summary"],
        "amount_minor": amount_minor,
        "currency": currency,
        "amount": {"minor": amount_minor, "currency": currency}
        if amount_minor is not None
        else None,
        "payload": raw["payload"],
        "evidence": raw["evidence"],
        "reasoning": raw["reasoning"],
        "mandate_ref": mandate_ref,
        "created_by": created_by,
        "status": "submitted",
    }

    with db.tenant_session(conn, tenant_id):
        # Resolve mandate_ref to valid mandate in table
        actual_mandate_ref = None
        if mandate_ref:
            m_row = conn.execute(
                "select id from mandates where tenant_id = %s and id = %s",
                (tenant_id, mandate_ref),
            ).fetchone()
            if m_row:
                actual_mandate_ref = m_row[0]
            else:
                agent_m = conn.execute(
                    "select id from mandates where tenant_id = %s and agent = %s order by version desc limit 1",
                    (tenant_id, raw["agent"]),
                ).fetchone()
                if agent_m:
                    actual_mandate_ref = agent_m[0]
        else:
            agent_m = conn.execute(
                "select id from mandates where tenant_id = %s and agent = %s order by version desc limit 1",
                (tenant_id, raw["agent"]),
            ).fetchone()
            if agent_m:
                actual_mandate_ref = agent_m[0]

        proposal_stored["mandate_ref"] = actual_mandate_ref

        # 1. Insert proposal
        conn.execute(
            """
            insert into proposals (
                tenant_id, id, agent, type, created_at, summary, amount_minor, currency,
                payload, evidence, reasoning, mandate_ref, created_by
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                proposal_id,
                proposal_stored["agent"],
                proposal_stored["type"],
                now,
                proposal_stored["summary"],
                amount_minor,
                currency,
                json.dumps(proposal_stored["payload"]),
                json.dumps(proposal_stored["evidence"]),
                proposal_stored["reasoning"],
                actual_mandate_ref,
                json.dumps(created_by),
            ),
        )

        # 2. Build context and run Guardian checks
        ctx = _build_guardian_context(conn, tenant_id, proposal_stored, now)
        checks = run_deterministic_checks(ctx)
        verdict: Verdict = build_verdict(proposal_id, checks, now)

        # 3. Store verdict
        verdict_dict = verdict.model_dump(mode="json", exclude_none=True)
        v_body = dict(verdict_dict)
        v_body_no_hash = {k: v for k, v in v_body.items() if k != "verdict_hash"}
        v_hash = verdict_hash(v_body_no_hash)

        conn.execute(
            """
            insert into verdicts (
                tenant_id, id, proposal_id, outcome, checks, conditions, decided_at,
                verdict_hash, policy_version, previous_verdict_id, body
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                verdict.id,
                proposal_id,
                verdict.outcome,
                json.dumps(verdict_dict.get("checks", [])),
                json.dumps(verdict_dict.get("conditions", [])),
                now,
                v_hash,
                verdict.policy_version,
                verdict.previous_verdict_id,
                json.dumps(v_body_no_hash),
            ),
        )

        # 4. Append to audit log
        append(
            conn,
            tenant_id,
            {
                "action": "proposal_submitted",
                "proposal_id": proposal_id,
                "agent": raw["agent"],
                "type": raw["type"],
                "amount_minor": amount_minor,
                "currency": currency,
                "verdict_id": verdict.id,
                "outcome": verdict.outcome,
            },
            proposal_id=proposal_id,
            now=now,
        )

    # Re-fetch full stored proposal
    stored = get_proposal(conn, tenant_id, proposal_id)
    return stored or proposal_stored, verdict_dict


def record_owner_decision(
    conn: psycopg.Connection,
    tenant_id: str,
    proposal_id: str,
    req: DecisionRequest,
    *,
    decided_by: str,
    now: datetime,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Record an owner approval or rejection for an escalated proposal."""
    with db.tenant_session(conn, tenant_id):
        # 1. Verify proposal exists
        p_row = conn.execute(
            "select created_by from proposals where tenant_id = %s and id = %s",
            (tenant_id, proposal_id),
        ).fetchone()
        if not p_row:
            raise ApiError(404, "not_found", f"No proposal found with ID: {proposal_id}")

        created_by = p_row[0] if isinstance(p_row[0], dict) else {}
        proposer_id = created_by.get("id")

        # 2. Maker-checker enforcement (G-04)
        if decided_by == proposer_id:
            raise ApiError(
                400,
                "maker_checker_violation",
                "The approver cannot be the proposer (maker-checker, G-04).",
            )

        # 3. Latest verdict
        v_row = conn.execute(
            """
            select id, outcome from verdicts
            where tenant_id = %s and proposal_id = %s
              and id not in (
                  select previous_verdict_id from verdicts
                  where tenant_id = %s and previous_verdict_id is not null
              )
            order by decided_at desc, id desc limit 1
            """,
            (tenant_id, proposal_id, tenant_id),
        ).fetchone()
        if not v_row:
            raise ApiError(400, "no_verdict", "Proposal has no Guardian verdict.")

        verdict_id, outcome = v_row[0], v_row[1]

        # 4. Cannot override a block
        if outcome == "block":
            raise ApiError(
                400,
                "cannot_override_block",
                "The Guardian blocked this proposal; an owner decision cannot override a block (rulebook/guardian.yaml).",
            )

        # 5. Check idempotency
        if idempotency_key:
            existing_dec = conn.execute(
                "select id, decision, note, decided_by, decided_at, passkey_verified from decisions"
                " where tenant_id = %s and idempotency_key = %s",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing_dec:
                return {
                    "api_version": "v1",
                    "decision": {
                        "id": existing_dec[0],
                        "proposal_id": proposal_id,
                        "verdict_id": verdict_id,
                        "decision": existing_dec[1],
                        "note": existing_dec[2],
                        "decided_by": existing_dec[3],
                        "decided_at": _iso(existing_dec[4]),
                        "passkey_verified": existing_dec[5],
                    },
                    "proposal_status": "approved" if existing_dec[1] == "approve" else "rejected",
                }

        # 6. Generate decision ID and store
        decision_id = _ulid("dec", now)
        passkey_verified = bool(req.assertion)

        conn.execute(
            """
            insert into decisions (
                tenant_id, id, proposal_id, verdict_id, decision, note, decided_by,
                decided_at, passkey_verified, idempotency_key
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                decision_id,
                proposal_id,
                verdict_id,
                req.decision,
                req.note,
                decided_by,
                now,
                passkey_verified,
                idempotency_key,
            ),
        )

        # 7. Audit log
        append(
            conn,
            tenant_id,
            {
                "action": "owner_decision",
                "proposal_id": proposal_id,
                "verdict_id": verdict_id,
                "decision": req.decision,
                "decided_by": decided_by,
                "passkey_verified": passkey_verified,
                "note": req.note,
            },
            proposal_id=proposal_id,
            now=now,
        )

    return {
        "api_version": "v1",
        "decision": {
            "id": decision_id,
            "proposal_id": proposal_id,
            "verdict_id": verdict_id,
            "decision": req.decision,
            "note": req.note,
            "decided_by": decided_by,
            "decided_at": _iso(now),
            "passkey_verified": passkey_verified,
        },
        "proposal_status": "approved" if req.decision == "approve" else "rejected",
    }
