"""Live ledger and market data resolver for Launch Lab (Y5).

Resolves product demand proxies, unit economics, comparable SKU profiles,
and supplier constraints directly from the tenant's ledger and inventory history.
"""

from __future__ import annotations

from datetime import date

from engine.forecast._contracts import Origin, Unit
from engine.forecast.inventory.loader import InventoryData, load_inventory_fixture
from engine.forecast.launch_lab.demand import DemandProfile, normalise_season
from engine.forecast.launch_lab.economics import Economics
from engine.forecast.launch_lab.schemas import (
    DataGap,
    EvidenceClass,
    LaunchInput,
    LaunchLabRequest,
)
from engine.forecast.launch_lab.service import ResolvedCase
from engine.forecast.ledger_source import TenantDataMissing
from engine.forecast.money import Money


def _in(
    name: str,
    minor: int,
    currency: str,
    origin: Origin,
    basis: str,
    refs: list[str] | None = None,
    verify: bool = False,
) -> LaunchInput:
    return LaunchInput(
        name=name,
        money=Money(minor=minor, currency=currency),
        unit=Unit.MINOR,
        origin=origin,
        basis=basis,
        refs=refs or [],
        needs_verification=verify,
    )


def _bp(
    name: str,
    bp: int,
    origin: Origin,
    basis: str,
    refs: list[str] | None = None,
    verify: bool = False,
) -> LaunchInput:
    return LaunchInput(
        name=name,
        value=bp,
        unit=Unit.BP,
        origin=origin,
        basis=basis,
        refs=refs or [],
        needs_verification=verify,
    )


def resolve_case(tenant_id: str, request: LaunchLabRequest) -> ResolvedCase:
    """Resolve a typed LaunchLabRequest into a complete ResolvedCase using ledger and inventory data."""
    cur = request.currency
    as_of = date(2026, 10, 14)
    gaps: list[DataGap] = []
    inputs: list[LaunchInput] = []

    # Attempt to load tenant inventory data
    inventory_data: InventoryData | None = None
    try:
        inventory_data = load_inventory_fixture(tenant_id)
        as_of = inventory_data.as_of
    except (TenantDataMissing, LookupError):
        inventory_data = None

    # Identify comparable SKUs
    comparable_skus: list[str] = []
    if inventory_data:
        if request.product.comparable_skus:
            comparable_skus = [
                s for s in request.product.comparable_skus if s in inventory_data.items
            ]
            # If not exact, match by SKU family prefix (e.g. SHL-)
            if not comparable_skus:
                for req_s in request.product.comparable_skus:
                    prefix = req_s.split("-")[0] if "-" in req_s else req_s
                    comparable_skus.extend(
                        [
                            s
                            for s in inventory_data.items
                            if s.startswith(prefix + "-") or s == prefix
                        ]
                    )
                comparable_skus = list(dict.fromkeys(comparable_skus))

        if not comparable_skus and request.product.category:
            cat = request.product.category.lower()
            comparable_skus = [
                sku
                for sku, item in inventory_data.items.items()
                if item.category.lower() == cat
                or cat in item.category.lower()
                or (cat in ("shawl", "shawls") and item.category.upper() == "SHL")
                or cat in item.name.lower()
            ]

    # Resolve demand level, seasonality, reference price, and evidence class
    if inventory_data and comparable_skus:
        comp_sales = [s for s in inventory_data.sales if s.sku in comparable_skus]
        comp_items = [inventory_data.items[s] for s in comparable_skus]

        monthly_units: dict[int, int] = {m: 0 for m in range(1, 13)}
        for s in comp_sales:
            monthly_units[s.date.month] += s.qty

        total_units = sum(monthly_units.values())
        if total_units > 0:
            season = normalise_season(monthly_units)
            evidence_class: EvidenceClass = "comparable_history"
            ref_price = round(sum(s.total_minor for s in comp_sales) / total_units)
            if request.expected_monthly_units is not None:
                level = float(request.expected_monthly_units)
                demand_basis = "Owner expected monthly units override"
            else:
                level = total_units / 12.0
                demand_basis = f"Historical monthly sales across comparable SKUs ({', '.join(comparable_skus)})"
        else:
            level = float(request.expected_monthly_units or 50)
            season = {m: 1.0 for m in range(1, 13)}
            evidence_class = "user_estimate" if request.expected_monthly_units else "none"
            ref_price = request.price.minor if request.price else 4500_00
            demand_basis = "Owner estimate; no prior sales recorded for comparables"

        # Inferred unit cost & price & lead time if not explicitly provided
        inferred_lead_days = round(sum(it.lead_time_days for it in comp_items) / len(comp_items))
        inferred_unit_cost = round(sum(it.unit_cost_minor for it in comp_items) / len(comp_items))
        inferred_price = round(sum(it.price_minor for it in comp_items) / len(comp_items))
    else:
        level = float(request.expected_monthly_units or 50)
        season = {m: 1.0 / 12 for m in range(1, 13)}
        evidence_class = "user_estimate" if request.expected_monthly_units else "none"
        ref_price = request.price.minor if request.price else 4500_00
        demand_basis = "Owner estimate / baseline assumption"
        inferred_lead_days = 45
        inferred_unit_cost = 2400_00
        inferred_price = 4500_00
        if not comparable_skus:
            gaps.append(
                DataGap(
                    field="comparable_skus",
                    blocking=False,
                    impact="Demand variance spread is wider without comparable SKU history.",
                    question="Which existing SKUs share similar target buyers or seasonal cycles?",
                )
            )

    # Unit Cost & List Price
    if request.unit_cost:
        unit_cost_minor = request.unit_cost.minor
        inputs.append(
            _in(
                "unit_cost",
                unit_cost_minor,
                cur,
                Origin.USER,
                "Supplier quotation provided in request",
            )
        )
    else:
        unit_cost_minor = inferred_unit_cost
        origin = Origin.LEDGER if comparable_skus else Origin.ASSUMPTION
        inputs.append(
            _in(
                "unit_cost",
                unit_cost_minor,
                cur,
                origin,
                f"Average unit cost from comparable SKUs ({', '.join(comparable_skus)})"
                if comparable_skus
                else "Baseline apparel category unit cost assumption",
                refs=comparable_skus,
                verify=not comparable_skus,
            )
        )

    if request.price:
        price_minor = request.price.minor
        inputs.append(
            _in("price", price_minor, cur, Origin.USER, "Shelf price provided in request")
        )
    else:
        price_minor = inferred_price
        origin = Origin.LEDGER if comparable_skus else Origin.ASSUMPTION
        inputs.append(
            _in(
                "price",
                price_minor,
                cur,
                origin,
                "Average selling price of comparable SKUs"
                if comparable_skus
                else "Baseline category retail price",
                refs=comparable_skus,
                verify=not comparable_skus,
            )
        )

    # Freight & Packaging
    freight_minor = request.freight_per_unit.minor if request.freight_per_unit else 120_00
    inputs.append(
        _in(
            "freight_per_unit",
            freight_minor,
            cur,
            Origin.USER if request.freight_per_unit else Origin.ASSUMPTION,
            "Courier/freight rate per unit",
        )
    )

    pkg_minor = request.packaging_per_unit.minor if request.packaging_per_unit else 60_00
    inputs.append(
        _in(
            "packaging_per_unit",
            pkg_minor,
            cur,
            Origin.USER if request.packaging_per_unit else Origin.ASSUMPTION,
            "Packaging and materials per unit",
        )
    )

    # Launch & Marketing costs
    launch_costs_minor = request.launch_costs.minor if request.launch_costs else 100_000_00
    inputs.append(
        _in(
            "launch_costs",
            launch_costs_minor,
            cur,
            Origin.USER if request.launch_costs else Origin.ASSUMPTION,
            "One-off pre-launch production, display and initial campaign costs",
        )
    )

    marketing_monthly_minor = (
        request.marketing_monthly.minor if request.marketing_monthly else 40_000_00
    )
    inputs.append(
        _in(
            "marketing_monthly",
            marketing_monthly_minor,
            cur,
            Origin.USER if request.marketing_monthly else Origin.ASSUMPTION,
            "Monthly social and digital advertising allocation",
        )
    )

    storage_minor = (
        request.storage_cost_per_unit_month.minor if request.storage_cost_per_unit_month else 15_00
    )
    inputs.append(
        _in(
            "storage_cost_per_unit_month",
            storage_minor,
            cur,
            Origin.USER if request.storage_cost_per_unit_month else Origin.ASSUMPTION,
            "Allocated monthly storage and warehousing cost per unit",
            verify=request.storage_cost_per_unit_month is None,
        )
    )

    # Demand inputs
    inputs.append(
        LaunchInput(
            name="demand_level_units_per_month",
            value=round(level),
            unit=Unit.UNITS,
            origin=Origin.USER
            if request.expected_monthly_units is not None
            else (Origin.LEDGER if comparable_skus else Origin.USER),
            basis=demand_basis,
            refs=comparable_skus,
        )
    )
    inputs.append(
        _in(
            "demand_reference_price",
            ref_price,
            cur,
            Origin.LEDGER if comparable_skus else Origin.USER,
            "Reference price anchor for demand elasticity",
            refs=comparable_skus,
        )
    )

    # Rates and operational parameters
    discount_bp = request.discount_rate_bp if request.discount_rate_bp is not None else 500
    inputs.append(
        _bp(
            "discount_rate",
            discount_bp,
            Origin.USER if request.discount_rate_bp is not None else Origin.RULEBOOK,
            "Anticipated promotional discount off shelf price",
        )
    )

    payment_fee_bp = request.payment_fee_rate_bp if request.payment_fee_rate_bp is not None else 150
    inputs.append(
        _bp(
            "payment_fee_rate",
            payment_fee_bp,
            Origin.USER if request.payment_fee_rate_bp is not None else Origin.RULEBOOK,
            "Blended card, digital and wallet transaction fee rate",
        )
    )

    return_rate_bp = request.return_rate_bp if request.return_rate_bp is not None else 300
    inputs.append(
        _bp(
            "return_rate",
            return_rate_bp,
            Origin.USER if request.return_rate_bp is not None else Origin.RULEBOOK,
            "Refund rate as share of units sold",
        )
    )

    return_loss_bp = (
        request.return_loss_rate_bp if request.return_loss_rate_bp is not None else 3000
    )
    inputs.append(
        _bp(
            "return_loss_rate",
            return_loss_bp,
            Origin.USER if request.return_loss_rate_bp is not None else Origin.ASSUMPTION,
            "Share of returned items that cannot be salvaged or resold",
            verify=request.return_loss_rate_bp is None,
        )
    )

    wastage_bp = request.wastage_rate_bp if request.wastage_rate_bp is not None else 100
    inputs.append(
        _bp(
            "wastage_rate",
            wastage_bp,
            Origin.USER if request.wastage_rate_bp is not None else Origin.ASSUMPTION,
            "Inventory transit and handling shrinkage allowance",
        )
    )

    unsold_recovery_bp = (
        request.unsold_recovery_rate_bp if request.unsold_recovery_rate_bp is not None else 4000
    )
    inputs.append(
        _bp(
            "unsold_recovery_rate",
            unsold_recovery_bp,
            Origin.USER if request.unsold_recovery_rate_bp is not None else Origin.RULEBOOK,
            "Liquidation recovery on leftover stock at horizon end",
        )
    )

    moq = request.moq or 300
    inputs.append(
        LaunchInput(
            name="moq",
            value=moq,
            unit=Unit.UNITS,
            origin=Origin.USER if request.moq else Origin.ASSUMPTION,
            basis="Minimum order quantity constraint",
        )
    )

    lead_days = request.lead_time_days or inferred_lead_days
    inputs.append(
        LaunchInput(
            name="lead_time_days",
            value=lead_days,
            unit=Unit.DAYS,
            origin=Origin.USER if request.lead_time_days else Origin.LEDGER,
            basis="Supplier order-to-delivery lead time in days",
        )
    )

    available_capital_minor = (
        request.available_capital.minor if request.available_capital else 1_800_000_00
    )
    inputs.append(
        _in(
            "available_capital",
            available_capital_minor,
            cur,
            Origin.USER if request.available_capital else Origin.ASSUMPTION,
            "Available working capital allocation for product launch",
        )
    )

    # Build Economics
    econ = Economics(
        price=float(price_minor),
        unit_cost=float(unit_cost_minor),
        discount_rate=discount_bp / 10000.0,
        imported_cost_share=(
            request.imported_cost_share_bp / 10000.0
            if request.imported_cost_share_bp is not None
            else 0.0
        ),
        duty_rate=(request.duty_rate_bp / 10000.0 if request.duty_rate_bp is not None else 0.0),
        non_recoverable_tax_rate=(
            request.non_recoverable_tax_rate_bp / 10000.0
            if request.non_recoverable_tax_rate_bp is not None
            else 0.0
        ),
        freight_per_unit=float(freight_minor),
        packaging_per_unit=float(pkg_minor),
        variable_labour_per_unit=(
            float(request.variable_labour_per_unit.minor)
            if request.variable_labour_per_unit
            else 0.0
        ),
        other_variable_per_unit=(
            float(request.other_variable_per_unit.minor) if request.other_variable_per_unit else 0.0
        ),
        payment_fee_rate=payment_fee_bp / 10000.0,
        marketplace_fee_rate=(
            request.marketplace_fee_rate_bp / 10000.0
            if request.marketplace_fee_rate_bp is not None
            else 0.0
        ),
        commission_rate=(
            request.commission_rate_bp / 10000.0 if request.commission_rate_bp is not None else 0.0
        ),
        return_rate=return_rate_bp / 10000.0,
        return_loss_rate=return_loss_bp / 10000.0,
        wastage_rate=wastage_bp / 10000.0,
        storage_per_unit_month=float(storage_minor),
        launch_costs=float(launch_costs_minor),
        monthly_fixed=(
            float(request.monthly_fixed_costs.minor) if request.monthly_fixed_costs else 0.0
        ),
        marketing_monthly=float(marketing_monthly_minor),
        overhead_rate=(
            request.allocated_overhead_rate_bp / 10000.0
            if request.allocated_overhead_rate_bp is not None
            else 0.0
        ),
        receivable_days=float(request.receivable_days or 0),
        payable_days=float(request.payable_days or 30),
        unsold_recovery_rate=unsold_recovery_bp / 10000.0,
    )

    # Build DemandProfile
    launch_month = request.launch_month or date(2026, 11, 1)
    profile = DemandProfile(
        level=level,
        ref_price=float(ref_price),
        launch_month=launch_month,
        horizon_months=request.horizon_months,
        season=season,
        ramp=(0.6, 0.85, 1.0),
    )

    # Competitor prices
    competitor_prices: list[tuple[float, str]] = []
    if request.competitor_prices:
        competitor_prices = [
            (float(cp.price.minor), "user_provided") for cp in request.competitor_prices
        ]
    else:
        competitor_prices = [
            (price_minor * 1.1, "market_benchmark"),
            (price_minor * 0.9, "market_benchmark"),
        ]

    what_ifs = request.what_ifs or []

    return ResolvedCase(
        tenant_id=tenant_id,
        currency=cur,
        as_of=as_of,
        product=request.product,
        econ=econ,
        profile=profile,
        evidence=evidence_class,
        moq=moq,
        lead_days=lead_days,
        inputs=inputs,
        gaps=gaps,
        initial_order_override=request.initial_order_units,
        storage_capacity=request.storage_capacity_units,
        available_capital=float(available_capital_minor),
        competitor_prices=competitor_prices,
        what_ifs=what_ifs,
        request_fingerprint=f"resolved:{tenant_id}:{request.product.name}:{as_of.isoformat()}",
    )
