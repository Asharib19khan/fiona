"""Payloads for `GET /v1/inventory/analysis`."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from engine.forecast._contracts import Figure, Finding, Money, Period, Threshold
from engine.forecast.figures import Envelope, InsufficientData


class InventoryItem(BaseModel):
    sku: str
    name: str
    category: str
    style: str = Field(description="Parent style; size and colour variants share it.")
    size: str | None = None
    colour: str | None = None
    season: Literal["all", "summer", "winter"]
    on_hand: int
    unit_cost: Money
    price: Money
    stock_value: Money
    units_sold_window: int
    revenue_window: Money
    gross_margin_window: Money
    gross_margin_bp: int | None
    abc: Literal["A", "B", "C"]
    xyz: Literal["X", "Y", "Z"] | None = Field(
        description="None when history is too short to measure variability."
    )
    demand_cv_bp: int | None
    movement: Literal["fast", "normal", "slow", "dead", "new"]
    days_of_cover: int | None
    last_sold_on: date | None
    lead_time_days: int
    safety_stock: int
    reorder_point: int
    suggested_order_qty: int
    turnover_bp: int | None = Field(description="Annualised turns, in bp of 1.")
    gmroi_bp: int | None
    cash_tied_up: Money = Field(
        description="Stock value above the cover target; all of it for dead stock."
    )
    source_refs: list[str] = Field(default_factory=list)


class SizeShare(BaseModel):
    size: str
    share_bp: int


class StyleRollup(BaseModel):
    style: str
    name: str
    skus: list[str]
    on_hand: int
    stock_value: Money
    units_sold_window: int
    size_curve: list[SizeShare]
    strongest_sku: str | None
    weakest_sku: str | None


class BundleCandidate(BaseModel):
    skus: list[str]
    baskets_together: int
    lift_bp: int
    reason_code: str


class DraftPOLine(BaseModel):
    sku: str
    qty: int = Field(ge=1)
    unit_cost: Money
    line_total: Money


class DraftPurchaseOrder(BaseModel):
    draft_id: str
    supplier_id: str
    order_by: date
    expected_on: date
    lines: list[DraftPOLine]
    total: Money
    reason_code: str
    refs: list[str] = Field(default_factory=list)


class InventoryAnalysisResponse(Envelope):
    run_id: str
    currency: str
    as_of: date
    window: Period
    parameters: list[Threshold]
    summary: list[Figure]
    items: list[InventoryItem]
    styles: list[StyleRollup]
    bundles: list[BundleCandidate]
    draft_purchase_orders: list[DraftPurchaseOrder]
    findings: list[Finding] = Field(default_factory=list)
    insufficient_data: list[InsufficientData] = Field(default_factory=list)
