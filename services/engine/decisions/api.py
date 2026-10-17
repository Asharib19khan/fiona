"""Decision endpoints: debt or equity and dividend (Y4), payment timing (Y8)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from engine.app.errors import ApiError
from engine.app.tenancy import TenantId
from engine.decisions.debt_equity import compare_debt_equity
from engine.decisions.dividend import compare_dividend
from engine.decisions.schemas import (
    DebtEquityRequest,
    DecisionResponse,
    DividendRequest,
    PaymentTimingRequest,
    PaymentTimingResponse,
)
from engine.forecast.deps import mode, not_live_yet, require_mock_tenant
from engine.forecast.ledger_source import TenantDataMissing, load_fixture_snapshot
from engine.forecast.mocks.registry import load

router = APIRouter(tags=["decisions"])


@router.post("/v1/decisions/debt-equity", response_model=DecisionResponse)
def debt_equity(request: Request, tenant_id: TenantId, body: DebtEquityRequest) -> DecisionResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y4", "Sat 17 Oct")
    try:
        snapshot = load_fixture_snapshot(tenant_id)
    except TenantDataMissing:
        require_mock_tenant(tenant_id)
        return load("decision_debt_equity")
    if body.as_of is not None and body.as_of != snapshot.as_of:
        raise ApiError(
            422,
            "unsupported_as_of",
            "Debt-versus-equity comparison is available for the fixture's current snapshot date.",
            {"available_as_of": snapshot.as_of.isoformat()},
        )
    if body.amount.currency != snapshot.currency:
        raise ApiError(
            422,
            "invalid_decision_request",
            f"amount must be in {snapshot.currency}",
            {"currency": snapshot.currency},
        )
    return compare_debt_equity(body, snapshot, mode=mode(request), generated_at=datetime.now(UTC))


@router.post("/v1/decisions/dividend", response_model=DecisionResponse)
def dividend(request: Request, tenant_id: TenantId, body: DividendRequest) -> DecisionResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y4", "Sat 17 Oct")
    try:
        snapshot = load_fixture_snapshot(tenant_id)
    except TenantDataMissing:
        require_mock_tenant(tenant_id)
        return load("decision_dividend")
    if body.as_of is not None and body.as_of != snapshot.as_of:
        raise ApiError(
            422,
            "unsupported_as_of",
            "Dividend decision comparison is available for the fixture's current snapshot date.",
            {"available_as_of": snapshot.as_of.isoformat()},
        )
    if body.proposed_dividend is not None and body.proposed_dividend.currency != snapshot.currency:
        raise ApiError(
            422,
            "invalid_decision_request",
            f"proposed_dividend must be in {snapshot.currency}",
            {"currency": snapshot.currency},
        )
    return compare_dividend(body, snapshot, mode=mode(request), generated_at=datetime.now(UTC))


@router.post("/v1/decisions/payment-timing", response_model=PaymentTimingResponse)
def payment_timing(
    request: Request, tenant_id: TenantId, body: PaymentTimingRequest
) -> PaymentTimingResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y8", "Sun 18 Oct")
    require_mock_tenant(tenant_id)
    return load("payment_timing")
