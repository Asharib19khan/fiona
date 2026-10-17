"""Tests for Launch Lab ledger resolver (Y5).

Verifies:
- Resolves comparable SKU sales history, demand profile, seasonality, and reference price.
- Inferred unit cost, price, and lead time when not supplied by user.
- Explicit user overrides take precedence over historical averages.
- Fallback behaviour with honest data gap reporting when comparable SKUs are absent.
- Full end-to-end simulation via POST /v1/launch-lab/simulate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from engine.app.main import create_app
from engine.forecast.launch_lab.resolver import resolve_case
from engine.forecast.launch_lab.schemas import LaunchLabRequest, ProductSpec
from engine.forecast.money import Money

TENANT = "ten_karachi_apparel"
PKR = "PKR"


def test_resolver_with_comparable_skus():
    """When comparable SKUs exist in inventory, resolver infers demand profile, seasonality, and prices."""
    req = LaunchLabRequest(
        currency=PKR,
        product=ProductSpec(
            name="Cashmere wedding shawl",
            category="shawl",
            comparable_skus=["SHL-WOL-GRY", "SHL-WOL-BRN"],
        ),
    )
    case = resolve_case(TENANT, req)

    assert case.currency == PKR
    assert case.evidence == "comparable_history"
    assert case.profile.level > 0
    # Seasonality normalized around mean 1.0 (sums to 12.0 across 12 calendar months)
    assert sum(case.profile.season.values()) == pytest.approx(12.0, abs=1e-4)
    # Unit cost and price inferred from comparable SKUs
    assert case.econ.unit_cost > 0
    assert case.econ.price > 0
    assert case.lead_days > 0


def test_resolver_user_inputs_take_precedence():
    """Explicit user inputs take precedence over inferred ledger averages and are tagged Origin.USER."""
    req = LaunchLabRequest(
        currency=PKR,
        product=ProductSpec(name="Luxury Velvet Stole", category="shawl"),
        unit_cost=Money(minor=3200_00, currency=PKR),
        price=Money(minor=6800_00, currency=PKR),
        lead_time_days=25,
        expected_monthly_units=120,
    )
    case = resolve_case(TENANT, req)

    assert case.econ.unit_cost == 3200_00
    assert case.econ.price == 6800_00
    assert case.lead_days == 25
    assert case.profile.level == 120.0

    cost_input = next(i for i in case.inputs if i.name == "unit_cost")
    assert cost_input.origin == "user_provided" or cost_input.origin == "user"


def test_resolver_missing_comparables_reports_data_gap():
    """When category or comparable SKUs are unknown, a clear non-blocking data gap is recorded."""
    req = LaunchLabRequest(
        currency=PKR,
        product=ProductSpec(name="Experimental Drone Widget", category="robotics"),
        expected_monthly_units=30,
    )
    case = resolve_case(TENANT, req)

    assert case.evidence == "user_estimate"
    assert any(gap.field == "comparable_skus" for gap in case.gaps)


def test_api_launch_lab_simulate_live():
    """POST /v1/launch-lab/simulate runs the resolver and simulation engine end-to-end."""
    client = TestClient(create_app(modules=["forecast"]))
    res = client.post(
        "/v1/launch-lab/simulate",
        json={
            "currency": PKR,
            "product": {
                "name": "Pashmina winter shawl",
                "category": "shawl",
                "comparable_skus": ["SHL-WOL-GRY", "SHL-WOL-BRN"],
            },
            "unit_cost": {"minor": 240000, "currency": PKR},
            "price": {"minor": 450000, "currency": PKR},
            "simulation_runs": 300,
        },
        headers={"X-Fiona-Tenant": TENANT, "X-Fiona-Mode": "mock"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["api_version"] == "v1"
    assert data["mode"] == "mock"
    assert "recommendation" in data
    assert data["recommendation"]["label"] in {
        "LAUNCH",
        "PILOT_FIRST",
        "REVISE",
        "HOLD",
        "NOT_RECOMMENDED",
    }
    assert len(data["scenarios"]) == 3  # low, base, high
