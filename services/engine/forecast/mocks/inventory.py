"""Mock inventory analysis: planted slow and dead stock, a winter stockout risk, draft POs."""

from __future__ import annotations

from datetime import timedelta

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
    bp_figure,
    bp_threshold,
    money_figure,
    stable_id,
    to_bp,
    value_figure,
)
from engine.forecast.inventory.schemas import (
    BundleCandidate,
    DraftPOLine,
    DraftPurchaseOrder,
    InventoryAnalysisResponse,
    InventoryItem,
    SizeShare,
    StyleRollup,
)
from engine.forecast.mocks import AS_OF, CURRENCY, GENERATED_AT, envelope

WINDOW_DAYS = 90
# sku, name, category, style, size, colour, season, on_hand, cost (Rs), price (Rs),
# units sold in window, last sold (days ago), lead days, supplier, xyz, cv
ROWS = [
    (
        "KRT-M-BLU",
        "Cotton kurta - M - Blue",
        "kurta",
        "KRT",
        "M",
        "BLU",
        "all",
        40,
        1800,
        3000,
        210,
        0,
        7,
        "sup_017",
        "X",
        0.31,
    ),
    (
        "KRT-L-BLU",
        "Cotton kurta - L - Blue",
        "kurta",
        "KRT",
        "L",
        "BLU",
        "all",
        34,
        1800,
        3000,
        165,
        1,
        7,
        "sup_017",
        "X",
        0.36,
    ),
    (
        "KRT-M-WHT",
        "Cotton kurta - M - White",
        "kurta",
        "KRT",
        "M",
        "WHT",
        "all",
        52,
        1800,
        3000,
        240,
        0,
        7,
        "sup_017",
        "X",
        0.28,
    ),
    (
        "KRT-XL-ORG",
        "Cotton kurta - XL - Orange",
        "kurta",
        "KRT",
        "XL",
        "ORG",
        "all",
        46,
        1800,
        3000,
        0,
        131,
        7,
        "sup_017",
        None,
        None,
    ),
    (
        "LWN-M-PNK",
        "Printed lawn suit - M - Pink",
        "lawn",
        "LWN",
        "M",
        "PNK",
        "summer",
        120,
        2600,
        4500,
        9,
        38,
        21,
        "sup_022",
        "Z",
        1.42,
    ),
    (
        "LWN-L-PNK",
        "Printed lawn suit - L - Pink",
        "lawn",
        "LWN",
        "L",
        "PNK",
        "summer",
        95,
        2600,
        4500,
        6,
        44,
        21,
        "sup_022",
        "Z",
        1.55,
    ),
    (
        "SHL-WOL-GRY",
        "Wool shawl - Grey",
        "shawl",
        "SHL",
        None,
        "GRY",
        "winter",
        25,
        1900,
        3500,
        48,
        2,
        45,
        "sup_031",
        "Y",
        0.74,
    ),
    (
        "SHL-WOL-BRN",
        "Wool shawl - Brown",
        "shawl",
        "SHL",
        None,
        "BRN",
        "winter",
        18,
        1900,
        3500,
        41,
        3,
        45,
        "sup_031",
        "Y",
        0.81,
    ),
    (
        "SWT-M-NVY",
        "Knit sweater - M - Navy",
        "sweater",
        "SWT",
        "M",
        "NVY",
        "winter",
        30,
        2200,
        3900,
        27,
        5,
        30,
        "sup_031",
        "Y",
        0.66,
    ),
    (
        "DUP-CHF-BLK",
        "Chiffon dupatta - Black",
        "dupatta",
        "DUP",
        None,
        "BLK",
        "all",
        60,
        650,
        1200,
        150,
        0,
        14,
        "sup_017",
        "X",
        0.40,
    ),
]


def _m(rupees: float) -> Money:
    return Money(minor=round(rupees * 100), currency=CURRENCY)


def build() -> InventoryAnalysisResponse:
    run_id = stable_id("inv", "mock", AS_OF.isoformat())
    window = Period(start=AS_OF - timedelta(days=WINDOW_DAYS - 1), end=AS_OF)
    revenue = {r[0]: r[10] * r[9] for r in ROWS}
    ranked = sorted(revenue, key=revenue.get, reverse=True)
    total = sum(revenue.values())
    abc, running = {}, 0.0
    for sku in ranked:
        share_before = running / total
        abc[sku] = "A" if share_before < 0.8 else "B" if share_before < 0.95 else "C"
        running += revenue[sku]

    items = []
    for (
        sku,
        name,
        cat,
        style,
        size,
        colour,
        season,
        on_hand,
        cost,
        price,
        sold,
        ago,
        lead,
        _sup,
        xyz,
        cv,
    ) in ROWS:
        daily = sold / WINDOW_DAYS
        cover = round(on_hand / daily) if daily > 0 else None
        movement = (
            "dead"
            if sold == 0 and ago >= 90
            else "slow"
            if cover is not None and cover > 180
            else "fast"
            if cover is not None and cover < 21
            else "normal"
        )
        stock_value = on_hand * cost
        safety = round(1.2816 * (cv or 0) * daily * 30 * (lead / 30) ** 0.5)
        rop = round(daily * lead) + safety
        suggested = (
            max(0, round(daily * (lead + 30)) + safety - on_hand) if season != "summer" else 0
        )
        target_units = daily * 60
        tied = (
            stock_value
            if movement == "dead"
            else max(0.0, (on_hand - target_units) * cost)
            if movement == "slow"
            else 0.0
        )
        margin = sold * (price - cost)
        avg_inv_cost = stock_value
        items.append(
            InventoryItem(
                sku=sku,
                name=name,
                category=cat,
                style=style,
                size=size,
                colour=colour,
                season=season,
                on_hand=on_hand,
                unit_cost=_m(cost),
                price=_m(price),
                stock_value=_m(stock_value),
                units_sold_window=sold,
                revenue_window=_m(sold * price),
                gross_margin_window=_m(margin),
                gross_margin_bp=to_bp((price - cost) / price) if sold else None,
                abc=abc[sku],
                xyz=xyz,
                demand_cv_bp=to_bp(cv) if cv is not None else None,
                movement=movement,
                days_of_cover=cover,
                last_sold_on=AS_OF - timedelta(days=ago) if sold or ago < 365 else None,
                lead_time_days=lead,
                safety_stock=safety,
                reorder_point=rop,
                suggested_order_qty=suggested,
                turnover_bp=to_bp(sold * cost * (365 / WINDOW_DAYS) / avg_inv_cost)
                if avg_inv_cost
                else None,
                gmroi_bp=to_bp(margin * (365 / WINDOW_DAYS) / avg_inv_cost)
                if avg_inv_cost
                else None,
                cash_tied_up=_m(tied),
                source_refs=["items.csv", f"events.jsonl#sale:{sku}"],
            )
        )

    by = {i.sku: i for i in items}
    dead_value = sum(i.cash_tied_up.minor for i in items if i.movement == "dead")
    slow_value = sum(i.cash_tied_up.minor for i in items if i.movement == "slow")
    stock_total = sum(i.stock_value.minor for i in items)

    kurta = [i for i in items if i.style == "KRT"]
    kurta_sold = sum(i.units_sold_window for i in kurta)
    sizes: dict[str, int] = {}
    for i in kurta:
        sizes[i.size] = sizes.get(i.size, 0) + i.units_sold_window
    styles = [
        StyleRollup(
            style="KRT",
            name="Cotton kurta",
            skus=[i.sku for i in kurta],
            on_hand=sum(i.on_hand for i in kurta),
            stock_value=Money(minor=sum(i.stock_value.minor for i in kurta), currency=CURRENCY),
            units_sold_window=kurta_sold,
            size_curve=[
                SizeShare(size=s, share_bp=to_bp(n / kurta_sold)) for s, n in sorted(sizes.items())
            ],
            strongest_sku="KRT-M-WHT",
            weakest_sku="KRT-XL-ORG",
        )
    ]

    shawl_lines = [
        DraftPOLine(sku=s, qty=q, unit_cost=_m(1900), line_total=_m(1900 * q))
        for s, q in (
            ("SHL-WOL-GRY", by["SHL-WOL-GRY"].suggested_order_qty),
            ("SHL-WOL-BRN", by["SHL-WOL-BRN"].suggested_order_qty),
        )
        if q > 0
    ]
    pos = [
        DraftPurchaseOrder(
            draft_id=stable_id("dpo", "mock", "sup_031"),
            supplier_id="sup_031",
            order_by=AS_OF + timedelta(days=1),
            expected_on=AS_OF + timedelta(days=46),
            lines=shawl_lines,
            total=Money(minor=sum(x.line_total.minor for x in shawl_lines), currency=CURRENCY),
            reason_code="below_reorder_point_before_peak_season",
            refs=["SHL-WOL-GRY", "SHL-WOL-BRN"],
        )
    ]

    findings = [
        Finding(
            id=stable_id("fnd", "dead_stock", AS_OF.isoformat()),
            source="inventory",
            severity="medium",
            title=f"Rs {dead_value // 100:,} is tied up in a kurta colour that hasn't sold for 131 days",
            money_at_stake=Money(minor=dead_value, currency=CURRENCY),
            evidence=[
                Evidence(kind="inventory_run", ref=run_id),
                Evidence(kind="item", ref="KRT-XL-ORG"),
            ],
            actions=[Action(label="Open inventory", route="/inventory?filter=dead")],
            type="dead_stock",
            period=window,
            created_at=GENERATED_AT,
            dedupe_key="dead_stock:KRT-XL-ORG",
            figures=[
                money_figure(
                    "inventory.dead_stock_value", "Dead stock at cost", dead_value, CURRENCY
                )
            ],
        ),
        Finding(
            id=stable_id("fnd", "slow_stock", AS_OF.isoformat()),
            source="inventory",
            severity="medium",
            title="Summer lawn suits cover more than a year of sales",
            money_at_stake=Money(minor=slow_value, currency=CURRENCY),
            evidence=[
                Evidence(kind="inventory_run", ref=run_id),
                Evidence(kind="item", ref="LWN-M-PNK"),
                Evidence(kind="item", ref="LWN-L-PNK"),
            ],
            actions=[Action(label="Open inventory", route="/inventory?filter=slow")],
            type="slow_stock",
            period=window,
            created_at=GENERATED_AT,
            dedupe_key="slow_stock:LWN",
            figures=[
                money_figure(
                    "inventory.slow_stock_value",
                    "Slow stock above 60 days' cover",
                    slow_value,
                    CURRENCY,
                )
            ],
        ),
        Finding(
            id=stable_id("fnd", "stockout_risk", AS_OF.isoformat()),
            source="inventory",
            severity="medium",
            title="Wool shawls will run out before the next delivery can arrive",
            money_at_stake=pos[0].total,
            evidence=[
                Evidence(kind="inventory_run", ref=run_id),
                Evidence(kind="draft_po", ref=pos[0].draft_id),
            ],
            actions=[Action(label="Review draft order", route="/inventory?tab=orders")],
            type="stockout_risk",
            created_at=GENERATED_AT,
            dedupe_key="stockout_risk:SHL",
        ),
    ]

    params = [
        bp_threshold("abc_a_cumulative_share", 0.80, Origin.DRAFT_DEFAULT, "<="),
        bp_threshold("abc_b_cumulative_share", 0.95, Origin.DRAFT_DEFAULT, "<="),
        bp_threshold("xyz_x_max_cv", 0.50, Origin.DRAFT_DEFAULT, "<="),
        bp_threshold("xyz_y_max_cv", 1.00, Origin.DRAFT_DEFAULT, "<="),
        Threshold(
            name="dead_after_days_without_sale",
            value=90,
            unit=Unit.DAYS,
            origin=Origin.DRAFT_DEFAULT,
            comparison=">=",
        ),
        Threshold(
            name="slow_above_days_of_cover",
            value=180,
            unit=Unit.DAYS,
            origin=Origin.DRAFT_DEFAULT,
            comparison=">",
        ),
        bp_threshold("service_level", 0.90, Origin.DRAFT_DEFAULT, ">="),
    ]
    summary = [
        money_figure("inventory.stock_value", "Stock at cost", stock_total, CURRENCY),
        money_figure("inventory.dead_stock_value", "Dead stock at cost", dead_value, CURRENCY),
        money_figure(
            "inventory.slow_stock_value", "Slow stock above 60 days' cover", slow_value, CURRENCY
        ),
        value_figure("inventory.sku_count", "SKUs", len(items), Unit.COUNT),
        bp_figure(
            "inventory.gmroi",
            "Gross margin return on inventory (annualised)",
            sum(i.gross_margin_window.minor for i in items) * (365 / WINDOW_DAYS) / stock_total,
        ),
    ]
    return InventoryAnalysisResponse(
        **envelope(),
        run_id=run_id,
        currency=CURRENCY,
        as_of=AS_OF,
        window=window,
        parameters=params,
        summary=summary,
        items=items,
        styles=styles,
        bundles=[
            BundleCandidate(
                skus=["DUP-CHF-BLK", "KRT-XL-ORG"],
                baskets_together=0,
                lift_bp=0,
                reason_code="pair_dead_stock_with_fast_mover",
            )
        ],
        draft_purchase_orders=pos,
        findings=findings,
    )
