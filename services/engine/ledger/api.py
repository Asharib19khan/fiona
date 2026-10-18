"""Ledger, import, wallet and audit endpoints (D3, D6). The tenant always comes from the server (R15).

Every response carries api_version "v1". Wallet responses say SIMULATED: no real money moves.
"""

from __future__ import annotations

import base64
import io
import tempfile
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from engine.app import clock, guardian_notify
from engine.app.errors import ApiError
from engine.app.tenancy import CurrentActor, TenantId
from engine.ledger import (
    bill_checks,
    db,
    importers,
    mandates,
    participation,
    pos_reconcile,
    proposals,
    reconcile,
    review,
)
from engine.wallet.audit import verify
from engine.wallet.oplog import export_operation_log
from engine.wallet.wallet import PaymentRequest, execute_payment
from fiona_contracts.models import DecisionRequest, Finding

router = APIRouter(tags=["ledger"])


def get_conn() -> Iterator[psycopg.Connection]:
    with db.connect(autocommit=True) as conn:
        yield conn


def get_clock() -> datetime:
    """The engine clock (FIONA_NOW pins it). Tests override this dependency; logic never calls
    now() itself."""
    return clock.now()


Conn = Annotated[psycopg.Connection, Depends(get_conn)]
Clock = Annotated[datetime, Depends(get_clock)]


class ImportResponse(BaseModel):
    api_version: str = "v1"
    inserted: int
    skipped: int
    errors: list[dict[str, Any]]


async def _csv(request: Request) -> str:
    """CSV files are posted as the raw request body (Content-Type: text/csv), UTF-8."""
    try:
        return (await request.body()).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ApiError(400, "invalid_file", "Files must be UTF-8 CSV.") from exc


@router.post("/v1/import/bank", response_model=ImportResponse)
async def import_bank(
    request: Request,
    tenant_id: TenantId,
    conn: Conn,
    now: Clock,
    file_name: str = "bank_statement.csv",
) -> ImportResponse:
    result = importers.import_bank_csv(
        conn, tenant_id, await _csv(request), file_name=file_name, now=now
    )
    return ImportResponse(**result.as_dict())


@router.post("/v1/import/pos", response_model=ImportResponse)
async def import_pos(
    request: Request, tenant_id: TenantId, conn: Conn, now: Clock, file_name: str = "pos_sales.csv"
) -> ImportResponse:
    result = importers.import_pos_csv(
        conn, tenant_id, await _csv(request), file_name=file_name, now=now
    )
    return ImportResponse(**result.as_dict())


class BillsImport(BaseModel):
    bills: list[dict[str, Any]] = Field(description="Extracted bills (FORMATS.md 3.7)")
    documents: dict[str, str] = Field(
        description="document_path -> base64 bytes; the SHA-256 is checked"
    )


@router.post("/v1/import/bills", response_model=ImportResponse)
def import_bills(tenant_id: TenantId, conn: Conn, now: Clock, body: BillsImport) -> ImportResponse:
    try:
        documents = {
            path: base64.b64decode(data, validate=True) for path, data in body.documents.items()
        }
    except ValueError as exc:
        raise ApiError(400, "invalid_document", "documents must be base64.") from exc
    result = importers.import_bills(
        conn, tenant_id, body.bills, documents, storage_prefix=f"uploads/{tenant_id}", now=now
    )
    return ImportResponse(**result.as_dict())


class EventsResponse(BaseModel):
    api_version: str = "v1"
    events: list[dict[str, Any]]
    next_offset: int | None


@router.get("/v1/ledger/events", response_model=EventsResponse)
def ledger_events(
    tenant_id: TenantId,
    conn: Conn,
    type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> EventsResponse:
    with db.tenant_session(conn, tenant_id):
        rows = conn.execute(
            "select id, type, occurred_at, business_date, currency, party_id, payload, source from events"
            " where (%(type)s::text is null or type = %(type)s)"
            " and (%(from)s::date is null or business_date >= %(from)s)"
            " and (%(to)s::date is null or business_date <= %(to)s)"
            " order by occurred_at, id limit %(limit)s offset %(offset)s",
            {"type": type, "from": date_from, "to": date_to, "limit": limit + 1, "offset": offset},
        ).fetchall()
    events = [
        {
            "id": r[0],
            "tenant_id": tenant_id,
            "event": r[1],
            "occurred_at": r[2].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date": r[3].isoformat(),
            "currency": r[4],
            "party_id": r[5],
            **r[6],
            "source": r[7],
        }
        for r in rows[:limit]
    ]
    return EventsResponse(events=events, next_offset=offset + limit if len(rows) > limit else None)


class ReconcileRunResponse(BaseModel):
    api_version: str = "v1"
    run_id: str
    matched_bank_lines: int
    unmatched_bank_lines: int
    exact: int
    rule: int
    one_to_many: int
    fuzzy: int = 0


class ReconcileMatch(BaseModel):
    match_id: str
    bank_line_id: str
    event_ids: list[str]
    pass_name: str
    confidence: float
    status: str


class ReconcileMatchesResponse(BaseModel):
    api_version: str = "v1"
    matches: list[ReconcileMatch]


class ReconcileFindingsResponse(BaseModel):
    api_version: str = "v1"
    ranked_by: str = "money_at_stake"
    findings: list[Finding]


class BillCheckResponse(BaseModel):
    api_version: str = "v1"
    bill_id: str
    check: dict[str, Any]


class BillCheckRequest(BaseModel):
    bill_id: str = Field(min_length=1)


@router.post("/v1/reconcile/run", response_model=ReconcileRunResponse)
def reconcile_run(tenant_id: TenantId, conn: Conn, now: Clock) -> ReconcileRunResponse:
    """Run conservative deterministic matching; proposals require review before posting."""
    return ReconcileRunResponse(**reconcile.run(conn, tenant_id, now=now))


@router.post("/v1/reconcile/pos", response_model=pos_reconcile.POSReconcileResponse)
def reconcile_pos(
    tenant_id: TenantId, conn: Conn, now: Clock
) -> pos_reconcile.POSReconcileResponse:
    """Run POS sales register reconciliation against cash deposits and acquirer settlements."""
    return pos_reconcile.POSReconcileResponse(
        **pos_reconcile.run_pos_reconciliation(conn, tenant_id, now=now)
    )


@router.get("/v1/reconcile/matches", response_model=ReconcileMatchesResponse)
def reconcile_matches(tenant_id: TenantId, conn: Conn) -> ReconcileMatchesResponse:
    with db.tenant_session(conn, tenant_id):
        rows = conn.execute(
            "select match_id, bank_line_id, array_agg(event_id order by event_id), pass, confidence, status"
            " from matches group by match_id, bank_line_id, pass, confidence, status"
            " order by bank_line_id, match_id"
        ).fetchall()
    return ReconcileMatchesResponse(
        matches=[
            ReconcileMatch(
                match_id=row[0],
                bank_line_id=row[1],
                event_ids=row[2],
                pass_name=row[3],
                confidence=float(row[4]),
                status=row[5],
            )
            for row in rows
        ]
    )


@router.get("/v1/reconcile/findings", response_model=ReconcileFindingsResponse)
def reconcile_findings(
    tenant_id: TenantId,
    conn: Conn,
    now: Clock,
    limit: int | None = Query(default=None, ge=1, le=10_000),
) -> ReconcileFindingsResponse:
    """Read-only findings for bank lines that still need reconciliation review, largest first.
    `limit` keeps the top ones (a briefing needs a few, not thousands)."""
    findings = reconcile.findings(conn, tenant_id, now=now)
    ranked = sorted(findings, key=lambda finding: finding.money_at_stake.minor, reverse=True)
    return ReconcileFindingsResponse(findings=ranked[:limit] if limit else ranked)


@router.post("/v1/bills/check", response_model=BillCheckResponse)
def bill_check(
    tenant_id: TenantId, conn: Conn, now: Clock, body: BillCheckRequest
) -> BillCheckResponse:
    """Run the read-only Guardian duplicate-bill check (G-05) for an imported bill."""
    check = bill_checks.duplicate_bill_check(conn, tenant_id, body.bill_id, now=now)
    if check is None:
        raise ApiError(404, "bill_not_found", "No imported bill exists for this bill_id.")
    return BillCheckResponse(bill_id=body.bill_id, check=check)


@router.get("/v1/mandates")
def get_mandates(tenant_id: TenantId, conn: Conn) -> dict[str, Any]:
    """Each agent's mandate in force: autonomy per action, caps, and the system ceiling."""
    return mandates.list_mandates(conn, tenant_id)


class AutonomyChange(BaseModel):
    action_type: str = Field(pattern=r"^[a-z_]{3,40}$")
    level: str


@router.post("/v1/mandates/{agent}/autonomy")
def change_autonomy(
    tenant_id: TenantId,
    actor: CurrentActor,
    conn: Conn,
    now: Clock,
    agent: str,
    body: AutonomyChange,
) -> dict[str, Any]:
    """The owner raises or lowers an agent's autonomy for one action type (a new version)."""
    if actor.role != "owner":
        raise ApiError(403, "owner_only", "Only the owner can change a mandate.")
    return mandates.set_autonomy(
        conn, tenant_id, agent, body.action_type, body.level, changed_by=actor.id, now=now
    )


@router.get("/v1/bills/{bill_id}")
def get_bill(tenant_id: TenantId, conn: Conn, bill_id: str) -> dict[str, Any]:
    """One imported bill as the ledger recorded it, with what has been paid against it."""
    with db.tenant_session(conn, tenant_id):
        row = conn.execute(
            "select id, business_date, party_id, currency, payload from events"
            " where type = 'purchase_bill' and payload->>'bill_id' = %s"
            " order by business_date desc, id desc limit 1",
            (bill_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "bill_not_found", "No imported bill exists for this bill_id.")
        paid = conn.execute(
            "select coalesce(sum((payload->>'amount_minor')::bigint), 0) from events"
            " where type = 'supplier_payment' and payload->>'bill_id' = %s",
            (bill_id,),
        ).fetchone()[0]
    payload = row[4] or {}
    total = int(payload.get("total_minor") or 0)
    return {
        "api_version": "v1",
        "bill": {
            "bill_id": bill_id,
            "event_id": row[0],
            "posted_on": row[1].isoformat(),
            "supplier_id": payload.get("party") or payload.get("supplier_id") or row[2],
            "number": payload.get("number"),
            "issue_date": payload.get("issue_date"),
            "due_date": payload.get("due_date"),
            "total": {"minor": total, "currency": row[3]},
            "paid": {"minor": int(paid), "currency": row[3]},
            "open": {"minor": max(0, total - int(paid)), "currency": row[3]},
            "document_id": payload.get("document_id"),
            "po_number": payload.get("po_number"),
            "category": payload.get("category"),
        },
    }


class PayRequest(BaseModel):
    proposal_id: str = Field(pattern=r"^prop_[A-Za-z0-9_]+$")
    verdict_id: str = Field(pattern=r"^vrd_[A-Za-z0-9_]+$")
    payee_id: str
    amount_minor: int = Field(ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    pay_on: date


class PayResponse(BaseModel):
    api_version: str = "v1"
    label: str = "SIMULATED"
    status: str
    reason: str | None = None
    payment_id: str | None = None
    wallet_ref: str | None = None
    event_id: str | None = None


@router.post("/v1/wallet/pay", response_model=PayResponse)
def wallet_pay(tenant_id: TenantId, conn: Conn, now: Clock, body: PayRequest) -> PayResponse:
    """Pays only a cleared proposal; every attempt is audited. SIMULATED: no real money moves."""
    result = execute_payment(
        conn,
        tenant_id,
        PaymentRequest(
            proposal_id=body.proposal_id,
            verdict_id=body.verdict_id,
            payee_id=body.payee_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
            pay_on=body.pay_on.isoformat(),
        ),
        now=now,
    )
    return PayResponse(
        status=result.status,
        reason=result.reason,
        payment_id=result.payment_id,
        wallet_ref=result.wallet_ref,
        event_id=result.event_id,
    )


class AuditResponse(BaseModel):
    api_version: str = "v1"
    verified: bool
    chain_length: int
    first_bad_seq: int | None
    records: list[dict[str, Any]]


@router.get("/v1/audit", response_model=AuditResponse)
def audit(tenant_id: TenantId, conn: Conn, proposal_id: str | None = None) -> AuditResponse:
    """The tenant's hash chain is always verified in full; `proposal_id` only filters the records shown."""
    with db.tenant_session(conn, tenant_id):
        result = verify(conn, tenant_id)
        rows = conn.execute(
            "select seq, prev_hash, record, hash, proposal_id, recorded_at from audit_log"
            " where %(p)s::text is null or proposal_id = %(p)s order by seq",
            {"p": proposal_id},
        ).fetchall()
    records = [
        {
            "seq": r[0],
            "prev_hash": r[1],
            "record": r[2],
            "hash": r[3],
            "proposal_id": r[4],
            "recorded_at": r[5].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for r in rows
    ]
    return AuditResponse(
        verified=result.ok,
        chain_length=result.length,
        first_bad_seq=result.first_bad_seq,
        records=records,
    )


@router.get("/v1/audit/export", response_class=Response)
def audit_export(tenant_id: TenantId, conn: Conn) -> Response:
    """Download a tenant-scoped, verified execution-evidence bundle."""
    with tempfile.TemporaryDirectory(prefix="fiona-audit-") as directory:
        with db.tenant_session(conn, tenant_id):
            export_operation_log(conn, tenant_id, directory)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in (
                "operations.jsonl",
                "audit_chain.jsonl",
                "verification_report.json",
                "README.md",
            ):
                with open(f"{directory}/{name}", "rb") as source:
                    bundle.writestr(name, source.read())
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="fiona-execution-evidence.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/v1/proposals")
def list_proposals(
    tenant_id: TenantId,
    conn: Conn,
    needs_owner: bool = False,
) -> dict[str, Any]:
    """List proposals for the tenant, projected with current status and verdict."""
    results = proposals.list_proposals(conn, tenant_id, needs_owner=needs_owner)
    return {"api_version": "v1", "proposals": results}


@router.get("/v1/proposals/{proposal_id}")
def get_proposal(
    tenant_id: TenantId,
    conn: Conn,
    proposal_id: str,
) -> dict[str, Any]:
    """Get single proposal by ID with its verdict and decision history."""
    item = proposals.get_proposal(conn, tenant_id, proposal_id)
    if not item:
        raise ApiError(404, "not_found", f"No proposal matches ID: {proposal_id}")
    return {"api_version": "v1", **item}


@router.post("/v1/proposals", status_code=201)
def create_proposal(
    tenant_id: TenantId,
    actor: CurrentActor,
    conn: Conn,
    now: Clock,
    body: dict[str, Any],
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="idempotency-key"),
) -> dict[str, Any]:
    """Store an agent proposal, run Guardian checks, and append to audit log.

    The proposer is the verified caller, never the body: an agent proposes only as itself, so
    the maker-checker rule (G-04) cannot be dodged by naming someone else as the maker.
    """
    if actor.role == "guardian":
        raise ApiError(
            403, "guardian_never_acts", "The Guardian reviews proposals; it never makes one."
        )
    if not actor.is_person and body.get("agent") != actor.id:
        raise ApiError(403, "wrong_agent", f"{actor.id} can only submit its own proposals.")
    body = {
        **body,
        "created_by": {"kind": "user" if actor.is_person else "agent", "id": actor.id},
    }
    prop, verdict = proposals.create_proposal(
        conn, tenant_id, body, now=now, idempotency_key=idempotency_key
    )
    background.add_task(guardian_notify.request_review, tenant_id, prop["id"])
    return {"api_version": "v1", "proposal": prop, "verdict": verdict}


@router.post("/v1/proposals/{proposal_id}/request-review", status_code=202)
def request_guardian_review(
    tenant_id: TenantId, actor: CurrentActor, conn: Conn, proposal_id: str
) -> dict[str, Any]:
    """A person asks the Guardian to review a proposal again (for example after an outage)."""
    if not actor.is_person:
        raise ApiError(403, "people_only", "Only the owner or finance team can ask for a review.")
    if proposals.get_proposal(conn, tenant_id, proposal_id) is None:
        raise ApiError(404, "not_found", f"No proposal found with ID: {proposal_id}")
    if not guardian_notify.enabled():
        raise ApiError(503, "guardian_not_configured", "The Guardian service is not configured.")
    requested = guardian_notify.request_review(tenant_id, proposal_id)
    if not requested:
        raise ApiError(503, "guardian_unavailable", "The Guardian did not accept the review.")
    return {"api_version": "v1", "status": "accepted", "proposal_id": proposal_id}


class GuardianReview(BaseModel):
    """The adversarial reviewer's answer (rulebook/guardian.yaml G-12 output_schema), or an error.

    The engine turns it into the G-12 check and sets the outcome itself. The answer fields are
    loose on purpose: a malformed answer is recorded as a CHECK_ERROR escalation, not rejected,
    so a bad model output can never leave a proposal unreviewed.
    """

    reviewed_verdict_id: str = Field(pattern=r"^vrd_[A-Za-z0-9]+$")
    concern: Any = None
    reasons: Any = None
    injection_detected: Any = None
    error: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=80)
    prompt_version: str | None = Field(default=None, max_length=80)
    latency_ms: int | None = Field(default=None, ge=0)


def _guardian_only(actor: Any) -> None:
    if actor.role != "guardian":
        raise ApiError(403, "guardian_only", "Only the Guardian service can do this.")


@router.get("/v1/proposals/{proposal_id}/review-packet")
def proposal_review_packet(
    tenant_id: TenantId, actor: CurrentActor, conn: Conn, proposal_id: str
) -> dict[str, Any]:
    """What the adversarial reviewer may see (G-12): no agent reasoning, documents as data."""
    _guardian_only(actor)
    return review.review_packet(conn, tenant_id, proposal_id)


@router.post("/v1/proposals/{proposal_id}/review")
def proposal_review(
    tenant_id: TenantId,
    actor: CurrentActor,
    conn: Conn,
    now: Clock,
    proposal_id: str,
    body: GuardianReview,
) -> dict[str, Any]:
    """Record the Guardian's review as a new verdict chained to the one it reviewed."""
    _guardian_only(actor)
    return review.record_review(
        conn,
        tenant_id,
        proposal_id,
        body.reviewed_verdict_id,
        body.model_dump(exclude={"reviewed_verdict_id"}),
        now=now,
    )


@router.post("/v1/proposals/{proposal_id}/decision")
@router.post("/v1/proposals/{proposal_id}/decide")
def decide_proposal(
    tenant_id: TenantId,
    actor: CurrentActor,
    conn: Conn,
    now: Clock,
    proposal_id: str,
    body: DecisionRequest,
    idempotency_key: str | None = Header(default=None, alias="idempotency-key"),
) -> dict[str, Any]:
    """Record a person's decision (approve or reject) on a proposal. Agents never decide."""
    if not actor.is_person:
        raise ApiError(403, "agents_cannot_decide", "Only the owner or finance team can decide.")
    return proposals.record_owner_decision(
        conn,
        tenant_id,
        proposal_id,
        body,
        decided_by=actor.id,
        now=now,
        idempotency_key=idempotency_key,
    )


@router.post("/v1/participation/run")
def run_participation(
    tenant_id: TenantId,
    actor: CurrentActor,
    conn: Conn,
    now: Clock,
    body: dict[str, Any],
    background: BackgroundTasks,
) -> dict[str, Any]:
    """Execute end-to-end participation loop: bill intake -> proposal -> guardian -> execution -> audit.

    An owner approval in the body counts only from a person, and always as that person.
    """
    bill = body.get("bill") or body
    owner_approval = body.get("owner_approval")
    if owner_approval is not None:
        if not actor.is_person:
            raise ApiError(
                403, "agents_cannot_decide", "Only the owner or finance team can decide."
            )
        owner_approval = {**owner_approval, "decided_by": actor.id}
    res = participation.run_full_participation_loop(
        conn,
        tenant_id,
        bill,
        owner_approval=owner_approval,
        now=now,
    )
    if owner_approval is None and res.get("proposal", {}).get("id"):
        background.add_task(guardian_notify.request_review, tenant_id, res["proposal"]["id"])
    return {"api_version": "v1", **res}
