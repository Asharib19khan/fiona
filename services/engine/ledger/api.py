"""Ledger, import, wallet and audit endpoints (D3, D6). The tenant always comes from the server (R15).

Every response carries api_version "v1". Wallet responses say SIMULATED: no real money moves.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from engine.app.errors import ApiError
from engine.app.tenancy import TenantId
from engine.ledger import db, importers
from engine.wallet.audit import verify
from engine.wallet.wallet import PaymentRequest, execute_payment

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
            "select id, type, occurred_at, business_date, currency, payload, source from events"
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
            **r[5],
            "source": r[6],
        }
        for r in rows[:limit]
    ]
    return EventsResponse(events=events, next_offset=offset + limit if len(rows) > limit else None)


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
