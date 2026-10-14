"""Health bands (Y2): healthy / watch / stressed / critical per dimension, and an overall band by
a transparent rule (rulebook/finance_rules.yaml `health`). There is no composite score: Fiona
says "band", never "score" (fiona-b7 ruling R9).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.analysis import rulebook
from engine.analysis._contracts import Figure, FigureInput, Money, Origin, Unit

Band = Literal["healthy", "watch", "stressed", "critical", "not_computable"]
_ORDER: list[Band] = ["healthy", "watch", "stressed", "critical"]


class ForecastView(BaseModel):
    """What the 13-week forecast (Y1) contributes: weekly closing cash and the owner's buffer."""

    weekly_closing_minor: list[int]
    buffer_minor: int
    currency: str
    forecast_run_id: str | None = None


class Dimension(BaseModel):
    band: Band
    reasons: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)


class HealthResult(BaseModel):
    overall: Band
    dimensions: dict[str, Dimension]
    divergences: list[dict] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    note: str = "Bands follow transparent rules; Fiona does not compute a composite health score."


def _v(f: dict[str, Figure], mid: str) -> int | None:
    fig = f.get(mid)
    if fig is None or fig.status != "ok":
        return None
    return fig.money.minor if fig.money is not None else fig.value


def _worst(*bands: Band) -> Band:
    ranked = [b for b in bands if b in _ORDER]
    return max(ranked, key=_ORDER.index) if ranked else "not_computable"


def forecast_figures(fc: ForecastView) -> dict[str, Figure]:
    weeks = fc.weekly_closing_minor
    refs = [fc.forecast_run_id] if fc.forecast_run_id else []
    m = min(weeks)
    week_of_min = weeks.index(m) + 1
    first_below = next((i + 1 for i, c in enumerate(weeks) if c < fc.buffer_minor), None)
    money = lambda x: Money(minor=x, currency=fc.currency)  # noqa: E731
    buf_in = FigureInput(
        name="cash buffer",
        money=money(fc.buffer_minor),
        unit=Unit.MINOR,
        origin=Origin.TENANT_POLICY,
    )
    out = {
        "liquidity.forecast_min_cash": Figure(
            metric_id="liquidity.forecast_min_cash",
            label="Lowest forecast cash balance",
            money=money(m),
            unit=Unit.MINOR,
            formula="min over forecast weeks of closing cash",
            source_refs=refs,
            note=f"week {week_of_min}",
            inputs=[
                FigureInput(
                    name=f"week {i + 1} closing cash",
                    money=money(c),
                    unit=Unit.MINOR,
                    origin=Origin.FIGURE,
                )
                for i, c in enumerate(weeks)
            ],
        ),
        "liquidity.buffer_headroom_min": Figure(
            metric_id="liquidity.buffer_headroom_min",
            label="Smallest headroom above your buffer",
            money=money(m - fc.buffer_minor),
            unit=Unit.MINOR,
            formula="lowest forecast cash - buffer",
            source_refs=refs,
            inputs=[
                FigureInput(
                    name="lowest forecast cash",
                    money=money(m),
                    unit=Unit.MINOR,
                    origin=Origin.FIGURE,
                    ref="liquidity.forecast_min_cash",
                ),
                buf_in,
            ],
        ),
    }
    if first_below is None:
        out["liquidity.first_week_below_buffer"] = Figure(
            metric_id="liquidity.first_week_below_buffer",
            label="First week below your buffer",
            unit=Unit.WEEKS,
            status="not_applicable",
            note="no forecast week is below the buffer",
            source_refs=refs,
        )
    else:
        out["liquidity.first_week_below_buffer"] = Figure(
            metric_id="liquidity.first_week_below_buffer",
            label="First week below your buffer",
            value=first_below,
            unit=Unit.WEEKS,
            formula="first week with closing cash < buffer",
            inputs=[buf_in],
            source_refs=refs,
        )
    return out


def assess_health(
    ratios: dict[str, Figure],
    forecast: ForecastView | None = None,
    industry: str | None = None,
    hurdle_bp: int | None = None,
) -> HealthResult:
    f = dict(ratios)
    if forecast is not None:
        f.update(forecast_figures(forecast))
    dims: dict[str, Dimension] = {}

    # Liquidity
    cr_b = rulebook.bands_bp("T-LIQ-CR-01", industry)
    headroom, min_cash, cr = (
        _v(f, "liquidity.buffer_headroom_min"),
        _v(f, "liquidity.forecast_min_cash"),
        _v(f, "liquidity.current_ratio"),
    )
    if min_cash is not None and min_cash < rulebook.value("T-LIQ-FLOOR-01"):
        dims["liquidity"] = Dimension(
            band="critical",
            reasons=["forecast cash goes below zero"],
            metric_ids=["liquidity.forecast_min_cash"],
        )
    elif headroom is not None and headroom < 0:
        week = _v(f, "liquidity.first_week_below_buffer")
        dims["liquidity"] = Dimension(
            band="stressed",
            reasons=[f"forecast cash falls below your buffer in week {week}"],
            metric_ids=["liquidity.buffer_headroom_min", "liquidity.first_week_below_buffer"],
        )
    elif cr is not None:
        band: Band = "healthy" if cr >= cr_b["healthy_min"] else "watch"
        if forecast is None:
            band = (
                "healthy"
                if cr >= cr_b["healthy_min"]
                else "watch"
                if cr >= cr_b["watch_min"]
                else "stressed"
                if cr >= cr_b["stressed_min"]
                else "critical"
            )
        dims["liquidity"] = Dimension(
            band=band,
            reasons=[]
            if band == "healthy"
            else ["current ratio below the healthy band"]
            + ([] if forecast else ["no cash forecast: banded on the current ratio"]),
            metric_ids=["liquidity.current_ratio"],
        )
    else:
        dims["liquidity"] = Dimension(
            band="not_computable", reasons=["no forecast and no current ratio"]
        )

    # Profitability
    om, om_prior, gm_chg = (
        _v(f, "profit.operating_margin"),
        _v(f, "profit.operating_margin_prior"),
        _v(f, "profit.gross_margin_change"),
    )
    gm_b = rulebook.bands_bp("T-PRO-GM-01")
    roic = _v(f, "profit.roic")
    if om is None:
        dims["profitability"] = Dimension(band="not_computable", reasons=["no revenue"])
    elif om < 0 and om_prior is not None and om_prior < 0:
        dims["profitability"] = Dimension(
            band="critical",
            reasons=["operating loss two years running"],
            metric_ids=["profit.operating_margin"],
        )
    elif om < 0 or (gm_chg is not None and gm_chg < gm_b["stressed_below_change"]):
        dims["profitability"] = Dimension(
            band="stressed",
            reasons=["operating loss" if om < 0 else "gross margin fell sharply"],
            metric_ids=["profit.operating_margin", "profit.gross_margin_change"],
        )
    elif (gm_chg is not None and gm_chg < gm_b["watch_below_change"]) or (
        roic is not None and hurdle_bp is not None and roic < hurdle_bp
    ):
        reasons = []
        if gm_chg is not None and gm_chg < gm_b["watch_below_change"]:
            reasons.append("gross margin fell")
        if roic is not None and hurdle_bp is not None and roic < hurdle_bp:
            reasons.append("return on invested capital is below the hurdle rate")
        dims["profitability"] = Dimension(
            band="watch", reasons=reasons, metric_ids=["profit.gross_margin_change", "profit.roic"]
        )
    else:
        dims["profitability"] = Dimension(band="healthy", metric_ids=["profit.operating_margin"])

    # Solvency
    icr, dscr, nde, de = (
        _v(f, k)
        for k in (
            "solvency.interest_coverage",
            "solvency.dscr",
            "solvency.net_debt_to_ebitda",
            "solvency.debt_to_equity",
        )
    )
    icr_b, nde_b, de_b = (
        rulebook.bands_bp("T-SOL-ICR-01"),
        rulebook.bands_bp("T-SOL-NDE-01"),
        rulebook.bands_bp("T-SOL-DE-01"),
    )
    dscr_floor = rulebook.value_bp("T-SOL-DSCR-02")
    if icr is None and dscr is None:
        dims["solvency"] = Dimension(band="healthy", reasons=["no interest-bearing debt"])
    elif (icr is not None and icr < icr_b["stressed_min"]) or (
        dscr is not None and dscr < dscr_floor
    ):
        dims["solvency"] = Dimension(
            band="critical",
            reasons=["earnings do not cover interest or debt service"],
            metric_ids=["solvency.interest_coverage", "solvency.dscr"],
        )
    elif (icr is not None and icr < icr_b["watch_min"]) or (
        nde is not None and nde > nde_b["stressed_above"]
    ):
        dims["solvency"] = Dimension(
            band="stressed",
            reasons=["thin interest cover or high leverage"],
            metric_ids=["solvency.interest_coverage", "solvency.net_debt_to_ebitda"],
        )
    elif (
        (icr is not None and icr < icr_b["healthy_min"])
        or (nde is not None and nde > nde_b["watch_above"])
        or (de is not None and de > de_b["watch_above"])
    ):
        dims["solvency"] = Dimension(
            band="watch",
            reasons=["coverage or leverage outside the healthy band"],
            metric_ids=[
                "solvency.interest_coverage",
                "solvency.net_debt_to_ebitda",
                "solvency.debt_to_equity",
            ],
        )
    else:
        dims["solvency"] = Dimension(band="healthy", metric_ids=["solvency.interest_coverage"])

    # Efficiency
    inv_chg = _v(f, "efficiency.inventory_days_change")
    inv_b = rulebook.bands_bp("T-EFF-INV-01")
    if inv_chg is None:
        dims["efficiency"] = Dimension(
            band="not_computable", reasons=["needs inventory days for two years"]
        )
    elif inv_chg > inv_b["stressed_above_change"]:
        dims["efficiency"] = Dimension(
            band="stressed",
            reasons=["inventory days rose sharply"],
            metric_ids=["efficiency.inventory_days_change"],
        )
    elif inv_chg > inv_b["watch_above_change"]:
        dims["efficiency"] = Dimension(
            band="watch",
            reasons=["inventory days rose"],
            metric_ids=["efficiency.inventory_days_change"],
        )
    else:
        dims["efficiency"] = Dimension(
            band="healthy", metric_ids=["efficiency.inventory_days_change"]
        )

    # Cash generation
    cfo, cfo_prior, cfo_ni, fcf = (
        _v(f, k) for k in ("cash.cfo", "cash.cfo_prior", "cash.cfo_to_net_income", "cash.fcf")
    )
    cfoni_b = rulebook.bands_bp("T-CSH-CFONI-01")
    if cfo is None:
        dims["cash_generation"] = Dimension(
            band="not_computable", reasons=["no operating cash flow"]
        )
    elif cfo < 0 and cfo_prior is not None and cfo_prior < 0:
        dims["cash_generation"] = Dimension(
            band="critical",
            reasons=["operations consumed cash two years running"],
            metric_ids=["cash.cfo"],
        )
    elif cfo < 0 or (cfo_ni is not None and cfo_ni < cfoni_b["stressed_below"]):
        dims["cash_generation"] = Dimension(
            band="stressed", reasons=["operations consumed cash"], metric_ids=["cash.cfo"]
        )
    elif (cfo_ni is not None and cfo_ni < cfoni_b["watch_below"]) or (fcf is not None and fcf < 0):
        dims["cash_generation"] = Dimension(
            band="watch",
            reasons=["cash lags profit or free cash flow is negative"],
            metric_ids=["cash.cfo_to_net_income", "cash.fcf"],
        )
    else:
        dims["cash_generation"] = Dimension(band="healthy", metric_ids=["cash.cfo"])

    liq, sol, cg = dims["liquidity"].band, dims["solvency"].band, dims["cash_generation"].band
    if liq == "not_computable" and sol == "not_computable":
        overall: Band = "not_computable"
    elif "critical" in (liq, sol):
        overall = "critical"
    elif "stressed" in (liq, sol) or cg == "critical":
        overall = "stressed"
    elif any(d.band in ("watch", "stressed", "critical") for d in dims.values()):
        overall = "watch"
    else:
        overall = "healthy"

    divergences = []
    ni = _v(f, "is.net_income")
    if ni is not None and cfo is not None and ni > 0 and cfo < 0:
        divergences.append(
            {
                "id": "HLT-DIV-01",
                "name": "Profitable but cash-negative",
                "metric_ids": [
                    "is.net_income",
                    "cash.cfo",
                    "wc.inventory_change",
                    "wc.receivables_change",
                    "wc.payables_change",
                ],
            }
        )
    if headroom is not None and om is not None and headroom > 0 and om < 0:
        divergences.append(
            {
                "id": "HLT-DIV-02",
                "name": "Cash-rich but unprofitable",
                "metric_ids": ["liquidity.buffer_headroom_min", "profit.operating_margin"],
            }
        )

    used = {m for d in dims.values() for m in d.metric_ids}
    return HealthResult(
        overall=overall,
        dimensions=dims,
        divergences=divergences,
        figures=[f[m] for m in sorted(used) if m in f],
    )
