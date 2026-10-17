"""Deterministic bank-to-ledger reconciliation (D4 passes 1 to 3).

The matcher only proposes rows it can verify from ledger facts. It never changes bank lines or
events; callers may later confirm a proposal through the ordinary review flow. This keeps an
uncertain grouping from becoming accounting truth.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import psycopg

from engine.ledger import db
from fiona_contracts.models import Action, Evidence, Finding, Money

RUN_ID = "reconcile-deterministic-v1"
_SETTLEMENT_METHODS = {
    "POS CARD SETTL": {"card", "bank_qr", "raast"},
    "QR SETTL": {"bank_qr", "raast"},
    "RAAST P2M SETTL": {"raast"},
    "JAZZCASH MERCH SETTL": {"jazzcash"},
    "EASYPAISA MERCH SETTL": {"easypaisa"},
}
_BRANCH = re.compile(r"\b(BR\d{2})\b")


@dataclass(frozen=True)
class Candidate:
    bank_line_id: str
    event_ids: tuple[str, ...]
    pass_name: str
    confidence: float


def _match_id(candidate: Candidate) -> str:
    source = "|".join((candidate.bank_line_id, *candidate.event_ids, candidate.pass_name))
    return "mch_" + hashlib.sha256(source.encode()).hexdigest()[:24]


def _days_apart(left: date, right: date) -> int:
    return abs((left - right).days)


def _event_total(kind: str, payload: dict[str, Any]) -> int:
    if kind == "supplier_payment":
        return int(payload["amount_minor"])
    return int(payload["total_minor"])


def _settlement_methods(narration: str) -> set[str] | None:
    for prefix, methods in _SETTLEMENT_METHODS.items():
        if narration.startswith(prefix):
            return methods
    return None


def _candidate_matches(
    bank_lines: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[Candidate]:
    """Return non-overlapping, deterministic proposals in pass order."""
    used_events: set[str] = set()
    candidates: list[Candidate] = []
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_kind[event["type"]].append(event)

    def add(
        bank: dict[str, Any], found: list[dict[str, Any]], pass_name: str, confidence: float
    ) -> None:
        ids = tuple(sorted(event["id"] for event in found))
        if not ids or any(event_id in used_events for event_id in ids):
            return
        candidates.append(Candidate(bank["id"], ids, pass_name, confidence))
        used_events.update(ids)

    # Pass 1: outgoing supplier payments and unambiguous invoice receipts. Both use an
    # exact integer amount, a three-day date window and a reference visible in the narration.
    for bank in bank_lines:
        narration = bank["narration"].upper()
        amount = bank["amount_minor"]
        if narration.startswith("IBFT TO ") and amount < 0:
            found = [
                event
                for event in by_kind["supplier_payment"]
                if event["id"] not in used_events
                and _event_total(event["type"], event["payload"]) == -amount
                and _days_apart(event["business_date"], bank["posted_on"]) <= 3
                and str(event["payload"].get("payment_id", ""))[4:] in bank["reference"]
            ]
            if len(found) == 1:
                add(bank, found, "exact", 1.0)
        elif narration.startswith("IBFT FROM ") and amount > 0:
            found = [
                event
                for event in by_kind["customer_invoice"]
                if event["id"] not in used_events
                and _event_total(event["type"], event["payload"]) == amount
                and event["payload"].get("number", "").upper() in narration
            ]
            if len(found) == 1:
                add(bank, found, "exact", 1.0)

    # Pass 2: customer receipts with several invoices. The party is carried on both the bank
    # line narration and the invoice event, while the total must still reconcile exactly.
    for bank in bank_lines:
        if bank["amount_minor"] <= 0 or not bank["narration"].upper().startswith("IBFT FROM "):
            continue
        if any(candidate.bank_line_id == bank["id"] for candidate in candidates):
            continue
        available = [
            event
            for event in by_kind["customer_invoice"]
            if event["id"] not in used_events and event["business_date"] <= bank["posted_on"]
        ]
        by_party: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for event in available:
            by_party[event["party_id"]].append(event)
        exact_groups = [
            group
            for group in by_party.values()
            if sum(_event_total(event["type"], event["payload"]) for event in group)
            == bank["amount_minor"]
        ]
        if len(exact_groups) == 1:
            add(bank, exact_groups[0], "rule", 0.98)

    # Pass 3: settlement batches. A settlement is the complete unmatched set for its method
    # and branch up to that bank date. Cash deposits allow the generator's documented drawer
    # over/short variance, capped at 2% of the deposit.
    for bank in bank_lines:
        if bank["amount_minor"] <= 0 or any(c.bank_line_id == bank["id"] for c in candidates):
            continue
        narration = bank["narration"].upper()
        methods = _settlement_methods(narration)
        branch = _BRANCH.search(narration)
        if methods is not None:
            found = [
                event
                for event in by_kind["sale"]
                if event["id"] not in used_events
                and event["business_date"] <= bank["posted_on"]
                and event["payload"].get("payment", {}).get("method") in methods
                and (branch is None or event["payload"].get("branch") == branch.group(1))
            ]
            if (
                found
                and sum(_event_total(event["type"], event["payload"]) for event in found)
                == bank["amount_minor"]
            ):
                add(bank, found, "one_to_many", 1.0)
        elif narration.startswith("CASH DEPOSIT ") and branch is not None:
            found = [
                event
                for event in by_kind["sale"]
                if event["id"] not in used_events
                and event["business_date"] < bank["posted_on"]
                and event["payload"].get("payment", {}).get("method") == "cash"
                and event["payload"].get("branch") == branch.group(1)
            ]
            total = sum(_event_total(event["type"], event["payload"]) for event in found)
            allowed_variance = max(1, bank["amount_minor"] * 200 // 10_000)
            if found and abs(total - bank["amount_minor"]) <= allowed_variance:
                add(bank, found, "one_to_many", 0.98)

    # Pass 4: Model/fuzzy matching with deterministic amount verification (Pass 4).
    # Unmatched bank lines are matched against remaining events where line amounts
    # deterministically match the bank settlement, using fuzzy text similarity.
    from rapidfuzz import fuzz

    for bank in bank_lines:
        if any(c.bank_line_id == bank["id"] for c in candidates):
            continue
        narration = bank["narration"].upper()
        reference = bank["reference"].upper()
        amount = bank["amount_minor"]

        if amount > 0:
            for event in by_kind["customer_invoice"]:
                if event["id"] in used_events:
                    continue
                evt_tot = _event_total(event["type"], event["payload"])
                if evt_tot != amount:
                    continue
                if _days_apart(event["business_date"], bank["posted_on"]) > 14:
                    continue
                num = str(event["payload"].get("number", "")).upper()
                party = str(event["payload"].get("party", "")).upper()
                desc = f"{num} {party}".strip()
                score = max(
                    fuzz.partial_ratio(num, narration) if num else 0,
                    fuzz.token_set_ratio(desc, narration) if desc else 0,
                    fuzz.partial_ratio(num, reference) if num and reference else 0,
                )
                if score >= 65:
                    confidence = round(min(0.95, score / 100.0), 2)
                    add(bank, [event], "fuzzy", confidence)
                    break
        elif amount < 0:
            target_types = ["supplier_payment", "purchase_bill"]
            matched_event = None
            best_score = 0
            for k in target_types:
                for event in by_kind[k]:
                    if event["id"] in used_events:
                        continue
                    evt_tot = _event_total(event["type"], event["payload"])
                    if evt_tot != -amount:
                        continue
                    if _days_apart(event["business_date"], bank["posted_on"]) > 14:
                        continue
                    ref = str(
                        event["payload"].get(
                            "payment_id",
                            event["payload"].get("bill_id", event["payload"].get("number", "")),
                        )
                    ).upper()
                    party = str(event.get("party_id") or "").upper()
                    desc = f"{ref} {party}".strip()
                    score = max(
                        fuzz.partial_ratio(ref, narration) if ref else 0,
                        fuzz.token_set_ratio(desc, narration) if desc else 0,
                        fuzz.partial_ratio(ref, reference) if ref and reference else 0,
                    )
                    if score >= 65 and score > best_score:
                        best_score = score
                        matched_event = event
            if matched_event is not None:
                confidence = round(min(0.95, best_score / 100.0), 2)
                add(bank, [matched_event], "fuzzy", confidence)

    return candidates


def run(conn: psycopg.Connection, tenant_id: str, *, now: datetime) -> dict[str, int | str]:
    """Replace this deterministic run's proposals and return its totals."""
    with db.tenant_session(conn, tenant_id):
        # Reruns may refresh unreviewed suggestions only. A confirmed or rejected row is a
        # human decision and remains part of the ledger review record.
        conn.execute("delete from matches where run_id = %s and status = 'proposed'", (RUN_ID,))
        bank_rows = conn.execute(
            "select id, posted_on, narration, reference, amount_minor from bank_lines order by posted_on, line_no"
        ).fetchall()
        event_rows = conn.execute(
            "select id, type, business_date, party_id, payload from events"
            " where type in ('supplier_payment', 'customer_invoice', 'sale', 'purchase_bill') order by business_date, id"
        ).fetchall()
        bank_lines = [
            {
                "id": row[0],
                "posted_on": row[1],
                "narration": row[2],
                "reference": row[3] or "",
                "amount_minor": row[4],
            }
            for row in bank_rows
        ]
        events = [
            {
                "id": row[0],
                "type": row[1],
                "business_date": row[2],
                "party_id": row[3],
                "payload": row[4],
            }
            for row in event_rows
        ]
        candidates = _candidate_matches(bank_lines, events)
        with conn.cursor() as cursor:
            cursor.executemany(
                "insert into matches (tenant_id, match_id, event_id, bank_line_id, run_id, pass, confidence, status, created_at)"
                " values (%s, %s, %s, %s, %s, %s, %s, 'proposed', %s) on conflict do nothing",
                [
                    (
                        tenant_id,
                        _match_id(candidate),
                        event_id,
                        candidate.bank_line_id,
                        RUN_ID,
                        candidate.pass_name,
                        candidate.confidence,
                        now,
                    )
                    for candidate in candidates
                    for event_id in candidate.event_ids
                ],
            )
    by_pass = defaultdict(int)
    for candidate in candidates:
        by_pass[candidate.pass_name] += 1
    return {
        "run_id": RUN_ID,
        "matched_bank_lines": len(candidates),
        "exact": by_pass["exact"],
        "rule": by_pass["rule"],
        "one_to_many": by_pass["one_to_many"],
        "fuzzy": by_pass["fuzzy"],
        "unmatched_bank_lines": len(bank_lines) - len(candidates),
    }


def findings(conn: psycopg.Connection, tenant_id: str, *, now: datetime) -> list[Finding]:
    """Publish every bank line without a proposed or confirmed reconciliation match."""
    with db.tenant_session(conn, tenant_id):
        rows = conn.execute(
            "select b.id, b.posted_on, b.narration, b.amount_minor, b.currency"
            " from bank_lines b where not exists ("
            " select 1 from matches m where m.bank_line_id = b.id"
            " and m.status in ('proposed', 'confirmed'))"
            " order by b.posted_on, b.line_no"
        ).fetchall()
    created_at = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        Finding(
            id=f"fnd_reconcile_{row[0][4:]}",
            source="reconciliation",
            type="unmatched_bank_line",
            severity="medium",
            title="Bank line needs reconciliation",
            detail=f"{row[1].isoformat()}: {row[2]}",
            money_at_stake=Money(minor=abs(row[3]), currency=row[4]),
            evidence=[Evidence(kind="bank_line", ref=row[0])],
            actions=[Action(label="Review reconciliation", route="/audit")],
            created_at=created_at,
            dedupe_key=f"reconciliation:{row[0]}",
        )
        for row in rows
    ]
