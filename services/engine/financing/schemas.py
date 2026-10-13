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


class FinancingMatchRequest(BaseModel):
    tenant_id: str
    amount: Money
    purpose: Purpose
    preferred_tenor_months: int | None = Field(None, ge=1, le=240)
    collateral_value: Money | None = None
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
    verification: Literal["primary", "secondary", "indicative_range"]
    figures: list[Figure] = Field(
        description="Effective annual cost, instalment, total cost, DSCR after (base and downside), runway after, "
        "dilution; range ends carry suffixes .low/.mid/.high in metric_id."
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
