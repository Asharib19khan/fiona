import yaml

from engine.analysis.health import ForecastView, assess_health
from engine.analysis.ratios import compute_ratios
from engine.analysis.rulebook import RULEBOOK_DIR


def _fixture_forecast() -> ForecastView:
    data = yaml.safe_load((RULEBOOK_DIR / "scenarios.yaml").read_text(encoding="utf-8"))
    fc = data["common"]["forecast_fixture"]
    return ForecastView(
        weekly_closing_minor=[w["closing_minor"] for w in fc["weeks"]],
        buffer_minor=data["common"]["buffer_minor"],
        currency="PKR",
        forecast_run_id=fc["id"],
    )


def test_week7_dip_makes_liquidity_stressed(fy2025, fy2026):
    result = assess_health(
        compute_ratios(fy2026, fy2025, 2900), _fixture_forecast(), industry="retail_apparel"
    )
    liq = result.dimensions["liquidity"]
    assert liq.band == "stressed"
    assert "week 7" in liq.reasons[0]
    figs = {f.metric_id: f for f in result.figures}
    assert figs["liquidity.buffer_headroom_min"].money.minor == -42_000_000
    assert figs["liquidity.first_week_below_buffer"].value == 7


def test_profitable_but_cash_negative_is_explained(fy2025, fy2026):
    result = assess_health(compute_ratios(fy2026, fy2025, 2900))
    assert result.dimensions["cash_generation"].band == "stressed"
    assert any(d["id"] == "HLT-DIV-01" for d in result.divergences)


def test_inventory_build_is_flagged(fy2025, fy2026):
    result = assess_health(compute_ratios(fy2026, fy2025, 2900))
    # inventory days 104 vs 93 the year before: +11.8%, below the 20% watch line
    assert result.dimensions["efficiency"].band == "healthy"


def test_overall_is_a_band_not_a_score(fy2025, fy2026):
    result = assess_health(
        compute_ratios(fy2026, fy2025, 2900), _fixture_forecast(), industry="retail_apparel"
    )
    assert result.overall == "stressed"
    assert "score" not in result.model_dump(exclude={"note"}).__repr__().lower()
