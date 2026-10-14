"""Stub statements for the mock endpoints and tests, until D3 builds statements from the ledger.

These are hand-made, internally consistent example windows (Origin.STUB), NOT persona data:
persona numbers come only from Daniyal's generator (fiona-b7 ruling, 13 Oct). Every response built
from them says so. Amounts in PKR minor units; each balance sheet balances and opening cash plus
the three cash flows equals closing cash.
"""

from datetime import date

from engine.analysis.statements import BalanceSheet, CashFlows, IncomeStatement, Window

STUB_TENANT = "ten_karachi_apparel"
STUB_NOTE = "Stub statements (hand-made example), not the tenant's ledger. Replaced when D3 builds statements from ledger events."
STUB_OWNER_STATED_STAGE = "growth"

BS_2024 = BalanceSheet(
    as_of=date(2024, 6, 30),
    cash=620_000_000,
    trade_receivables=110_000_000,
    inventory=1_280_000_000,
    other_current_assets=90_000_000,
    non_current_assets=970_000_000,
    trade_payables=690_000_000,
    other_current_liabilities=130_000_000,
    borrowings_current=300_000_000,
    borrowings_noncurrent=200_000_000,
    equity=1_750_000_000,
)
BS_2025 = BalanceSheet(
    as_of=date(2025, 6, 30),
    cash=758_220_000,
    trade_receivables=120_000_000,
    inventory=1_400_000_000,
    other_current_assets=95_000_000,
    non_current_assets=1_325_000_000,
    trade_payables=740_000_000,
    other_current_liabilities=145_000_000,
    borrowings_current=330_000_000,
    borrowings_noncurrent=420_000_000,
    equity=2_063_220_000,
)
BS_2026 = BalanceSheet(
    as_of=date(2026, 6, 30),
    cash=262_820_000,
    trade_receivables=135_000_000,
    inventory=1_890_000_000,
    other_current_assets=100_000_000,
    non_current_assets=1_340_000_000,
    trade_payables=830_000_000,
    other_current_liabilities=130_000_000,
    borrowings_current=380_000_000,
    borrowings_noncurrent=240_000_000,
    equity=2_147_820_000,
)

FY2025 = Window(
    label="FY2025 (Jul 2024 to Jun 2025)",
    start=date(2024, 7, 1),
    end=date(2025, 6, 30),
    currency="PKR",
    income=IncomeStatement(
        revenue=9_050_000_000,
        cogs=5_249_000_000,
        operating_expenses=2_961_000_000,
        depreciation_amortisation=125_000_000,
        interest_expense=133_000_000,
        tax_expense=168_780_000,
    ),
    opening=BS_2024,
    closing=BS_2025,
    cash_flows=CashFlows(
        cfo=468_220_000,
        cfi=-480_000_000,
        cff=150_000_000,
        capex=-480_000_000,
        principal_repaid=100_000_000,
        dividends_paid=100_000_000,
        largest_financing_inflow=400_000_000,
    ),
    source_refs=["example:fy2025"],
)
FY2026 = Window(
    label="FY2026 (Jul 2025 to Jun 2026)",
    start=date(2025, 7, 1),
    end=date(2026, 6, 30),
    currency="PKR",
    income=IncomeStatement(
        revenue=9_600_000_000,
        cogs=5_760_000_000,
        operating_expenses=3_320_000_000,
        depreciation_amortisation=155_000_000,
        interest_expense=105_000_000,
        tax_expense=75_400_000,
    ),
    opening=BS_2025,
    closing=BS_2026,
    cash_flows=CashFlows(
        cfo=-95_400_000,
        cfi=-170_000_000,
        cff=-230_000_000,
        capex=-170_000_000,
        principal_repaid=180_000_000,
        dividends_paid=100_000_000,
    ),
    source_refs=["example:fy2026"],
)
