"""Analysis endpoints (Abdullah lane, Y2): lifecycle stage, ratios and health bands.

GET endpoints serve the current tenant. Until D3 builds statements from ledger events they run the
real engine on labelled stub statements (mock mode, demo tenant only) and say so in `data_source`.
POST endpoints run the same engine on statements the caller supplies (uploads, agents, QA).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from engine.analysis import rulebook, stub
from engine.analysis._contracts import Figure
from engine.analysis.health import ForecastView, HealthResult, assess_health
from engine.analysis.ratios import compute_ratios
from engine.analysis.stage import StageResult, detect_stage
from engine.analysis.statements import Window
from engine.app.errors import ApiError
from engine.app.tenancy import TenantId

router = APIRouter(tags=["analysis"])


class Envelope(BaseModel):
    api_version: Literal["v1"] = "v1"
    mode: Literal["mock", "live"]
    tenant_id: str
    generated_at: datetime
    data_source: Literal["stub", "ledger", "request"]
    data_note: str | None = None


class StageResponse(Envelope):
    result: StageResult


class RatiosResponse(Envelope):
    figures: list[Figure]


class HealthResponse(Envelope):
    result: HealthResult


class AnalysisRequest(BaseModel):
    latest: Window
    prior: Window | None = None
    owner_stated_stage: str | None = None
    owner_declared_event: str | None = None
    country: str | None = Field(None, description="country pack for the tax rate, e.g. PK")
    industry: str | None = Field(None, description="industry pack key, e.g. retail_apparel")
    forecast: ForecastView | None = None


def _mode(request: Request) -> Literal["mock", "live"]:
    return getattr(request.app.state, "mode", "mock")


def _stub_windows(request: Request, tenant_id: str) -> tuple[Window, Window]:
    if _mode(request) != "mock" or tenant_id != stub.STUB_TENANT:
        raise ApiError(
            404,
            "no_statements",
            "No statements for this tenant yet: the ledger statement builder (D3) has not run.",
        )
    return stub.FY2026, stub.FY2025


def _env(request: Request, tenant_id: str, source: Literal["stub", "ledger", "request"]) -> dict:
    return {
        "mode": _mode(request),
        "tenant_id": tenant_id,
        "generated_at": datetime.now(UTC),
        "data_source": source,
        "data_note": stub.STUB_NOTE if source == "stub" else None,
    }


def _ratios(req: AnalysisRequest) -> dict[str, Figure]:
    tax = rulebook.tax_rate_bp(req.country) if req.country else None
    return compute_ratios(req.latest, req.prior, tax)


@router.get("/v1/stage", response_model=StageResponse)
def get_stage(request: Request, tenant_id: TenantId) -> StageResponse:
    latest, prior = _stub_windows(request, tenant_id)
    ratios = compute_ratios(latest, prior, rulebook.tax_rate_bp("PK"))
    growth, margin = ratios["growth.revenue_growth"], ratios["profit.operating_margin"]
    result = detect_stage(
        latest,
        prior,
        stub.STUB_OWNER_STATED_STAGE,
        revenue_growth_bp=growth.value,
        operating_margin_bp=margin.value,
    )
    return StageResponse(**_env(request, tenant_id, "stub"), result=result)


@router.get("/v1/analysis/ratios", response_model=RatiosResponse)
def get_ratios(request: Request, tenant_id: TenantId) -> RatiosResponse:
    latest, prior = _stub_windows(request, tenant_id)
    figures = compute_ratios(latest, prior, rulebook.tax_rate_bp("PK"))
    return RatiosResponse(**_env(request, tenant_id, "stub"), figures=list(figures.values()))


@router.get("/v1/analysis/health", response_model=HealthResponse)
def get_health(request: Request, tenant_id: TenantId) -> HealthResponse:
    latest, prior = _stub_windows(request, tenant_id)
    result = assess_health(
        compute_ratios(latest, prior, rulebook.tax_rate_bp("PK")), None, industry="retail_apparel"
    )
    return HealthResponse(**_env(request, tenant_id, "stub"), result=result)


@router.post("/v1/analysis/stage", response_model=StageResponse)
def post_stage(request: Request, tenant_id: TenantId, body: AnalysisRequest) -> StageResponse:
    ratios = _ratios(body)
    growth, margin = ratios["growth.revenue_growth"], ratios["profit.operating_margin"]
    result = detect_stage(
        body.latest,
        body.prior,
        body.owner_stated_stage,
        revenue_growth_bp=growth.value,
        operating_margin_bp=margin.value,
        owner_declared_event=body.owner_declared_event,
    )
    return StageResponse(**_env(request, tenant_id, "request"), result=result)


@router.post("/v1/analysis/ratios", response_model=RatiosResponse)
def post_ratios(request: Request, tenant_id: TenantId, body: AnalysisRequest) -> RatiosResponse:
    return RatiosResponse(
        **_env(request, tenant_id, "request"), figures=list(_ratios(body).values())
    )


@router.post("/v1/analysis/health", response_model=HealthResponse)
def post_health(request: Request, tenant_id: TenantId, body: AnalysisRequest) -> HealthResponse:
    result = assess_health(_ratios(body), body.forecast, industry=body.industry)
    return HealthResponse(**_env(request, tenant_id, "request"), result=result)
