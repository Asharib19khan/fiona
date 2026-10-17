"""Tests for the Dividend versus Reinvestment decision engine (Y4 Part 2 / Tier 2)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.app.main import app
from engine.decisions.dividend import compare_dividend
from engine.decisions.schemas import DecisionResponse, DividendRequest
from engine.forecast._contracts import Money
from engine.forecast.ledger_source import load_fixture_snapshot

TENANT = "ten_karachi_apparel"
client = TestClient(app)


def test_dividend_comparison_on_seeded_ledger():
    snapshot = load_fixture_snapshot(TENANT)
    body = DividendRequest(
        proposed_dividend=Money(minor=150_000_000, currency="PKR"),  # 1.5M PKR
        reinvestment_return_bp=1_800,
        owner_required_return_bp=1_500,
    )
    result = compare_dividend(body, snapshot, mode="mock", generated_at=datetime.now(UTC))

    assert isinstance(result, DecisionResponse)
    assert result.decision == "dividend"
    assert result.currency == "PKR"
    assert result.as_of == snapshot.as_of
    assert len(result.options) == 3

    option_ids = [opt.option_id for opt in result.options]
    assert "pay_now" in option_ids
    assert "reinvest" in option_ids
    assert any("pay_after_week" in opt_id for opt_id in option_ids)

    # Check integer minor units throughout
    for opt in result.options:
        for f in opt.figures:
            if f.money is not None:
                assert isinstance(f.money.minor, int)
                assert f.money.currency == "PKR"

    assert result.recommendation.outcome in ("recommend", "no_clear_winner")
    assert result.recommendation.option_id is not None
    assert len(result.recommendation.rule_trace) > 0


def test_dividend_api_endpoint_serves_fixture_backed_response():
    resp = client.post(
        "/v1/decisions/dividend",
        headers={"X-Fiona-Tenant": TENANT, "X-Fiona-Mode": "mock"},
        json={
            "proposed_dividend": {"minor": 150_000_000, "currency": "PKR"},
            "reinvestment_return_bp": 2_000,
            "owner_required_return_bp": 1_500,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["decision"] == "dividend"
    assert data["currency"] == "PKR"
    assert len(data["options"]) == 3
    assert data["recommendation"]["outcome"] == "recommend"


def test_large_dividend_breaches_buffer_and_marks_pay_now_ineligible():
    snapshot = load_fixture_snapshot(TENANT)
    # Propose massive 20M PKR dividend which exceeds entire bank balance
    body = DividendRequest(
        proposed_dividend=Money(minor=2_000_000_000, currency="PKR"),
        reinvestment_return_bp=1_800,
    )
    result = compare_dividend(body, snapshot, mode="mock")

    pay_now = next(opt for opt in result.options if opt.option_id == "pay_now")
    assert pay_now.eligible is False

    dv01 = next(chk for chk in pay_now.rule_checks if chk.rule_id == "DV-01")
    assert dv01.passed is False


def test_small_safe_dividend_recommends_pay_now_when_hurdle_rate_low():
    snapshot = load_fixture_snapshot(TENANT)
    # Propose 100k PKR which easily fits in liquid buffer headroom
    body = DividendRequest(
        proposed_dividend=Money(minor=10_000_000, currency="PKR"),
        reinvestment_return_bp=1_200,
        owner_required_return_bp=1_500,
    )
    result = compare_dividend(body, snapshot, mode="mock")

    pay_now = next(opt for opt in result.options if opt.option_id == "pay_now")
    if pay_now.eligible:
        assert result.recommendation.option_id == "pay_now"
        assert "cash_stays_above_buffer" in result.recommendation.reason_codes


SNAPSHOT = load_fixture_snapshot(TENANT)


@settings(max_examples=25)
@given(
    proposed_minor=st.integers(min_value=100_000, max_value=500_000_000),
    reinvest_bp=st.integers(min_value=0, max_value=5_000),
)
def test_property_dividend_cash_path_never_invents_floats(proposed_minor: int, reinvest_bp: int):
    body = DividendRequest(
        proposed_dividend=Money(minor=proposed_minor, currency="PKR"),
        reinvestment_return_bp=reinvest_bp,
    )
    result = compare_dividend(body, SNAPSHOT, mode="mock")

    for opt in result.options:
        if opt.cash_path:
            for pt in opt.cash_path:
                assert isinstance(pt.closing_with.minor, int)
                assert isinstance(pt.closing_without.minor, int)
                assert pt.closing_with.currency == "PKR"
