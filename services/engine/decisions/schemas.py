"""Payloads for the decision calculators (Y4) and the payment-timing optimiser (Y8).

Every decision answers in one shape, so one screen and one council debate can show any of
them: options with Figures, the rule checks behind the recommendation, and what data is
missing. The engine never writes prose; the CFO Strategist turns this into a memo.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from engine.forecast._contracts import Figure, FigureInput, Money
from engine.forecast.figures import Envelope, InsufficientData, RuleCheck

# ---- requests ------------------------------------------------------------------------------


class DebtTerms(BaseModel):
    lender_label: str | None = None
    annual_rate_bp: int = Field(ge=0, le=100_000)
    term_months: int = Field(ge=1, le=360)
    grace_months: int = Field(0, ge=0, le=60)
    upfront_fee_bp: int = Field(0, ge=0, le=10_000)
    repayment: Literal["annuity", "equal_principal", "bullet"] = "annuity"


class EquityTerms(BaseModel):
    investor_label: str | None = None
    pre_money_valuation: Money | None = None
    stake_offered_bp: int | None = Field(None, ge=1, le=10_000)
    owner_required_return_bp: int | None = Field(None, ge=0, le=100_000)


class DebtEquityRequest(BaseModel):
    amount: Money
    purpose: str
    debt: DebtTerms | None = Field(
        None, description="None: use the cheapest eligible catalogue loan."
    )
    equity: EquityTerms | None = None
    horizon_months: int = Field(12, ge=1, le=60)
    as_of: date | None = None


class DividendRequest(BaseModel):
    proposed_dividend: Money | None = Field(
        None, description="None: the engine reports the largest safe amount."
    )
    reinvestment_return_bp: int | None = Field(None, ge=-10_000, le=100_000)
    owner_required_return_bp: int | None = Field(None, ge=0, le=100_000)
    as_of: date | None = None


class PaymentTimingRequest(BaseModel):
    bill_ids: list[str] | None = Field(None, description="None: every open supplier bill.")
    cost_of_money_annual_bp: int | None = Field(None, ge=0, le=100_000)
    horizon_weeks: int = Field(13, ge=1, le=26)
    as_of: date | None = None


# ---- responses -----------------------------------------------------------------------------


class AmortisationRow(BaseModel):
    month: int = Field(ge=1)
    due_on: date
    payment: Money
    interest: Money
    principal: Money
    balance: Money


class CashPathPoint(BaseModel):
    week: int = Field(ge=1)
    closing_with: Money = Field(description="Closing cash if this option is taken.")
    closing_without: Money = Field(description="Closing cash on the current forecast.")


class DecisionOption(BaseModel):
    option_id: str
    label: str
    eligible: bool | None
    figures: list[Figure]
    rule_checks: list[RuleCheck]
    amortisation: list[AmortisationRow] | None = None
    cash_path: list[CashPathPoint] | None = None


class DecisionRecommendation(BaseModel):
    outcome: Literal["recommend", "no_clear_winner", "insufficient_data"]
    option_id: str | None
    rule_trace: list[RuleCheck]
    reason_codes: list[str] = Field(default_factory=list)


class DecisionResponse(Envelope):
    decision: Literal["debt_equity", "dividend"]
    run_id: str
    currency: str
    as_of: date
    inputs: list[FigureInput]
    figures: list[Figure] = Field(
        description="Figures shared by every option, e.g. current DSCR and buffer."
    )
    options: list[DecisionOption]
    recommendation: DecisionRecommendation
    insufficient_data: list[InsufficientData] = Field(default_factory=list)


class EarlyPaymentTerms(BaseModel):
    discount_bp: int = Field(ge=0, le=10_000)
    within_days: int = Field(ge=0)
    net_days: int = Field(ge=0)
    origin: Literal["bill_text", "supplier_terms", "assumption_unverified"]


class BillTiming(BaseModel):
    bill_id: str
    supplier_id: str
    supplier_name: str
    amount: Money
    issue_date: date
    due_date: date
    terms: EarlyPaymentTerms | None
    action: Literal["pay_early", "pay_on_due", "cannot_pay_on_due"]
    pay_on: date | None
    figures: list[Figure]
    rule_checks: list[RuleCheck]


class TimingWeek(BaseModel):
    week: int = Field(ge=1)
    start: date
    end: date
    payments: Money
    closing_before: Money
    closing_after: Money
    below_buffer: bool


class PaymentTimingResponse(Envelope):
    run_id: str
    currency: str
    as_of: date
    cost_of_money: Figure
    buffer: Figure
    bills: list[BillTiming]
    weeks: list[TimingWeek]
    totals: list[Figure]
    insufficient_data: list[InsufficientData] = Field(default_factory=list)
