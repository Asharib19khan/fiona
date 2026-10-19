"""Default per-unit costs scale with the product's unit cost, and the owner's figures win."""

from __future__ import annotations

from engine.forecast.launch_lab.resolver import resolve_case
from engine.forecast.launch_lab.schemas import LaunchLabRequest, ProductSpec
from engine.forecast.money import Money


def _inputs(**extra: object) -> dict[str, object]:
    req = LaunchLabRequest(
        currency="PKR",
        product=ProductSpec(name="Test product", category="baby clothes"),
        unit_cost=Money(minor=2_000, currency="PKR"),
        price=Money(minor=5_000, currency="PKR"),
        **extra,
    )
    return {i.name: i for i in resolve_case("ten_karachi_apparel", req).inputs}


def test_a_cheap_product_gets_a_proportionate_default() -> None:
    inputs = _inputs()
    # PKR 20 unit cost: 5% freight is PKR 1, 2.5% packaging is PKR 0.50 (was PKR 120 and PKR 60).
    assert inputs["freight_per_unit"].money.minor == 100
    assert inputs["packaging_per_unit"].money.minor == 50
    assert inputs["freight_per_unit"].origin.value == "assumption_unverified"
    assert "5% of unit cost" in inputs["freight_per_unit"].basis


def test_the_owners_figures_are_used_as_given() -> None:
    inputs = _inputs(
        freight_per_unit=Money(minor=0, currency="PKR"),
        packaging_per_unit=Money(minor=700, currency="PKR"),
    )
    assert inputs["freight_per_unit"].money.minor == 0
    assert inputs["packaging_per_unit"].money.minor == 700
    assert inputs["packaging_per_unit"].origin.value == "user_provided"
