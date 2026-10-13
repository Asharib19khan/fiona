"""Forecast endpoints: cash forecast (Y1), findings feed (Y6), inventory (Y3), Launch Lab (Y5)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request

from engine.forecast.cash.schemas import CashForecastResponse
from engine.forecast.deps import mode, not_live_yet, require_mock_tenant
from engine.forecast.feed.schemas import FindingsResponse
from engine.forecast.inventory.schemas import InventoryAnalysisResponse
from engine.forecast.launch_lab.schemas import LaunchLabRequest, LaunchLabResponse
from engine.forecast.mocks.registry import load

router = APIRouter(tags=["forecast"])


@router.get("/v1/forecast/cash", response_model=CashForecastResponse)
def cash_forecast(
    request: Request, tenant_id: str = Query(...), weeks: int = Query(13, ge=1, le=26)
) -> CashForecastResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y1", "Fri 16 Oct")
    require_mock_tenant(tenant_id)
    result = load("cash_forecast")
    if weeks == result.horizon_weeks:
        return result
    return result.model_copy(
        update={"horizon_weeks": min(weeks, 13), "weeks": result.weeks[:weeks]}
    )


@router.get("/v1/forecast/findings", response_model=FindingsResponse)
def findings(request: Request, tenant_id: str = Query(...)) -> FindingsResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y6", "Sat 17 Oct")
    require_mock_tenant(tenant_id)
    return load("findings")


@router.get("/v1/inventory/analysis", response_model=InventoryAnalysisResponse)
def inventory_analysis(request: Request, tenant_id: str = Query(...)) -> InventoryAnalysisResponse:
    if mode(request) != "mock":
        raise not_live_yet("Y3", "Mon 19 Oct")
    require_mock_tenant(tenant_id)
    return load("inventory_analysis")


@router.post("/v1/launch-lab/simulate", response_model=LaunchLabResponse)
def launch_lab_simulate(request: Request, body: LaunchLabRequest) -> LaunchLabResponse:
    """Mock mode returns the winter-shawl run for any valid request, stamped now."""
    if mode(request) != "mock":
        raise not_live_yet("Y5", "Mon 19 Oct")
    require_mock_tenant(body.tenant_id)
    return load("launch_lab_winter_shawl").model_copy(update={"generated_at": datetime.now(UTC)})
