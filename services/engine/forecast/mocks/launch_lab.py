"""Mock Launch Lab run: the winter-shawl scenario from the roadmap (Y5 'done when').

The inputs are what a resolver would produce for the synthetic Karachi tenant: the owner's
supplier quote and price, comparable shawls from the ledger for demand, and labelled
assumptions for everything else. The analysis itself is the real engine.
"""

from __future__ import annotations

from datetime import date

from engine.forecast._contracts import Origin, Unit
from engine.forecast.launch_lab.demand import DemandProfile, normalise_season
from engine.forecast.launch_lab.economics import Economics
from engine.forecast.launch_lab.policy import load_policy
from engine.forecast.launch_lab.schemas import (
    DataGap,
    LaunchInput,
    LaunchLabResponse,
    ProductSpec,
)
from engine.forecast.launch_lab.service import ResolvedCase, analyse
from engine.forecast.mocks import AS_OF, CURRENCY, GENERATED_AT, MOCK_TENANT
from engine.forecast.money import Money

RUNS = 2000  # fewer than the policy default to keep the mock file small; stated in the payload

# Comparable shawls' monthly units by calendar month (synthetic ledger, two winters averaged).
SHAWL_SEASON = {1: 180, 2: 90, 3: 20, 4: 5, 5: 2, 6: 2, 7: 2, 8: 5, 9: 20, 10: 70, 11: 130, 12: 170}


def _in(
    name: str, rupees: float, origin: Origin, basis: str, refs=None, verify=False
) -> LaunchInput:
    return LaunchInput(
        name=name,
        money=Money(minor=round(rupees * 100), currency=CURRENCY),
        unit=Unit.MINOR,
        origin=origin,
        basis=basis,
        refs=refs or [],
        needs_verification=verify,
    )


def _bp(name: str, bp: int, origin: Origin, basis: str, verify=False) -> LaunchInput:
    return LaunchInput(
        name=name, value=bp, unit=Unit.BP, origin=origin, basis=basis, needs_verification=verify
    )


def case() -> ResolvedCase:
    level = sum(SHAWL_SEASON.values()) / 12
    econ = Economics(
        price=4500_00,
        unit_cost=2400_00,
        discount_rate=0.05,
        freight_per_unit=120_00,
        packaging_per_unit=60_00,
        payment_fee_rate=0.015,
        return_rate=0.03,
        return_loss_rate=0.30,
        wastage_rate=0.01,
        storage_per_unit_month=15_00,
        launch_costs=100_000_00,
        marketing_monthly=40_000_00,
        payable_days=30,
        unsold_recovery_rate=0.40,
    )
    inputs = [
        _in(
            "unit_cost",
            2400,
            Origin.USER,
            "Supplier quotation from sup_031 for 300+ units.",
            ["sup_031"],
        ),
        _in("price", 4500, Origin.USER, "Owner's proposed shelf price, GST included."),
        _in("freight_per_unit", 120, Origin.USER, "Courier rate quoted by the supplier."),
        _in("packaging_per_unit", 60, Origin.USER, "Gift box and tissue."),
        _in(
            "launch_costs",
            100_000,
            Origin.USER,
            "Photoshoot, window display and first social campaign.",
        ),
        _in("marketing_monthly", 40_000, Origin.USER, "Planned monthly social ads."),
        _in(
            "storage_cost_per_unit_month",
            15,
            Origin.ASSUMPTION,
            "Share of back-room rent; verify.",
            verify=True,
        ),
        LaunchInput(
            name="demand_level_units_per_month",
            value=round(level),
            unit=Unit.UNITS,
            origin=Origin.LEDGER,
            basis="Average monthly units of comparable wool shawls over the last 24 months.",
            refs=["SHL-WOL-GRY", "SHL-WOL-BRN"],
        ),
        _in(
            "demand_reference_price",
            3500,
            Origin.LEDGER,
            "Average selling price of the comparable shawls.",
            ["SHL-WOL-GRY", "SHL-WOL-BRN"],
        ),
        _bp(
            "seasonality_peak_index",
            round(SHAWL_SEASON[1] / level * 10_000),
            Origin.LEDGER,
            "January index of comparable shawl sales; Nov-Feb carry 85% of the year.",
        ),
        _bp(
            "price_elasticity_medium",
            -12_000,
            Origin.ASSUMPTION,
            "No price experiments in the ledger; medium-sensitivity scenario from the rulebook.",
            verify=True,
        ),
        _bp("discount_rate", 500, Origin.LEDGER, "Average discount on shawls last winter."),
        _bp(
            "payment_fee_rate",
            150,
            Origin.LEDGER,
            "Card and QR settlement fees as a share of shawl takings.",
        ),
        _bp("return_rate", 300, Origin.LEDGER, "Refunded share of comparable shawl sales."),
        _bp(
            "return_loss_rate",
            3000,
            Origin.ASSUMPTION,
            "Share of returned shawls that cannot be resold; verify.",
            verify=True,
        ),
        _bp("wastage_rate", 100, Origin.ASSUMPTION, "Transit damage allowance."),
        _bp(
            "unsold_recovery_rate",
            4000,
            Origin.RULEBOOK,
            "Apparel industry pack: unsold seasonal stock clears at 40% of cost.",
        ),
        LaunchInput(
            name="moq",
            value=300,
            unit=Unit.UNITS,
            origin=Origin.USER,
            basis="Supplier minimum order.",
        ),
        LaunchInput(
            name="lead_time_days",
            value=45,
            unit=Unit.DAYS,
            origin=Origin.USER,
            basis="Supplier lead time.",
        ),
        _in(
            "available_capital",
            1_800_000,
            Origin.USER,
            "Cash the owner has set aside for this product.",
        ),
    ]
    return ResolvedCase(
        tenant_id=MOCK_TENANT,
        currency=CURRENCY,
        as_of=AS_OF,
        product=ProductSpec(
            name="Pashmina-blend winter shawl",
            category="shawl",
            description="Mid-price pashmina-blend shawl in four colours for the winter wedding season.",
            target_customers="Women 25-45 shopping for winter weddings",
            target_market="Karachi, in store and Instagram",
            region="PK-KHI",
            sales_channels=["store", "instagram"],
            comparable_skus=["SHL-WOL-GRY", "SHL-WOL-BRN"],
        ),
        econ=econ,
        profile=DemandProfile(
            level=level,
            ref_price=3500_00,
            launch_month=date(2026, 11, 1),
            horizon_months=6,
            season=normalise_season(SHAWL_SEASON),
            ramp=(0.6, 0.85, 1.0),
        ),
        evidence="comparable_history",
        moq=300,
        lead_days=45,
        inputs=inputs,
        gaps=[
            DataGap(
                field="storage_cost_per_unit_month",
                blocking=False,
                impact="Small: under 1% of contribution in the base case.",
                question="Roughly how much of your back-room rent should a box of shawls carry each month?",
            )
        ],
        available_capital=1_800_000_00,
        competitor_prices=[
            (4990_00, "user_provided"),
            (3990_00, "user_provided"),
            (5500_00, "user_provided"),
        ],
        request_fingerprint="mock:winter_shawl:v1",
    )


def build() -> LaunchLabResponse:
    policy, sources = load_policy()
    return analyse(case(), policy, sources, mode="mock", generated_at=GENERATED_AT, runs=RUNS)
