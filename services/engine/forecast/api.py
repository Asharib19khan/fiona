"""Forecast endpoints: cash forecast (Y1), findings feed (Y6), inventory (Y3), Launch Lab (Y5)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request

from engine.app.tenancy import TenantId
from engine.forecast.cash.engine import forecast_cash
from engine.forecast.cash.schemas import CashForecastResponse
from engine.forecast.deps import mode, require_mock_tenant
from engine.forecast.feed.rank import rank_findings
from engine.forecast.feed.schemas import FindingsResponse, SourceStatus
from engine.forecast.inventory.schemas import InventoryAnalysisResponse
from engine.forecast.launch_lab.schemas import LaunchLabRequest, LaunchLabResponse
from engine.forecast.ledger_source import TenantDataMissing, load_fixture_snapshot
from engine.forecast.mocks.registry import load

router = APIRouter(tags=["forecast"])


def _cash(request: Request, tenant_id: str, weeks: int) -> CashForecastResponse:
    """The real Y1 engine on the tenant's ledger fixtures; the static mock only if there are none."""
    try:
        snapshot = load_fixture_snapshot(tenant_id)
    except TenantDataMissing:
        require_mock_tenant(tenant_id)
        result = load("cash_forecast")
        return result.model_copy(
            update={"horizon_weeks": min(weeks, 13), "weeks": result.weeks[:weeks]}
        )
    return forecast_cash(snapshot, weeks=weeks, mode=mode(request), generated_at=datetime.now(UTC))


@router.get("/v1/forecast/cash", response_model=CashForecastResponse)
def cash_forecast(
    request: Request, tenant_id: TenantId, weeks: int = Query(13, ge=1, le=26)
) -> CashForecastResponse:
    return _cash(request, tenant_id, weeks)


@router.get("/v1/forecast/findings", response_model=FindingsResponse)
def findings(request: Request, tenant_id: TenantId) -> FindingsResponse:
    """Cash findings from the Y1 engine; inventory and Launch Lab stay mocks until Y3/Y5."""
    cash = _cash(request, tenant_id, 13)
    if cash.method.name == "mock_fixture":
        return load("findings")
    feed = load("findings")
    others = [f for f in feed.findings if f.source != "forecast"]
    return FindingsResponse(
        mode=mode(request),
        tenant_id=tenant_id,
        generated_at=datetime.now(UTC),
        findings=rank_findings([*cash.findings, *others]),
        sources=[
            SourceStatus(
                source="forecast", status="ok", run_id=cash.run_id, generated_at=cash.generated_at
            ),
            SourceStatus(
                source="inventory", status="ok", note="mock fixture until Y3 (Mon 19 Oct)"
            ),
            SourceStatus(
                source="launch_lab", status="ok", note="mock fixture until Y5 (Mon 19 Oct)"
            ),
            SourceStatus(
                source="financing",
                status="unavailable",
                note="Y10 publishes findings from Fri 16 Oct.",
            ),
        ],
    )


@router.get("/v1/inventory/analysis", response_model=InventoryAnalysisResponse)
def inventory_analysis(request: Request, tenant_id: TenantId) -> InventoryAnalysisResponse:
    try:
        from engine.forecast.inventory.engine import analyse_inventory
        from engine.forecast.inventory.loader import load_inventory_fixture

        data = load_inventory_fixture(tenant_id)
    except TenantDataMissing:
        require_mock_tenant(tenant_id)
        return load("inventory_analysis")
    return analyse_inventory(
        data,
        as_of=data.as_of,
        mode=mode(request),
        generated_at=datetime.now(UTC),
    )


@router.post("/v1/launch-lab/simulate", response_model=LaunchLabResponse)
def launch_lab_simulate(
    request: Request, tenant_id: TenantId, body: LaunchLabRequest
) -> LaunchLabResponse:
    """Simulate a product launch using resolved ledger history and market benchmarks (Y5)."""
    from engine.forecast.launch_lab.policy import load_policy
    from engine.forecast.launch_lab.resolver import resolve_case
    from engine.forecast.launch_lab.service import analyse

    current_mode = mode(request)
    policy, sources = load_policy(
        owner_overrides=body.constraints.model_dump(exclude_none=True) if body.constraints else None
    )
    case = resolve_case(tenant_id, body)
    runs = body.simulation_runs or (500 if current_mode == "mock" else 2000)
    seed = body.seed or 42

    return analyse(
        case,
        policy,
        sources,
        mode=current_mode,
        generated_at=datetime.now(UTC),
        runs=runs,
        seed=seed,
    )
