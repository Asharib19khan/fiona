"""The financial facts the analysis needs for one 12-month window, in framework-neutral concepts
(rulebook/metrics.yaml `concepts`). Built from ledger postings by neutral_class once D3 lands, or
supplied directly (uploads, fixtures). All amounts are integer minor units of one currency.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class IncomeStatement(BaseModel):
    model_config = ConfigDict(frozen=True)

    revenue: StrictInt
    cogs: StrictInt
    operating_expenses: StrictInt = Field(description="excluding depreciation and amortisation")
    depreciation_amortisation: StrictInt = 0
    interest_expense: StrictInt = 0
    other_income: StrictInt = 0
    tax_expense: StrictInt = 0

    @property
    def gross_profit(self) -> int:
        return self.revenue - self.cogs

    @property
    def ebit(self) -> int:
        return self.gross_profit - self.operating_expenses - self.depreciation_amortisation

    @property
    def ebitda(self) -> int:
        return self.ebit + self.depreciation_amortisation

    @property
    def net_income(self) -> int:
        return self.ebit - self.interest_expense + self.other_income - self.tax_expense


class BalanceSheet(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    cash: StrictInt
    trade_receivables: StrictInt = 0
    inventory: StrictInt = 0
    other_current_assets: StrictInt = 0
    non_current_assets: StrictInt = 0
    trade_payables: StrictInt = 0
    other_current_liabilities: StrictInt = 0
    borrowings_current: StrictInt = 0
    borrowings_noncurrent: StrictInt = 0
    lease_liabilities: StrictInt = 0
    other_noncurrent_liabilities: StrictInt = 0
    equity: StrictInt

    @property
    def current_assets(self) -> int:
        return self.cash + self.trade_receivables + self.inventory + self.other_current_assets

    @property
    def total_assets(self) -> int:
        return self.current_assets + self.non_current_assets

    @property
    def current_liabilities(self) -> int:
        return self.trade_payables + self.other_current_liabilities + self.borrowings_current

    @property
    def total_liabilities(self) -> int:
        return (
            self.current_liabilities
            + self.borrowings_noncurrent
            + self.lease_liabilities
            + self.other_noncurrent_liabilities
        )

    @property
    def interest_bearing_debt(self) -> int:
        return self.borrowings_current + self.borrowings_noncurrent + self.lease_liabilities

    @property
    def imbalance(self) -> int:
        """Assets minus liabilities minus equity; 0 for a balanced sheet."""
        return self.total_assets - self.total_liabilities - self.equity


class CashFlows(BaseModel):
    model_config = ConfigDict(frozen=True)

    cfo: StrictInt
    cfi: StrictInt
    cff: StrictInt
    capex: StrictInt = Field(0, description="purchases of PPE and intangibles, negative")
    principal_repaid: StrictInt = Field(
        0, description="scheduled borrowing and lease principal repaid, positive"
    )
    dividends_paid: StrictInt = 0
    acquisitions: StrictInt = Field(0, description="business acquisitions inside CFI, negative")
    largest_financing_inflow: StrictInt = Field(
        0, description="largest single loan drawdown or equity injection"
    )
    largest_disposal: StrictInt = Field(
        0, description="largest single asset sale inside CFI, positive"
    )


class Window(BaseModel):
    """One 12-month window: income and cash flows for the window, balances at both ends."""

    model_config = ConfigDict(frozen=True)

    label: str
    start: date
    end: date
    currency: str
    months_of_data: StrictInt = 12
    income: IncomeStatement
    opening: BalanceSheet | None = None
    closing: BalanceSheet
    cash_flows: CashFlows
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dates(self):
        if self.end <= self.start:
            raise ValueError("window end must be after its start")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1
