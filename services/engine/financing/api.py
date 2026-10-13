"""Financing endpoint: option matching (Y10)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from engine.financing.schemas import FinancingMatchRequest, FinancingMatchResponse
from engine.forecast.deps import mode, not_live_yet, require_mock_tenant
from engine.forecast.mocks.registry import load

router = APIRouter(tags=["financing"])


@router.post("/v1/financing/match", response_model=FinancingMatchResponse)
def financing_match(request: Request, body: FinancingMatchRequest) -> FinancingMatchResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y10", "Fri 16 Oct")
    require_mock_tenant(body.tenant_id)
    return load("financing_match")
