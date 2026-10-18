"""Decision endpoints: debt or equity and dividend (Y4), payment timing (Y8)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from engine.app.errors import ApiError
from engine.app.tenancy import TenantId
from engine.decisions.debt_equity import compare_debt_equity
from engine.decisions.dividend import compare_dividend
from engine.decisions.payment_timing_live import live_payment_timing
from engine.decisions.schemas import (
    DebtEquityRequest,
    DecisionResponse,
    DividendRequest,
    PaymentTimingRequest,
    PaymentTimingResponse,
)
from engine.forecast.cash.engine import forecast_cash
from engine.forecast.deps import mode, require_mock_tenant
from engine.forecast.ledger_source import TenantDataMissing, load_ledger_snapshot, load_snapshot
from engine.forecast.mocks.registry import load

router = APIRouter(tags=["decisions"])


@router.post("/v1/decisions/debt-equity", response_model=DecisionResponse)
def debt_equity(request: Request, tenant_id: TenantId, body: DebtEquityRequest) -> DecisionResponse:
    try:
        snapshot = load_snapshot(tenant_id, mode(request))
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
    try:
        snapshot = load_snapshot(tenant_id, mode(request))
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
    """Mock mode: the labelled fixture. Live mode: every open bill against the live forecast."""
    run_mode = mode(request)
    if run_mode == "mock":
        require_mock_tenant(tenant_id)
        return load("payment_timing")
    from engine.ledger import db

    with db.connect(autocommit=True) as conn:
        snapshot = load_ledger_snapshot(conn, tenant_id)
        with db.tenant_session(conn, tenant_id):
            names = dict(conn.execute("select id, name from parties").fetchall())
    cash = forecast_cash(
        snapshot, weeks=body.horizon_weeks, mode=run_mode, generated_at=datetime.now(UTC)
    )
    return live_payment_timing(body, snapshot, cash, names, mode=run_mode)
