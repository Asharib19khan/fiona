"""Payloads for `GET /v1/forecast/cash?weeks=13`."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from engine.forecast._contracts import Figure, FigureInput, Finding, Money, Period
from engine.forecast.figures import Envelope, InsufficientData


class CashCategory(StrEnum):
    POS_SALES = "pos_sales"
    CUSTOMER_RECEIPTS = "customer_receipts"
    OTHER_INFLOW = "other_inflow"
    SUPPLIER_BILLS = "supplier_bills"
    PAYROLL = "payroll"
    RENT = "rent"
    UTILITIES = "utilities"
    LOAN_REPAYMENT = "loan_repayment"
    TAX = "tax"
    OTHER_OUTFLOW = "other_outflow"


class CashLine(BaseModel):
    category: CashCategory
    direction: Literal["in", "out"]
    money: Money = Field(description="Always positive; `direction` gives the sign.")
    basis: Literal["scheduled", "forecast"] = Field(
        description="scheduled: a known bill, invoice or recurring commitment; forecast: a statistical estimate."
    )
    refs: list[str] = Field(
        default_factory=list, description="Bill, invoice or pattern ids behind the line."
    )


class CashWeek(BaseModel):
    week: int = Field(ge=1)
    start: date
    end: date
    opening: Money
    inflows: Money
    outflows: Money
    net: Money
    closing: Money
    closing_low: Money = Field(description="Low end of the band (p10 of the closing balance).")
    closing_high: Money = Field(description="High end of the band (p90 of the closing balance).")
    below_buffer: bool
    lines: list[CashLine]


class ForecastMethod(BaseModel):
    name: str
    description: str
    history: Period | None = None
    band: str = Field(description="How closing_low/closing_high are produced.")
    backtest: list[Figure] = Field(default_factory=list)


class CashForecastResponse(Envelope):
    run_id: str
    currency: str
    as_of: date
    horizon_weeks: int
    method: ForecastMethod
    opening_balance: Figure
    buffer: Figure
    lowest_closing: Figure
    first_week_below_buffer: int | None
    shortfall: Figure = Field(
        description="How far the lowest closing balance falls below the buffer (0 if never)."
    )
    open_receivables: Figure
    open_payables: Figure
    weeks: list[CashWeek]
    assumptions: list[FigureInput] = Field(default_factory=list)
    insufficient_data: list[InsufficientData] = Field(default_factory=list)
    findings: list[Finding] = Field(
        default_factory=list, description="Alert findings raised by this run."
    )
