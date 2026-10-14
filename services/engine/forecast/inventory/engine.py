"""Computed inventory analytics: ABC-XYZ, movement, cash tied up and reorder drafts."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations
from math import sqrt

from engine.forecast._contracts import (
    Action,
    Evidence,
    Finding,
    Money,
    Origin,
    Period,
    Threshold,
    Unit,
)
from engine.forecast.figures import (
    InsufficientData,
    bp_figure,
    bp_threshold,
    money_figure,
    stable_id,
    to_bp,
    value_figure,
)
from engine.forecast.inventory.loader import InventoryData, InventoryItemRecord, SaleLine
from engine.forecast.inventory.schemas import (
    BundleCandidate,
    DraftPOLine,
    DraftPurchaseOrder,
    InventoryAnalysisResponse,
    InventoryItem,
    SizeShare,
    StyleRollup,
)

WINDOW_DAYS = 90
ABC_A_CUMULATIVE_SHARE = Decimal("0.80")
ABC_B_CUMULATIVE_SHARE = Decimal("0.95")
XYZ_X_MAX_CV = Decimal("0.50")
XYZ_Y_MAX_CV = Decimal("1.00")
DEAD_AFTER_DAYS = 90
SLOW_ABOVE_DAYS = 180
SERVICE_LEVEL = Decimal("0.90")

ABC_BASIS = "revenue"
COVER_TARGET_DAYS = 60
FAST_BELOW_DAYS = 21
REORDER_COVER_DAYS = 30
XYZ_MIN_WEEKS = 4
SAFETY_STOCK_FACTOR = Decimal("1.2816")


@dataclass(frozen=True)
class _Metrics:
    units_sold: int
    revenue_minor: int
    gross_margin_minor: int
    last_sold_on: date | None
    weekly_demand: list[int]
    source_refs: list[str]


def analyse_inventory(
    data: InventoryData, *, as_of: date, generated_at: datetime, mode: str
) -> InventoryAnalysisResponse:
    window = Period(start=as_of - timedelta(days=WINDOW_DAYS - 1), end=as_of)
    sales_in_window = [sale for sale in data.sales if window.start <= sale.date <= window.end]
    metrics = _metrics_by_sku(data.items, sales_in_window, window)
    on_hand, insufficient = _on_hand_by_sku(data)
    abc = _abc_classes(data.items, metrics)

    items = [
        _inventory_item(item, metrics[item.sku], on_hand[item.sku], abc[item.sku], window, as_of)
        for item in sorted(data.items.values(), key=lambda item: item.sku)
    ]
    styles = _style_rollups(items, data.currency)
    draft_pos = _draft_purchase_orders(data, items, as_of)
    bundles, bundle_note = _bundles(sales_in_window)
    if bundle_note is not None:
        insufficient.append(bundle_note)

    stock_total = sum(item.stock_value.minor for item in items)
    dead_value = sum(item.cash_tied_up.minor for item in items if item.movement == "dead")
    slow_value = sum(item.cash_tied_up.minor for item in items if item.movement == "slow")
    gross_margin_total = sum(item.gross_margin_window.minor for item in items)
    gmroi = (
        Decimal(gross_margin_total) * Decimal(365) / Decimal(WINDOW_DAYS) / Decimal(stock_total)
        if stock_total
        else Decimal(0)
    )

    run_id = stable_id("inv", "engine", data.tenant_id, data.source_hash, as_of.isoformat())
    findings = _findings(items, run_id, window, generated_at, data.currency)

    return InventoryAnalysisResponse(
        api_version="v1",
        mode=mode,
        tenant_id=data.tenant_id,
        generated_at=generated_at,
        run_id=run_id,
        currency=data.currency,
        as_of=as_of,
        window=window,
        parameters=_parameters(),
        summary=[
            money_figure("inventory.stock_value", "Stock at cost", stock_total, data.currency),
            money_figure(
                "inventory.dead_stock_value", "Dead stock at cost", dead_value, data.currency
            ),
            money_figure(
                "inventory.slow_stock_value",
                "Slow stock above 60 days' cover",
                slow_value,
                data.currency,
            ),
            value_figure("inventory.sku_count", "SKUs", len(items), Unit.COUNT),
            bp_figure("inventory.gmroi", "Gross margin return on inventory (annualised)", gmroi),
        ],
        items=items,
        styles=styles,
        bundles=bundles,
        draft_purchase_orders=draft_pos,
        findings=findings,
        insufficient_data=insufficient,
    )


def _parameters() -> list[Threshold]:
    return [
        bp_threshold("abc_a_cumulative_share", ABC_A_CUMULATIVE_SHARE, Origin.DRAFT_DEFAULT, "<="),
        bp_threshold("abc_b_cumulative_share", ABC_B_CUMULATIVE_SHARE, Origin.DRAFT_DEFAULT, "<="),
        bp_threshold("xyz_x_max_cv", XYZ_X_MAX_CV, Origin.DRAFT_DEFAULT, "<="),
        bp_threshold("xyz_y_max_cv", XYZ_Y_MAX_CV, Origin.DRAFT_DEFAULT, "<="),
        Threshold(
            name="dead_after_days_without_sale",
            value=DEAD_AFTER_DAYS,
            unit=Unit.DAYS,
            origin=Origin.DRAFT_DEFAULT,
            comparison=">=",
        ),
        Threshold(
            name="slow_above_days_of_cover",
            value=SLOW_ABOVE_DAYS,
            unit=Unit.DAYS,
            origin=Origin.DRAFT_DEFAULT,
            comparison=">",
        ),
        bp_threshold("service_level", SERVICE_LEVEL, Origin.DRAFT_DEFAULT, ">="),
        Threshold(
            name="analysis_window_days",
            value=WINDOW_DAYS,
            unit=Unit.DAYS,
            origin=Origin.ASSUMPTION,
            comparison=">=",
        ),
        Threshold(
            name="cover_target_days",
            value=COVER_TARGET_DAYS,
            unit=Unit.DAYS,
            origin=Origin.ASSUMPTION,
            comparison=">=",
        ),
        Threshold(
            name="fast_below_days_of_cover",
            value=FAST_BELOW_DAYS,
            unit=Unit.DAYS,
            origin=Origin.ASSUMPTION,
            comparison="<",
        ),
        Threshold(
            name="reorder_cover_days",
            value=REORDER_COVER_DAYS,
            unit=Unit.DAYS,
            origin=Origin.ASSUMPTION,
            comparison=">=",
        ),
        Threshold(
            name="xyz_min_weeks",
            value=XYZ_MIN_WEEKS,
            unit=Unit.WEEKS,
            origin=Origin.ASSUMPTION,
            comparison=">=",
        ),
        bp_threshold("safety_stock_factor", SAFETY_STOCK_FACTOR, Origin.ASSUMPTION, ">="),
        Threshold(
            name="abc_basis_revenue",
            value=1,
            unit=Unit.COUNT,
            origin=Origin.ASSUMPTION,
            comparison=">=",
        ),
    ]


def _metrics_by_sku(
    items: dict[str, InventoryItemRecord], sales: list[SaleLine], window: Period
) -> dict[str, _Metrics]:
    by_sku: dict[str, list[SaleLine]] = defaultdict(list)
    for sale in sales:
        if sale.sku in items:
            by_sku[sale.sku].append(sale)

    out = {}
    for sku in items:
        sku_sales = by_sku.get(sku, [])
        weekly = [0 for _ in range(((window.end - window.start).days // 7) + 1)]
        for sale in sku_sales:
            week = min((sale.date - window.start).days // 7, len(weekly) - 1)
            weekly[week] += sale.qty
        positive_sales = [sale.date for sale in sku_sales if sale.qty > 0]
        out[sku] = _Metrics(
            units_sold=sum(sale.qty for sale in sku_sales),
            revenue_minor=sum(sale.total_minor for sale in sku_sales),
            gross_margin_minor=sum(
                sale.total_minor - sale.cost_minor * sale.qty for sale in sku_sales
            ),
            last_sold_on=max(positive_sales) if positive_sales else None,
            weekly_demand=weekly,
            source_refs=sorted({sale.source_ref for sale in sku_sales})[:10],
        )
    return out


def _on_hand_by_sku(data: InventoryData) -> tuple[dict[str, int], list[InsufficientData]]:
    on_hand = {sku: item.opening_stock_qty for sku, item in data.items.items()}
    for movement in data.stock_movements:
        if movement.sku in on_hand and movement.date <= data.as_of:
            on_hand[movement.sku] += movement.qty
    for sale in data.sales:
        if sale.sku in on_hand and sale.date <= data.as_of:
            on_hand[sale.sku] -= sale.qty

    clamped = sorted(sku for sku, qty in on_hand.items() if qty < 0)
    for sku in clamped:
        on_hand[sku] = 0
    notes = (
        [
            InsufficientData(
                need="Reconcile stock movements for negative on-hand SKUs",
                why="Computed on-hand stock went below zero, so the engine clamped it to zero.",
                blocking=False,
                metric_ids=["inventory.stock_value"],
            )
        ]
        if clamped
        else []
    )
    return on_hand, notes


def _abc_classes(
    items: dict[str, InventoryItemRecord], metrics: dict[str, _Metrics]
) -> dict[str, str]:
    basis = {sku: max(0, metrics[sku].revenue_minor) for sku in items}
    total = sum(basis.values())
    if total <= 0:
        return {sku: "C" for sku in items}

    out, running = {}, 0
    for sku, value in sorted(basis.items(), key=lambda pair: (-pair[1], pair[0])):
        share_before = Decimal(running) / Decimal(total)
        out[sku] = (
            "A"
            if share_before < ABC_A_CUMULATIVE_SHARE
            else "B"
            if share_before < ABC_B_CUMULATIVE_SHARE
            else "C"
        )
        running += value
    return out


def _inventory_item(
    item: InventoryItemRecord,
    metrics: _Metrics,
    on_hand: int,
    abc: str,
    window: Period,
    as_of: date,
) -> InventoryItem:
    daily = (
        Decimal(metrics.units_sold) / Decimal(WINDOW_DAYS) if metrics.units_sold > 0 else Decimal(0)
    )
    days_of_cover = _round_int(Decimal(on_hand) / daily) if daily > 0 else None
    movement = _movement(item, metrics, days_of_cover, window, as_of)
    stock_value = on_hand * item.unit_cost_minor
    safety_stock = (
        _round_int(
            SAFETY_STOCK_FACTOR
            * _demand_cv_decimal(metrics.weekly_demand)
            * daily
            * Decimal(REORDER_COVER_DAYS)
            * (Decimal(item.lead_time_days) / Decimal(REORDER_COVER_DAYS)).sqrt()
        )
        if daily > 0
        else 0
    )
    lead_time_demand = _round_int(daily * Decimal(item.lead_time_days)) if daily > 0 else 0
    reorder_point = lead_time_demand + safety_stock
    target_units = daily * Decimal(COVER_TARGET_DAYS)
    suggested_order_qty = (
        max(
            0,
            _round_int(daily * Decimal(item.lead_time_days + REORDER_COVER_DAYS))
            + safety_stock
            - on_hand,
        )
        if on_hand <= reorder_point
        else 0
    )
    gross_margin_bp = (
        to_bp(Decimal(metrics.gross_margin_minor) / Decimal(metrics.revenue_minor))
        if metrics.revenue_minor > 0
        else None
    )
    turnover_bp = (
        to_bp(
            Decimal(metrics.units_sold)
            * Decimal(item.unit_cost_minor)
            * Decimal(365)
            / Decimal(WINDOW_DAYS)
            / Decimal(stock_value)
        )
        if stock_value > 0 and metrics.units_sold > 0
        else None
    )
    gmroi_bp = (
        to_bp(
            Decimal(metrics.gross_margin_minor)
            * Decimal(365)
            / Decimal(WINDOW_DAYS)
            / Decimal(stock_value)
        )
        if stock_value > 0 and metrics.revenue_minor > 0
        else None
    )
    excess_units = max(Decimal(0), Decimal(on_hand) - target_units)
    cash_tied_up = (
        stock_value if movement == "dead" else _round_int(excess_units * item.unit_cost_minor)
    )

    return InventoryItem(
        sku=item.sku,
        name=item.name,
        category=item.category,
        style=_style_code(item.sku),
        size=item.size,
        colour=item.colour,
        season=item.season,
        on_hand=on_hand,
        unit_cost=Money(minor=item.unit_cost_minor, currency=item.currency),
        price=Money(minor=item.price_minor, currency=item.currency),
        stock_value=Money(minor=stock_value, currency=item.currency),
        units_sold_window=metrics.units_sold,
        revenue_window=Money(minor=metrics.revenue_minor, currency=item.currency),
        gross_margin_window=Money(minor=metrics.gross_margin_minor, currency=item.currency),
        gross_margin_bp=gross_margin_bp,
        abc=abc,
        xyz=_xyz(metrics.weekly_demand),
        demand_cv_bp=to_bp(_demand_cv_decimal(metrics.weekly_demand))
        if _has_xyz_history(metrics.weekly_demand)
        else None,
        movement=movement,
        days_of_cover=days_of_cover,
        last_sold_on=metrics.last_sold_on,
        lead_time_days=item.lead_time_days,
        safety_stock=safety_stock,
        reorder_point=reorder_point,
        suggested_order_qty=suggested_order_qty,
        turnover_bp=turnover_bp,
        gmroi_bp=gmroi_bp,
        cash_tied_up=Money(minor=cash_tied_up, currency=item.currency),
        source_refs=["items.csv", *metrics.source_refs],
    )


def _movement(
    item: InventoryItemRecord,
    metrics: _Metrics,
    days_of_cover: int | None,
    window: Period,
    as_of: date,
) -> str:
    if item.launched_on >= window.start:
        return "new"
    if metrics.last_sold_on is None:
        if (as_of - item.launched_on).days >= DEAD_AFTER_DAYS:
            return "dead"
    elif (as_of - metrics.last_sold_on).days >= DEAD_AFTER_DAYS:
        return "dead"
    if days_of_cover is not None and days_of_cover > SLOW_ABOVE_DAYS:
        return "slow"
    if days_of_cover is not None and days_of_cover < FAST_BELOW_DAYS:
        return "fast"
    return "normal"


def _xyz(weekly_demand: list[int]) -> str | None:
    if not _has_xyz_history(weekly_demand):
        return None
    cv = _demand_cv_decimal(weekly_demand)
    if cv <= XYZ_X_MAX_CV:
        return "X"
    if cv <= XYZ_Y_MAX_CV:
        return "Y"
    return "Z"


def _has_xyz_history(weekly_demand: list[int]) -> bool:
    return len(weekly_demand) >= XYZ_MIN_WEEKS and sum(weekly_demand) > 0


def _demand_cv_decimal(weekly_demand: list[int]) -> Decimal:
    if not _has_xyz_history(weekly_demand):
        return Decimal(0)
    mean = Decimal(sum(weekly_demand)) / Decimal(len(weekly_demand))
    variance = sum((Decimal(value) - mean) ** 2 for value in weekly_demand) / Decimal(
        len(weekly_demand)
    )
    return Decimal(str(sqrt(float(variance)))) / mean if mean > 0 else Decimal(0)


def _style_rollups(items: list[InventoryItem], currency: str) -> list[StyleRollup]:
    grouped: dict[str, list[InventoryItem]] = defaultdict(list)
    for item in items:
        grouped[item.style].append(item)

    out = []
    for style, variants in sorted(grouped.items()):
        sold = sum(item.units_sold_window for item in variants)
        size_counts: Counter[str] = Counter()
        for item in variants:
            if item.size:
                size_counts[item.size] += item.units_sold_window
        size_curve = [
            SizeShare(size=size, share_bp=to_bp(Decimal(count) / Decimal(sold)))
            for size, count in sorted(size_counts.items())
            if sold > 0
        ]
        strongest = max(variants, key=lambda item: (item.units_sold_window, item.sku))
        weakest = min(variants, key=lambda item: (item.units_sold_window, item.sku))
        out.append(
            StyleRollup(
                style=style,
                name=variants[0].name.rsplit(" - ", 2)[0],
                skus=[item.sku for item in variants],
                on_hand=sum(item.on_hand for item in variants),
                stock_value=Money(
                    minor=sum(item.stock_value.minor for item in variants), currency=currency
                ),
                units_sold_window=sold,
                size_curve=size_curve,
                strongest_sku=strongest.sku if variants else None,
                weakest_sku=weakest.sku if variants else None,
            )
        )
    return out


def _draft_purchase_orders(
    data: InventoryData, items: list[InventoryItem], as_of: date
) -> list[DraftPurchaseOrder]:
    by_sku = data.items
    grouped: dict[str, list[InventoryItem]] = defaultdict(list)
    for item in items:
        if item.suggested_order_qty > 0:
            grouped[by_sku[item.sku].supplier_id].append(item)

    out = []
    for supplier_id, supplier_items in sorted(grouped.items()):
        lines = [
            DraftPOLine(
                sku=item.sku,
                qty=item.suggested_order_qty,
                unit_cost=item.unit_cost,
                line_total=Money(
                    minor=item.suggested_order_qty * item.unit_cost.minor,
                    currency=data.currency,
                ),
            )
            for item in sorted(supplier_items, key=lambda item: item.sku)
        ]
        expected_on = as_of + timedelta(
            days=max(by_sku[item.sku].lead_time_days for item in supplier_items)
        )
        out.append(
            DraftPurchaseOrder(
                draft_id=stable_id("dpo", data.tenant_id, supplier_id, as_of.isoformat()),
                supplier_id=supplier_id,
                order_by=as_of,
                expected_on=expected_on,
                lines=lines,
                total=Money(
                    minor=sum(line.line_total.minor for line in lines), currency=data.currency
                ),
                reason_code="at_or_below_reorder_point",
                refs=[line.sku for line in lines],
            )
        )
    return out


def _bundles(sales: list[SaleLine]) -> tuple[list[BundleCandidate], InsufficientData | None]:
    receipts: dict[str, set[str]] = defaultdict(set)
    for sale in sales:
        if sale.qty > 0:
            receipts[sale.receipt_no].add(sale.sku)
    baskets = [skus for skus in receipts.values() if skus]
    if not baskets:
        return [], InsufficientData(
            need="Receipt-level sale lines",
            why="Bundle lift needs baskets with at least one positive sale line.",
            blocking=False,
            metric_ids=["inventory.bundle_lift"],
        )

    sku_baskets: Counter[str] = Counter()
    pair_baskets: Counter[tuple[str, str]] = Counter()
    for skus in baskets:
        for sku in skus:
            sku_baskets[sku] += 1
        for pair in combinations(sorted(skus), 2):
            pair_baskets[pair] += 1
    total = len(baskets)
    candidates = []
    for (left, right), together in pair_baskets.items():
        if together <= 0:
            continue
        lift = Decimal(together * total) / Decimal(sku_baskets[left] * sku_baskets[right])
        candidates.append(
            BundleCandidate(
                skus=[left, right],
                baskets_together=together,
                lift_bp=to_bp(lift),
                reason_code="bought_together",
            )
        )
    candidates.sort(key=lambda item: (-item.lift_bp, -item.baskets_together, item.skus))
    return candidates[:5], None


def _findings(
    items: list[InventoryItem],
    run_id: str,
    window: Period,
    generated_at: datetime,
    currency: str,
) -> list[Finding]:
    candidates = [
        item for item in items if item.movement in {"slow", "dead"} and item.cash_tied_up.minor > 0
    ]
    candidates.sort(key=lambda item: (-item.cash_tied_up.minor, item.sku))
    out = []
    for item in candidates:
        label = (
            "Dead stock at cost" if item.movement == "dead" else "Slow stock above 60 days' cover"
        )
        metric_id = (
            "inventory.dead_stock_value"
            if item.movement == "dead"
            else "inventory.slow_stock_value"
        )
        out.append(
            Finding(
                id=stable_id("fnd", item.movement, item.sku, run_id),
                source="inventory",
                severity="medium",
                title=f"Rs {item.cash_tied_up.minor // 100:,} is tied up in {item.sku} ({item.movement} stock)",
                money_at_stake=item.cash_tied_up,
                evidence=[
                    Evidence(kind="inventory_run", ref=run_id),
                    Evidence(kind="item", ref=item.sku),
                ],
                actions=[
                    Action(label="Open inventory", route=f"/inventory?filter={item.movement}")
                ],
                type=f"{item.movement}_stock",
                period=window,
                created_at=generated_at,
                dedupe_key=f"{item.movement}_stock:{item.sku}",
                figures=[money_figure(metric_id, label, item.cash_tied_up.minor, currency)],
            )
        )
    return out


def _style_code(sku: str) -> str:
    return sku.split("-", 1)[0]


def _round_int(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
