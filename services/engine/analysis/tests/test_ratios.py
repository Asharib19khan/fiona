from datetime import date

from engine.analysis.ratios import compute_ratios
from engine.analysis.statements import BalanceSheet, CashFlows, IncomeStatement, Window


def test_example_windows_are_internally_consistent(fy2025, fy2026):
    for w in (fy2025, fy2026):
        assert w.opening.imbalance == 0 and w.closing.imbalance == 0
        cf = w.cash_flows
        assert w.opening.cash + cf.cfo + cf.cfi + cf.cff == w.closing.cash


def test_hand_computed_ratios(fy2025, fy2026):
    r = compute_ratios(fy2026, fy2025, tax_rate_bp=2900)
    v = {k: (f.money.minor if f.money else f.value) for k, f in r.items() if f.status == "ok"}
    # current assets 2,387.82m / current liabilities 1,340m = 1.781955
    assert v["liquidity.current_ratio"] == 17820
    # (262.82m + 135m) / 1,340m = 0.296881
    assert v["liquidity.quick_ratio"] == 2969
    assert v["profit.gross_margin"] == 4000  # 3,840m / 9,600m
    assert v["profit.operating_margin"] == 380  # 365m / 9,600m = 3.802%
    assert v["is.net_income"] == 184_600_000  # 365m - 105m - 75.4m
    assert v["solvency.interest_coverage"] == 34762  # 365 / 105 = 3.47619
    assert v["solvency.debt_service"] == 285_000_000  # 105m interest + 180m principal
    assert v["solvency.dscr"] == 18246  # EBITDA 520m / 285m = 1.824561
    assert v["solvency.debt_to_equity"] == 2887  # 620m / 2,147.82m
    assert v["efficiency.inventory_days"] == 104  # (1,400m + 1,890m) / 2 / 5,760m x 365 = 104.24
    assert v["growth.revenue_growth"] == 608  # 9,600 / 9,050 - 1 = 6.077%
    assert v["profit.nopat"] == 259_150_000  # 365m x 0.71
    assert v["profit.roic"] == 1137  # 259.15m / ((2,055m + 2,505m) / 2)
    assert v["cash.cfo_to_net_income"] == -5168  # -95.4m / 184.6m
    assert v["cash.fcf"] == -265_400_000
    assert v["wc.inventory_change"] == -490_000_000


def test_every_figure_has_a_metric_id_and_formula(fy2026):
    for metric_id, fig in compute_ratios(fy2026, None, 2900).items():
        assert fig.metric_id == metric_id
        assert fig.status != "ok" or fig.formula


def test_missing_prior_and_tax_rate_are_insufficient_not_zero(fy2026):
    r = compute_ratios(fy2026)
    assert r["growth.revenue_growth"].status == "insufficient_data"
    assert r["profit.roic"].status == "insufficient_data"
    assert r["profit.roic"].missing == ["country pack corporate tax rate"]


def test_zero_denominators_are_not_applicable():
    bs = BalanceSheet(as_of=date(2026, 6, 30), cash=100, equity=100)
    w = Window(
        label="tiny",
        start=date(2025, 7, 1),
        end=date(2026, 6, 30),
        currency="PKR",
        income=IncomeStatement(revenue=0, cogs=0, operating_expenses=0),
        closing=bs,
        cash_flows=CashFlows(cfo=0, cfi=0, cff=0),
    )
    r = compute_ratios(w)
    assert r["liquidity.current_ratio"].status == "not_applicable"
    assert r["profit.gross_margin"].status == "not_applicable"
    assert r["solvency.interest_coverage"].status == "not_applicable"
    assert r["profit.roa"].note == "opening balance missing: closing balance used"
