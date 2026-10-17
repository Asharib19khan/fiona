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
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from engine.app.errors import ApiError
from engine.app.tenancy import TenantId
from engine.ledger import (
    bill_checks,
    db,
    importers,
    participation,
    pos_reconcile,
    proposals,
    reconcile,
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
    """The engine clock. Tests override this dependency; logic never calls now() itself."""
    return datetime.now(UTC)


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
def reconcile_findings(tenant_id: TenantId, conn: Conn, now: Clock) -> ReconcileFindingsResponse:
    """Read-only findings for bank lines that still need reconciliation review."""
    findings = reconcile.findings(conn, tenant_id, now=now)
    return ReconcileFindingsResponse(
        findings=sorted(findings, key=lambda finding: finding.money_at_stake.minor, reverse=True)
    )


@router.post("/v1/bills/check", response_model=BillCheckResponse)
def bill_check(
    tenant_id: TenantId, conn: Conn, now: Clock, body: BillCheckRequest
) -> BillCheckResponse:
    """Run the read-only Guardian duplicate-bill check (G-05) for an imported bill."""
    check = bill_checks.duplicate_bill_check(conn, tenant_id, body.bill_id, now=now)
    if check is None:
        raise ApiError(404, "bill_not_found", "No imported bill exists for this bill_id.")
    return BillCheckResponse(bill_id=body.bill_id, check=check)


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
    conn: Conn,
    now: Clock,
    body: dict[str, Any],
    idempotency_key: str | None = Header(default=None, alias="idempotency-key"),
) -> dict[str, Any]:
    """Store an agent proposal, run Guardian checks, and append to audit log."""
    prop, verdict = proposals.create_proposal(
        conn, tenant_id, body, now=now, idempotency_key=idempotency_key
    )
    return {"api_version": "v1", "proposal": prop, "verdict": verdict}


@router.post("/v1/proposals/{proposal_id}/decision")
@router.post("/v1/proposals/{proposal_id}/decide")
def decide_proposal(
    tenant_id: TenantId,
    conn: Conn,
    now: Clock,
    proposal_id: str,
    body: DecisionRequest,
    decided_by: str = Header(default="usr_owner", alias="x-user-id"),
    idempotency_key: str | None = Header(default=None, alias="idempotency-key"),
) -> dict[str, Any]:
    """Record an owner decision (approve or reject) for an escalated proposal."""
    return proposals.record_owner_decision(
        conn,
        tenant_id,
        proposal_id,
        body,
        decided_by=decided_by,
        now=now,
        idempotency_key=idempotency_key,
    )


@router.post("/v1/participation/run")
def run_participation(
    tenant_id: TenantId,
    conn: Conn,
    now: Clock,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Execute end-to-end participation loop: bill intake -> proposal -> guardian -> execution -> audit."""
    bill = body.get("bill") or body
    owner_approval = body.get("owner_approval")
    res = participation.run_full_participation_loop(
        conn,
        tenant_id,
        bill,
        owner_approval=owner_approval,
        now=now,
    )
    return {"api_version": "v1", **res}
