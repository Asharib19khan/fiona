"""Financing endpoint: option matching (Y10)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from engine.app.errors import ApiError
from engine.app.tenancy import TenantId
from engine.financing.business import business_figures
from engine.financing.matcher import match_financing
from engine.financing.schemas import FinancingMatchRequest, FinancingMatchResponse
from engine.forecast.deps import mode, not_live_yet, require_mock_tenant
from engine.forecast.ledger_source import TenantDataMissing, load_fixture_snapshot
from engine.forecast.mocks.registry import load

router = APIRouter(tags=["financing"])


@router.post("/v1/financing/match", response_model=FinancingMatchResponse)
def financing_match(
    request: Request, tenant_id: TenantId, body: FinancingMatchRequest
) -> FinancingMatchResponse:
    run_mode = mode(request)
    if run_mode != "mock":
        raise not_live_yet("Y10", "Fri 16 Oct")

    try:
        snapshot = load_fixture_snapshot(tenant_id)
    except TenantDataMissing:
        require_mock_tenant(tenant_id)
        return load("financing_match")

    if body.as_of is not None and body.as_of != snapshot.as_of:
        raise ApiError(
            422,
            "unsupported_as_of",
            "Financing matching is available for the fixture's current snapshot date.",
            {"available_as_of": snapshot.as_of.isoformat()},
        )
    if body.amount.currency != snapshot.currency:
        raise ApiError(
            422,
            "invalid_financing_request",
            f"amount must be in {snapshot.currency}",
            {"currency": snapshot.currency},
        )

    try:
        from engine.ledger import db

        with db.connect(autocommit=True) as conn:
            biz = business_figures(snapshot, conn=conn, tenant_id=tenant_id)
    except Exception:
        biz = business_figures(snapshot, tenant_id=tenant_id)

    return match_financing(
        body,
        biz,
        tenant_id=tenant_id,
        as_of=snapshot.as_of,
        mode=run_mode,
        generated_at=datetime.now(UTC),
    )
