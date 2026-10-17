"""Analysis endpoints (Abdullah lane, Y2): lifecycle stage, ratios and health bands.

GET endpoints build statements from the current tenant's posted D3 ledger events and identify that
source in `data_source`.
POST endpoints run the same engine on statements the caller supplies (uploads, agents, QA).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from engine.analysis import rulebook
from engine.analysis._contracts import Figure
from engine.analysis.health import ForecastView, HealthResult, assess_health
from engine.analysis.ledger_adapter import NoLedgerStatements, ledger_windows
from engine.analysis.ratios import compute_ratios
from engine.analysis.stage import StageResult, detect_stage
from engine.analysis.statements import Window
from engine.app.errors import ApiError
from engine.app.tenancy import TenantId
from engine.ledger import db

router = APIRouter(tags=["analysis"])


class Envelope(BaseModel):
    api_version: Literal["v1"] = "v1"
    mode: Literal["mock", "live"]
    tenant_id: str
    generated_at: datetime
    data_source: Literal["ledger", "request"]
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


def get_conn() -> Iterator[psycopg.Connection]:
    with db.connect(autocommit=True) as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_conn)]


def _ledger_windows(conn: psycopg.Connection, tenant_id: str) -> tuple[Window, Window | None]:
    try:
        return ledger_windows(conn, tenant_id)
    except NoLedgerStatements as exc:
        raise ApiError(
            404,
            "no_statements",
            "No posted ledger statements are available for this tenant yet.",
        ) from exc


def _env(request: Request, tenant_id: str, source: Literal["ledger", "request"]) -> dict:
    return {
        "mode": _mode(request),
        "tenant_id": tenant_id,
        "generated_at": datetime.now(UTC),
        "data_source": source,
        "data_note": None,
    }


def _ratios(req: AnalysisRequest) -> dict[str, Figure]:
    tax = rulebook.tax_rate_bp(req.country) if req.country else None
    return compute_ratios(req.latest, req.prior, tax)


@router.get("/v1/stage", response_model=StageResponse)
def get_stage(request: Request, tenant_id: TenantId, conn: Conn) -> StageResponse:
    latest, prior = _ledger_windows(conn, tenant_id)
    ratios = compute_ratios(latest, prior, rulebook.tax_rate_bp("PK"))
    growth, margin = ratios["growth.revenue_growth"], ratios["profit.operating_margin"]
    result = detect_stage(
        latest,
        prior,
        None,
        revenue_growth_bp=growth.value,
        operating_margin_bp=margin.value,
    )
    return StageResponse(**_env(request, tenant_id, "ledger"), result=result)


@router.get("/v1/analysis/ratios", response_model=RatiosResponse)
def get_ratios(request: Request, tenant_id: TenantId, conn: Conn) -> RatiosResponse:
    latest, prior = _ledger_windows(conn, tenant_id)
    figures = compute_ratios(latest, prior, rulebook.tax_rate_bp("PK"))
    return RatiosResponse(**_env(request, tenant_id, "ledger"), figures=list(figures.values()))


@router.get("/v1/analysis/health", response_model=HealthResponse)
def get_health(request: Request, tenant_id: TenantId, conn: Conn) -> HealthResponse:
    latest, prior = _ledger_windows(conn, tenant_id)
    result = assess_health(
        compute_ratios(latest, prior, rulebook.tax_rate_bp("PK")), None, industry="retail_apparel"
    )
    return HealthResponse(**_env(request, tenant_id, "ledger"), result=result)


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
