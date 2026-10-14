"""Payloads for `POST /v1/financing/match`.

Options come from Abdullah's catalogue (rulebook/financing.yaml). Business figures such as
DSCR and leverage come from the one ratio implementation (engine.analysis, task Y2); this
module never computes its own ratios.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from engine.forecast._contracts import Figure, Money
from engine.forecast.figures import Envelope, InsufficientData, RuleCheck

Purpose = Literal["working_capital_seasonal", "working_capital_permanent", "capex", "refinancing"]
OptionKind = Literal[
    "term_loan",
    "running_finance",
    "invoice_discounting",
    "supplier_credit",
    "equipment_lease",
    "refinance_scheme",
    "microfinance",
    "equity_angel",
    "revenue_based",
]


class BusinessProfile(BaseModel):
    """Facts the catalogue's eligibility rules need that the ledger cannot tell us."""

    owner_age_years: int | None = Field(None, ge=16, le=100)
    legal_form: (
        Literal["sole_proprietor", "partnership", "private_limited", "public_limited", "other"]
        | None
    ) = None
    size_tier: Literal["micro", "small", "medium", "large"] | None = None
    years_operating: int | None = Field(None, ge=0, le=200)
    has_b2b_receivables: bool | None = Field(
        None, description="None: derived from the ledger's open invoices."
    )
    industry: str | None = None


class SupplierDiscount(BaseModel):
    discount_bp: int = Field(ge=0, lt=10_000)
    within_days: int = Field(ge=0)
    net_days: int = Field(gt=0)


class FinancingMatchRequest(BaseModel):
    amount: Money
    purpose: Purpose
    preferred_tenor_months: int | None = Field(None, ge=1, le=240)
    collateral_value: Money | None = None
    is_new_borrower_of_bank: bool | None = None
    profile: BusinessProfile = Field(default_factory=BusinessProfile)
    pre_money_valuation: Money | None = Field(
        None, description="Needed to size dilution for equity options."
    )
    supplier_discount: SupplierDiscount | None = Field(
        None, description="Early-payment discount given up by taking longer supplier terms, if any."
    )
    as_of: date | None = None


class CatalogueRef(BaseModel):
    source: str = "rulebook/financing.yaml"
    version: str
    as_of: date


class FinancingOption(BaseModel):
    option_id: str = Field(description="Catalogue row id.")
    name: str
    kind: OptionKind
    provider_label: str | None = None
    illustrative: bool = Field(
        description="True when the catalogue row is an illustrative example product."
    )
    source_ref: str = Field(description="Catalogue row id plus the source and as-of date it cites.")
    eligible: bool | None = Field(
        description="None when eligibility cannot be decided from the data."
    )
    eligibility: list[RuleCheck]
    verification: Literal["primary", "secondary", "assumption", "unverified", "indicative_range"]
    figures: list[Figure] = Field(
        description="Effective annual cost, instalment, total cost, DSCR after (base and downside), runway after, "
        "dilution; range ends carry suffixes .low/.mid/.high in metric_id."
    )
    outcome: Literal[
        "recommended", "possible_at_smaller_size", "cost_unknown", "needs_information", "ineligible"
    ]
    max_amount: Money | None = Field(
        None, description="Largest amount that keeps cover at the minimum, when it is smaller."
    )
    rank: int | None = Field(
        None, description="1 = best among eligible options; None if not eligible."
    )
    rank_reasons: list[str] = Field(
        default_factory=list, description="Reason codes, e.g. 'lowest_effective_cost'."
    )


class FinancingMatchResponse(Envelope):
    run_id: str
    currency: str
    as_of: date
    amount: Money
    purpose: Purpose
    catalogue: CatalogueRef
    business_figures: list[Figure] = Field(
        description="The business's own figures each option was tested against."
    )
    options: list[FinancingOption] = Field(
        description="Ranked eligible options first, then ineligible ones."
    )
    insufficient_data: list[InsufficientData] = Field(default_factory=list)
