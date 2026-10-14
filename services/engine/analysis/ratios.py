"""The ratio library (Y2): every ratio in rulebook/metrics.yaml that statements alone can produce.

Each result is a Figure carrying its metric_id, formula and inputs, so explain-any-number and B6
finance QA can recompute it. Arithmetic is exact integer/Decimal maths, rounded once, half away
from zero. A ratio that cannot be computed is an `insufficient_data` or `not_applicable` Figure
with the reason, never 0 and never infinity.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from engine.analysis._contracts import Figure, FigureInput, Money, Origin, Unit
from engine.analysis.coverage import debt_service, dscr
from engine.analysis.statements import BalanceSheet, Window


def _round(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _avg(opening: int | None, closing: int) -> tuple[Decimal, str]:
    if opening is None:
        return Decimal(closing), "closing_only"
    return (Decimal(opening) + Decimal(closing)) / 2, "average"


class _Builder:
    """Collects Figures for one window, with consistent inputs and refs."""

    def __init__(self, window: Window, origin: Origin) -> None:
        self.w = window
        self.ccy = window.currency
        self.origin = origin
        self.out: dict[str, Figure] = {}

    def inp(self, name: str, minor: int | Decimal) -> FigureInput:
        value = minor if isinstance(minor, int) else _round(minor)
        return FigureInput(
            name=name,
            money=Money(minor=value, currency=self.ccy),
            unit=Unit.MINOR,
            origin=self.origin,
        )

    def money(
        self, metric_id: str, label: str, minor: int, formula: str, inputs: list[FigureInput]
    ) -> None:
        self.out[metric_id] = Figure(
            metric_id=metric_id,
            label=label,
            money=Money(minor=minor, currency=self.ccy),
            unit=Unit.MINOR,
            formula=formula,
            inputs=inputs,
            source_refs=self.w.source_refs,
        )

    def bp(
        self,
        metric_id: str,
        label: str,
        num: int | Decimal,
        den: int | Decimal,
        formula: str,
        inputs: list[FigureInput],
        null_reason: str,
        not_applicable: bool = False,
        note: str | None = None,
    ) -> None:
        if den == 0 or (not_applicable and den < 0):
            self.out[metric_id] = Figure(
                metric_id=metric_id,
                label=label,
                unit=Unit.BP,
                formula=formula,
                inputs=inputs,
                status="not_applicable",
                note=null_reason,
                source_refs=self.w.source_refs,
            )
            return
        value = _round(Decimal(num) * 10000 / Decimal(den))
        self.out[metric_id] = Figure(
            metric_id=metric_id,
            label=label,
            value=value,
            unit=Unit.BP,
            formula=formula,
            inputs=inputs,
            source_refs=self.w.source_refs,
            note=note,
        )

    def days(
        self,
        metric_id: str,
        label: str,
        num: Decimal,
        den: int,
        formula: str,
        inputs: list[FigureInput],
        null_reason: str,
        note: str | None = None,
    ) -> None:
        if den == 0:
            self.out[metric_id] = Figure(
                metric_id=metric_id,
                label=label,
                unit=Unit.DAYS,
                formula=formula,
                inputs=inputs,
                status="not_applicable",
                note=null_reason,
                source_refs=self.w.source_refs,
            )
            return
        value = _round(num / Decimal(den) * self.w.days)
        self.out[metric_id] = Figure(
            metric_id=metric_id,
            label=label,
            value=value,
            unit=Unit.DAYS,
            formula=formula,
            inputs=inputs,
            source_refs=self.w.source_refs,
            note=note,
        )

    def missing(self, metric_id: str, label: str, unit: Unit, missing: list[str]) -> None:
        self.out[metric_id] = Figure(
            metric_id=metric_id,
            label=label,
            unit=unit,
            status="insufficient_data",
            missing=missing,
            source_refs=self.w.source_refs,
        )


def _balance(b: _Builder, bs: BalanceSheet) -> None:
    ca, cl = bs.current_assets, bs.current_liabilities
    ca_in, cl_in = b.inp("current assets", ca), b.inp("current liabilities", cl)
    na = "no current liabilities"
    b.bp(
        "liquidity.current_ratio",
        "Current ratio",
        ca,
        cl,
        "current assets / current liabilities",
        [ca_in, cl_in],
        na,
    )
    b.bp(
        "liquidity.quick_ratio",
        "Quick ratio",
        bs.cash + bs.trade_receivables,
        cl,
        "(cash + trade receivables) / current liabilities",
        [b.inp("cash", bs.cash), b.inp("trade receivables", bs.trade_receivables), cl_in],
        na,
    )
    b.bp(
        "liquidity.cash_ratio",
        "Cash ratio",
        bs.cash,
        cl,
        "cash / current liabilities",
        [b.inp("cash", bs.cash), cl_in],
        na,
    )
    b.money(
        "liquidity.working_capital",
        "Working capital",
        ca - cl,
        "current assets - current liabilities",
        [ca_in, cl_in],
    )

    debt = bs.interest_bearing_debt
    debt_in = b.inp("interest-bearing debt", debt)
    b.money(
        "solvency.interest_bearing_debt",
        "Interest-bearing debt",
        debt,
        "borrowings (current + non-current) + lease liabilities",
        [
            b.inp("borrowings, current", bs.borrowings_current),
            b.inp("borrowings, non-current", bs.borrowings_noncurrent),
            b.inp("lease liabilities", bs.lease_liabilities),
        ],
    )
    b.bp(
        "solvency.debt_to_equity",
        "Debt to equity",
        debt,
        bs.equity,
        "interest-bearing debt / equity",
        [debt_in, b.inp("equity", bs.equity)],
        "equity is zero or negative",
        not_applicable=True,
    )
    b.bp(
        "solvency.debt_to_assets",
        "Debt to assets",
        debt,
        bs.total_assets,
        "interest-bearing debt / total assets",
        [debt_in, b.inp("total assets", bs.total_assets)],
        "no assets",
    )
    b.money(
        "solvency.net_debt",
        "Net debt",
        debt - bs.cash,
        "interest-bearing debt - cash",
        [debt_in, b.inp("cash", bs.cash)],
    )
    b.money(
        "profit.invested_capital",
        "Invested capital",
        bs.equity + debt - bs.cash,
        "equity + interest-bearing debt - cash",
        [b.inp("equity", bs.equity), debt_in, b.inp("cash", bs.cash)],
    )


def compute_ratios(
    window: Window,
    prior: Window | None = None,
    tax_rate_bp: int | None = None,
    origin: Origin = Origin.LEDGER,
) -> dict[str, Figure]:
    """All statement-based metrics for `window`; year-on-year metrics need `prior`.

    `tax_rate_bp` (country pack statutory rate) is needed for NOPAT and ROIC.
    """
    b = _Builder(window, origin)
    inc, close, open_, cf = window.income, window.closing, window.opening, window.cash_flows
    _balance(b, close)

    rev_in = b.inp("revenue", inc.revenue)
    no_rev = "revenue is zero or negative"
    b.bp(
        "profit.gross_margin",
        "Gross margin",
        inc.gross_profit,
        inc.revenue if inc.revenue > 0 else 0,
        "gross profit / revenue",
        [b.inp("gross profit", inc.gross_profit), rev_in],
        no_rev,
    )
    b.bp(
        "profit.operating_margin",
        "Operating margin",
        inc.ebit,
        inc.revenue if inc.revenue > 0 else 0,
        "operating profit (EBIT) / revenue",
        [b.inp("operating profit", inc.ebit), rev_in],
        no_rev,
    )
    b.money(
        "profit.ebitda",
        "EBITDA",
        inc.ebitda,
        "operating profit + depreciation and amortisation",
        [
            b.inp("operating profit", inc.ebit),
            b.inp("depreciation and amortisation", inc.depreciation_amortisation),
        ],
    )
    b.bp(
        "profit.ebitda_margin",
        "EBITDA margin",
        inc.ebitda,
        inc.revenue if inc.revenue > 0 else 0,
        "EBITDA / revenue",
        [b.inp("EBITDA", inc.ebitda), rev_in],
        no_rev,
    )
    b.money(
        "is.net_income",
        "Net profit",
        inc.net_income,
        "operating profit - interest + other income - tax",
        [
            b.inp("operating profit", inc.ebit),
            b.inp("interest", inc.interest_expense),
            b.inp("other income", inc.other_income),
            b.inp("tax", inc.tax_expense),
        ],
    )
    b.bp(
        "profit.net_margin",
        "Net profit margin",
        inc.net_income,
        inc.revenue if inc.revenue > 0 else 0,
        "net profit / revenue",
        [b.inp("net profit", inc.net_income), rev_in],
        no_rev,
    )

    avg_assets, basis = _avg(open_.total_assets if open_ else None, close.total_assets)
    avg_equity, _ = _avg(open_.equity if open_ else None, close.equity)
    basis_note = None if basis == "average" else "opening balance missing: closing balance used"
    b.bp(
        "profit.roa",
        "Return on assets",
        inc.net_income,
        avg_assets,
        "net profit / average total assets",
        [b.inp("net profit", inc.net_income), b.inp("average total assets", avg_assets)],
        "no assets",
        note=basis_note,
    )
    b.bp(
        "profit.roe",
        "Return on equity",
        inc.net_income,
        avg_equity,
        "net profit / average equity",
        [b.inp("net profit", inc.net_income), b.inp("average equity", avg_equity)],
        "average equity is zero or negative",
        not_applicable=True,
        note=basis_note,
    )

    if tax_rate_bp is None:
        b.missing(
            "profit.nopat",
            "Net operating profit after tax",
            Unit.MINOR,
            ["country pack corporate tax rate"],
        )
        b.missing(
            "profit.roic",
            "Return on invested capital",
            Unit.BP,
            ["country pack corporate tax rate"],
        )
    else:
        nopat = _round(Decimal(inc.ebit) * (10000 - tax_rate_bp) / 10000)
        tax_in = FigureInput(
            name="corporate tax rate", value=tax_rate_bp, unit=Unit.BP, origin=Origin.RULEBOOK
        )
        b.money(
            "profit.nopat",
            "Net operating profit after tax",
            nopat,
            "operating profit x (1 - tax rate)",
            [b.inp("operating profit", inc.ebit), tax_in],
        )
        ic_close = close.equity + close.interest_bearing_debt - close.cash
        ic_open = (open_.equity + open_.interest_bearing_debt - open_.cash) if open_ else None
        avg_ic, _ = _avg(ic_open, ic_close)
        b.bp(
            "profit.roic",
            "Return on invested capital",
            nopat,
            avg_ic,
            "NOPAT / average invested capital",
            [b.inp("NOPAT", nopat), b.inp("average invested capital", avg_ic)],
            "average invested capital is zero or negative",
            not_applicable=True,
            note=basis_note,
        )

    interest_in = b.inp("interest expense", inc.interest_expense)
    b.bp(
        "solvency.interest_coverage",
        "Interest coverage",
        inc.ebit,
        inc.interest_expense,
        "operating profit / interest expense",
        [b.inp("operating profit", inc.ebit), interest_in],
        "no interest expense (no interest-bearing debt)",
    )
    service = debt_service(inc.interest_expense, cf.principal_repaid)
    b.money(
        "solvency.debt_service",
        "Debt service, last 12 months",
        service,
        "interest + scheduled principal repaid",
        [interest_in, b.inp("principal repaid", cf.principal_repaid)],
    )
    cov = dscr(inc.ebitda, inc.interest_expense, cf.principal_repaid)  # the one DSCR implementation
    dscr_inputs = [b.inp("EBITDA", inc.ebitda), b.inp("debt service", service)]
    if cov.value_bp is None:
        b.out["solvency.dscr"] = Figure(
            metric_id="solvency.dscr",
            label="Debt-service coverage",
            unit=Unit.BP,
            status="not_applicable",
            note=cov.reason,
            inputs=dscr_inputs,
            formula="EBITDA / (interest + principal repaid)",
            source_refs=window.source_refs,
        )
    else:
        b.out["solvency.dscr"] = Figure(
            metric_id="solvency.dscr",
            label="Debt-service coverage",
            value=cov.value_bp,
            unit=Unit.BP,
            inputs=dscr_inputs,
            formula="EBITDA / (interest + principal repaid)",
            source_refs=window.source_refs,
        )
    net_debt = close.interest_bearing_debt - close.cash
    b.bp(
        "solvency.net_debt_to_ebitda",
        "Net debt to EBITDA",
        net_debt,
        inc.ebitda,
        "net debt / EBITDA",
        [b.inp("net debt", net_debt), b.inp("EBITDA", inc.ebitda)],
        "EBITDA is zero or negative",
        not_applicable=True,
    )

    avg_inv, _ = _avg(open_.inventory if open_ else None, close.inventory)
    avg_ar, _ = _avg(open_.trade_receivables if open_ else None, close.trade_receivables)
    avg_ap, _ = _avg(open_.trade_payables if open_ else None, close.trade_payables)
    cogs_in = b.inp("cost of sales", inc.cogs)
    b.days(
        "efficiency.inventory_days",
        "Inventory days",
        avg_inv,
        inc.cogs,
        "average inventory / cost of sales x days",
        [b.inp("average inventory", avg_inv), cogs_in],
        "no cost of sales",
        note=basis_note,
    )
    b.days(
        "efficiency.receivable_days",
        "Receivable days",
        avg_ar,
        inc.revenue,
        "average receivables / revenue x days",
        [b.inp("average receivables", avg_ar), rev_in],
        no_rev,
        note=basis_note,
    )
    b.days(
        "efficiency.payable_days",
        "Payable days",
        avg_ap,
        inc.cogs,
        "average payables / cost of sales x days",
        [b.inp("average payables", avg_ap), cogs_in],
        "no cost of sales",
        note=basis_note,
    )
    parts = [
        b.out[k]
        for k in (
            "efficiency.inventory_days",
            "efficiency.receivable_days",
            "efficiency.payable_days",
        )
    ]
    if all(p.status == "ok" for p in parts):
        ccc = parts[0].value + parts[1].value - parts[2].value
        b.out["efficiency.cash_conversion_cycle"] = Figure(
            metric_id="efficiency.cash_conversion_cycle",
            label="Cash conversion cycle",
            value=ccc,
            unit=Unit.DAYS,
            formula="inventory days + receivable days - payable days",
            inputs=[
                FigureInput(
                    name=p.label,
                    value=p.value,
                    unit=Unit.DAYS,
                    origin=Origin.FIGURE,
                    ref=p.metric_id,
                )
                for p in parts
            ],
            source_refs=window.source_refs,
        )
    else:
        b.missing(
            "efficiency.cash_conversion_cycle",
            "Cash conversion cycle",
            Unit.DAYS,
            ["cost of sales and revenue"],
        )
    b.bp(
        "efficiency.asset_turnover",
        "Asset turnover",
        inc.revenue,
        avg_assets,
        "revenue / average total assets",
        [rev_in, b.inp("average total assets", avg_assets)],
        "no assets",
        note=basis_note,
    )

    b.money(
        "cash.cfo",
        "Operating cash flow",
        cf.cfo,
        "net cash from operating activities",
        [b.inp("CFO", cf.cfo)],
    )
    b.money(
        "cash.cfi",
        "Investing cash flow",
        cf.cfi,
        "net cash from investing activities",
        [b.inp("CFI", cf.cfi)],
    )
    b.money(
        "cash.cff",
        "Financing cash flow",
        cf.cff,
        "net cash from financing activities",
        [b.inp("CFF", cf.cff)],
    )
    b.money(
        "cash.fcf",
        "Free cash flow",
        cf.cfo + cf.capex,
        "operating cash flow + capex (capex is negative)",
        [b.inp("CFO", cf.cfo), b.inp("capex", cf.capex)],
    )
    b.bp(
        "cash.cfo_to_net_income",
        "Operating cash flow to net profit",
        cf.cfo,
        inc.net_income if inc.net_income > 0 else 0,
        "operating cash flow / net profit",
        [b.inp("CFO", cf.cfo), b.inp("net profit", inc.net_income)],
        "net profit is zero or negative",
    )
    b.bp(
        "cash.capex_coverage",
        "Capex coverage",
        cf.cfo,
        abs(cf.capex),
        "operating cash flow / |capex|",
        [b.inp("CFO", cf.cfo), b.inp("capex", cf.capex)],
        "no capex",
    )
    b.bp(
        "cash.capex_to_depreciation",
        "Capex to depreciation",
        abs(cf.capex),
        inc.depreciation_amortisation,
        "|capex| / depreciation and amortisation",
        [b.inp("capex", cf.capex), b.inp("depreciation", inc.depreciation_amortisation)],
        "no depreciation",
    )
    if open_ is not None:
        b.money(
            "wc.inventory_change",
            "Cash absorbed by inventory",
            -(close.inventory - open_.inventory),
            "-(closing inventory - opening inventory)",
            [
                b.inp("opening inventory", open_.inventory),
                b.inp("closing inventory", close.inventory),
            ],
        )
        b.money(
            "wc.receivables_change",
            "Cash absorbed by receivables",
            -(close.trade_receivables - open_.trade_receivables),
            "-(closing receivables - opening receivables)",
            [
                b.inp("opening receivables", open_.trade_receivables),
                b.inp("closing receivables", close.trade_receivables),
            ],
        )
        b.money(
            "wc.payables_change",
            "Cash provided by payables",
            close.trade_payables - open_.trade_payables,
            "closing payables - opening payables",
            [
                b.inp("opening payables", open_.trade_payables),
                b.inp("closing payables", close.trade_payables),
            ],
        )
    else:
        for mid, label in (
            ("wc.inventory_change", "Cash absorbed by inventory"),
            ("wc.receivables_change", "Cash absorbed by receivables"),
            ("wc.payables_change", "Cash provided by payables"),
        ):
            b.missing(mid, label, Unit.MINOR, ["opening balance sheet"])

    if prior is not None:
        _year_on_year(b, window, prior, tax_rate_bp)
    else:
        for mid, label, unit in (
            ("growth.revenue_growth", "Revenue growth", Unit.BP),
            ("profit.gross_margin_change", "Change in gross margin", Unit.BP),
            ("profit.operating_margin_prior", "Operating margin, prior 12 months", Unit.BP),
            ("efficiency.inventory_days_change", "Change in inventory days", Unit.BP),
            ("cash.cfo_prior", "Operating cash flow, prior 12 months", Unit.MINOR),
        ):
            b.missing(mid, label, unit, ["prior 12-month window"])
    return b.out


def _year_on_year(b: _Builder, window: Window, prior: Window, tax_rate_bp: int | None) -> None:
    p = compute_ratios(prior, None, tax_rate_bp)
    cur, pre = window.income.revenue, prior.income.revenue
    b.bp(
        "growth.revenue_growth",
        "Revenue growth",
        cur - pre,
        pre if pre > 0 else 0,
        "revenue / prior revenue - 1",
        [b.inp("revenue", cur), b.inp("prior revenue", pre)],
        "prior revenue is zero or negative",
    )
    for mid, label, base in (
        ("profit.gross_margin_change", "Change in gross margin", "profit.gross_margin"),
    ):
        now, then = b.out[base], p[base]
        if now.status == "ok" and then.status == "ok":
            b.out[mid] = Figure(
                metric_id=mid,
                label=label,
                value=now.value - then.value,
                unit=Unit.BP,
                formula="gross margin - prior gross margin (percentage points in bp)",
                inputs=[
                    FigureInput(
                        name="gross margin",
                        value=now.value,
                        unit=Unit.BP,
                        origin=Origin.FIGURE,
                        ref=base,
                    ),
                    FigureInput(
                        name="prior gross margin",
                        value=then.value,
                        unit=Unit.BP,
                        origin=Origin.FIGURE,
                        ref=base,
                    ),
                ],
                source_refs=window.source_refs + prior.source_refs,
            )
        else:
            b.missing(mid, label, Unit.BP, ["revenue in both windows"])
    prior_om = p["profit.operating_margin"]
    b.out["profit.operating_margin_prior"] = prior_om.model_copy(
        update={
            "metric_id": "profit.operating_margin_prior",
            "label": "Operating margin, prior 12 months",
        }
    )
    inv_now, inv_then = b.out["efficiency.inventory_days"], p["efficiency.inventory_days"]
    if inv_now.status == "ok" and inv_then.status == "ok" and inv_then.value > 0:
        b.bp(
            "efficiency.inventory_days_change",
            "Change in inventory days",
            inv_now.value - inv_then.value,
            inv_then.value,
            "(inventory days - prior inventory days) / prior inventory days",
            [
                FigureInput(
                    name="inventory days",
                    value=inv_now.value,
                    unit=Unit.DAYS,
                    origin=Origin.FIGURE,
                    ref="efficiency.inventory_days",
                ),
                FigureInput(
                    name="prior inventory days",
                    value=inv_then.value,
                    unit=Unit.DAYS,
                    origin=Origin.FIGURE,
                    ref="efficiency.inventory_days",
                ),
            ],
            "no prior inventory days",
        )
    else:
        b.missing(
            "efficiency.inventory_days_change",
            "Change in inventory days",
            Unit.BP,
            ["inventory and cost of sales in both windows"],
        )
    b.money(
        "cash.cfo_prior",
        "Operating cash flow, prior 12 months",
        prior.cash_flows.cfo,
        "prior window CFO",
        [b.inp("prior CFO", prior.cash_flows.cfo)],
    )
