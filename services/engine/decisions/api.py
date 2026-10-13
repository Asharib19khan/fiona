"""Decision endpoints: debt or equity and dividend (Y4), payment timing (Y8)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from engine.decisions.schemas import (
    DebtEquityRequest,
    DecisionResponse,
    DividendRequest,
    PaymentTimingRequest,
    PaymentTimingResponse,
)
from engine.forecast.deps import mode, not_live_yet, require_mock_tenant
from engine.forecast.mocks.registry import load

router = APIRouter(tags=["decisions"])


@router.post("/v1/decisions/debt-equity", response_model=DecisionResponse)
def debt_equity(request: Request, body: DebtEquityRequest) -> DecisionResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y4", "Sat 17 Oct")
    require_mock_tenant(body.tenant_id)
    return load("decision_debt_equity")


@router.post("/v1/decisions/dividend", response_model=DecisionResponse)
def dividend(request: Request, body: DividendRequest) -> DecisionResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y4", "Sat 17 Oct")
    require_mock_tenant(body.tenant_id)
    return load("decision_dividend")


@router.post("/v1/decisions/payment-timing", response_model=PaymentTimingResponse)
def payment_timing(request: Request, body: PaymentTimingRequest) -> PaymentTimingResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y8", "Sun 18 Oct")
    require_mock_tenant(body.tenant_id)
    return load("payment_timing")
