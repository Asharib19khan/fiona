"""The Guardian's adversarial review, engine side (G-12, A6).

The model half of the Guardian runs in services/guardian, in its own Claude process. The engine
never calls a model. It does two deterministic jobs around that review:

1. `review_packet` builds what rulebook/guardian.yaml G-12 says the reviewer sees: the Proposal
   without the agent's `reasoning`, the raw evidence rows and document text (quoted as data),
   the payee's history, and a deterministic pre-scan of the document text. The Guardian fetches
   this itself, so the proposing agent cannot hand it a doctored version.
2. `record_review` turns the reviewer's structured answer into a G-12 Check, combines it with the
   proposal's deterministic checks (the strictest outcome wins, so the model can only raise an
   outcome), and stores a new verdict chained to the one it reviewed. Any failure escalates.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import psycopg

from engine.app.errors import ApiError
from engine.guardian_checks.combine import build_verdict
from engine.guardian_checks.rules import get_threshold
from engine.ledger import db
from engine.wallet.audit import append
from fiona_contracts.hashing import verdict_hash
from fiona_contracts.models import Check

REVIEWED_TYPES = {
    "payment",
    "bill_approval",
    "journal_adjustment",
    "send_document",
    "purchase_order",
}
CONCERN_SCALE = ("none", "low", "medium", "high")
MAX_TEXT = 4_000  # characters of any one document's text passed to the reviewer
MAX_REASON = 600

# The deterministic pre-scan (G-12 deterministic_pre_scan). Flags are data for the reviewer,
# never an outcome on their own.
_PRE_SCAN: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "addresses_an_ai",
        re.compile(
            r"(ignore|disregard|forget) (all |any )?(of )?(your |the |my )?(previous|prior|above|earlier|existing)"
            r"|as the assistant|\bsystem\s*(note|prompt|message)?\s*:"
            r"|(note|message|instructions?) (to|for) (the |any )?(ai|assistant|agent|model|bot)\b"
            r"|you are (an? )?(ai|assistant|model)|disregard (the|your) (rules|instructions)",
            re.I,
        ),
    ),
    (
        "urgency",
        re.compile(r"\burgent\b|today only|immediately|within the hour|final notice|asap", re.I),
    ),
    (
        "secrecy",
        re.compile(
            r"do not call|don'?t call|keep (this )?confidential|do not tell|no need to verify", re.I
        ),
    ),
    (
        "payment_instruction_change",
        re.compile(
            r"new (bank )?account|account (has )?changed|new iban|updated bank details|pay to (the )?following",
            re.I,
        ),
    ),
)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _clip(value: Any) -> Any:
    """Document content with every string cut to MAX_TEXT characters."""
    if isinstance(value, str):
        return value[:MAX_TEXT]
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v) for v in value[:200]]
    return value


def pre_scan(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    for doc in documents:
        for text in _strings(doc.get("content")):
            for flag, pattern in _PRE_SCAN:
                match = pattern.search(text)
                if match:
                    flags.append(
                        {"flag": flag, "document_id": doc["id"], "excerpt": match.group(0)}
                    )
    return flags


def _latest_verdict(conn: psycopg.Connection, proposal_id: str) -> tuple | None:
    """The newest verdict of the chain: the one no other verdict replaces (the wallet's rule)."""
    return conn.execute(
        "select id, outcome, checks, body from verdicts where proposal_id = %s and id not in"
        " (select previous_verdict_id from verdicts where previous_verdict_id is not null)"
        " order by decided_at desc, id desc limit 1",
        (proposal_id,),
    ).fetchone()


def review_packet(conn: psycopg.Connection, tenant_id: str, proposal_id: str) -> dict[str, Any]:
    with db.tenant_session(conn, tenant_id):
        row = conn.execute(
            "select id, agent, type, created_at, summary, amount_minor, currency, payload, evidence"
            " from proposals where id = %s",
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "not_found", f"No proposal found with ID: {proposal_id}")
        pid, agent, ptype, created_at, summary, amount_minor, currency, payload, evidence = row
        latest = _latest_verdict(conn, pid)
        if latest is None:
            raise ApiError(409, "no_verdict", "The deterministic checks have not run yet.")

        bill_ids = {e["ref"] for e in evidence if e.get("kind") == "ledger_row"}
        if payload.get("bill_id"):
            bill_ids.add(payload["bill_id"])
        bills = [
            r[0]
            for r in conn.execute(
                "select payload from events where type = 'purchase_bill' and payload->>'bill_id' = any(%s)",
                (sorted(bill_ids),),
            )
        ]
        doc_ids = {e["ref"] for e in evidence if e.get("kind") == "document"}
        doc_ids |= {b["document_id"] for b in bills if b.get("document_id")}
        documents = [
            {
                "id": r[0],
                "kind": r[1],
                "sha256": r[2],
                "content": _clip(r[3]),
            }
            for r in conn.execute(
                "select id, kind, sha256, extracted from documents where id = any(%s) order by id",
                (sorted(doc_ids),),
            )
        ]

        payee_id = payload.get("payee_id") or payload.get("supplier_id")
        payee = None
        if payee_id:
            party = conn.execute(
                "select id, name, kind, on_allow_list, bank_iban, bank_account_changed_at from parties"
                " where id = %s",
                (payee_id,),
            ).fetchone()
            if party:
                changes = conn.execute(
                    "select occurred_at, payload from events where type = 'bank_detail_change'"
                    " and party_id = %s order by occurred_at desc limit 5",
                    (payee_id,),
                ).fetchall()
                history = conn.execute(
                    "select count(*), coalesce(sum((payload->>'amount_minor')::bigint), 0),"
                    " max(business_date) from events where type = 'supplier_payment' and party_id = %s",
                    (payee_id,),
                ).fetchone()
                payee = {
                    "id": party[0],
                    "name": party[1],
                    "kind": party[2],
                    "on_allow_list": party[3],
                    "bank_iban": party[4],
                    "bank_account_changed_at": party[5].isoformat() if party[5] else None,
                    "recent_bank_detail_changes": [
                        {"occurred_at": c[0].isoformat(), "detail": c[1]} for c in changes
                    ],
                    "payments_to_date": {
                        "count": history[0],
                        "total_minor": int(history[1]),
                        "last_paid_on": str(history[2]) if history[2] else None,
                    },
                }

    return {
        "api_version": "v1",
        "proposal": {
            "id": pid,
            "agent": agent,
            "type": ptype,
            "created_at": created_at.isoformat(),
            "summary": summary,
            "amount": {"minor": amount_minor, "currency": currency}
            if amount_minor is not None
            else None,
            "payload": payload,
            "evidence": evidence,
        },
        "reviewed_verdict_id": latest[0],
        "deterministic_outcome": latest[1],
        "deterministic_checks": [
            {k: c.get(k) for k in ("rule", "result", "outcome", "detail")}
            for c in (latest[2] or [])
            if c.get("name") != "adversarial"
        ],
        "bills": bills,
        "documents": documents,
        "payee": payee,
        "pre_scan_flags": pre_scan(documents),
        "review_required": ptype in REVIEWED_TYPES,
    }


def _review_check(review: dict[str, Any]) -> Check:
    """The G-12 Check from the reviewer's answer. The engine, not the model, sets the outcome."""
    audit = {
        "model": str(review.get("model") or "unknown")[:80],
        "prompt_version": str(review.get("prompt_version") or "unknown")[:80],
        "latency_ms": review.get("latency_ms")
        if isinstance(review.get("latency_ms"), int)
        else None,
    }
    error = review.get("error")
    concern = review.get("concern")
    reasons = review.get("reasons")
    injection = review.get("injection_detected")
    if (
        error
        or concern not in CONCERN_SCALE
        or not isinstance(reasons, list)
        or not all(isinstance(r, str) for r in reasons)
        or not isinstance(injection, bool)
    ):
        detail = str(error or "the reviewer's answer did not match the G-12 output schema")[
            :MAX_REASON
        ]
        return Check(
            name="adversarial",
            rule="G-12",
            result="fail",
            outcome="escalate",
            detail=f"CHECK_ERROR: {detail}",
            audit=audit,
        )
    threshold = str(get_threshold("T-G12-CONCERN").get("value", "high"))
    raised = CONCERN_SCALE.index(concern) >= CONCERN_SCALE.index(threshold)
    clipped = [r[:MAX_REASON] for r in reasons[:6]]
    summary = "; ".join(clipped) or "No concerns found."
    return Check(
        name="adversarial",
        rule="G-12",
        result="fail" if raised else "pass",
        outcome="escalate" if raised else "approve",
        detail=f"Adversarial review: concern {concern}. {summary}"[:1_000],
        audit={**audit, "concern": concern, "reasons": clipped, "injection_detected": injection},
    )


def record_review(
    conn: psycopg.Connection,
    tenant_id: str,
    proposal_id: str,
    reviewed_verdict_id: str,
    review: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    check = _review_check(review)
    with db.tenant_session(conn, tenant_id):
        latest = _latest_verdict(conn, proposal_id)
        if latest is None:
            raise ApiError(404, "not_found", f"No verdict found for proposal {proposal_id}")
        if latest[0] != reviewed_verdict_id:
            raise ApiError(
                409, "stale_verdict", "A newer verdict replaces the one reviewed; review again."
            )
        kept = [
            Check.model_validate(c)
            for c in (latest[2] or [])
            if c.get("name") != "adversarial"  # a re-review replaces the earlier model check
        ]
        verdict = build_verdict(
            proposal_id,
            [*kept, check],
            now,
            policy_version=(latest[3] or {}).get("policy_version"),
            previous_verdict_id=latest[0],
        )
        body = verdict.model_dump(mode="json", exclude_none=True)
        stored = {k: v for k, v in body.items() if k != "verdict_hash"}
        conn.execute(
            "insert into verdicts (tenant_id, id, proposal_id, outcome, checks, conditions, decided_at,"
            " verdict_hash, policy_version, previous_verdict_id, body)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                tenant_id,
                verdict.id,
                proposal_id,
                verdict.outcome,
                json.dumps(body.get("checks", [])),
                json.dumps(body.get("conditions", [])),
                now,
                verdict_hash(stored),
                verdict.policy_version,
                latest[0],
                json.dumps(stored),
            ),
        )
        append(
            conn,
            tenant_id,
            {
                "action": "guardian_review",
                "proposal_id": proposal_id,
                "reviewed_verdict_id": latest[0],
                "verdict_id": verdict.id,
                "outcome": verdict.outcome,
                "concern": (check.audit or {}).get("concern"),
                "check_error": check.detail.startswith("CHECK_ERROR"),
                "model": (check.audit or {}).get("model"),
            },
            proposal_id=proposal_id,
            now=now,
        )
    return {"api_version": "v1", "verdict": body}
