from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from engine.app.main import create_app
from engine.forecast.inventory.engine import analyse_inventory
from engine.forecast.inventory.loader import (
    InventoryData,
    InventoryItemRecord,
    SaleLine,
    StockMovement,
    load_inventory_fixture,
)
from engine.forecast.inventory.schemas import InventoryAnalysisResponse

CURRENCY = "PKR"
AS_OF = date(2026, 10, 22)
GENERATED_AT = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)


def item(
    sku: str,
    *,
    opening: int,
    cost: int = 100,
    price: int = 200,
    supplier: str = "sup_1",
    lead: int = 7,
    launched_on: date = date(2025, 1, 1),
) -> InventoryItemRecord:
    return InventoryItemRecord(
        sku=sku,
        name=f"{sku} name",
        category=sku.split("-")[0],
        size="M",
        colour="BLK",
        season="all",
        unit_cost_minor=cost,
        price_minor=price,
        currency=CURRENCY,
        opening_stock_qty=opening,
        reorder_level=0,
        supplier_id=supplier,
        lead_time_days=lead,
        launched_on=launched_on,
    )


def sale(sku: str, day: date, qty: int, *, receipt: str | None = None) -> SaleLine:
    return SaleLine(
        event_id=f"evt_{sku}_{day.isoformat()}_{qty}",
        date=day,
        receipt_no=receipt or f"r_{sku}_{day.isoformat()}",
        sku=sku,
        qty=qty,
        price_minor=200,
        total_minor=qty * 200,
        cost_minor=100,
        source_ref=f"events.jsonl#{sku}",
    )


def data(items, sales, movements=None) -> InventoryData:
    return InventoryData(
        tenant_id="ten_test",
        currency=CURRENCY,
        as_of=AS_OF,
        items={record.sku: record for record in items},
        sales=sales,
        stock_movements=movements or [],
        purchase_orders=[],
        goods_received=[],
        source="test",
        source_hash="test_hash",
    )


def run(source: InventoryData):
    return analyse_inventory(source, as_of=source.as_of, generated_at=GENERATED_AT, mode="mock")


def by_sku(response):
    return {item.sku: item for item in response.items}


def test_steady_sales_are_fast_x_class_with_reorder_point():
    start = AS_OF - timedelta(days=89)
    steady_sales = [sale("KRT-M-BLK", start + timedelta(days=7 * week), 2) for week in range(13)]
    response = run(data([item("KRT-M-BLK", opening=2)], steady_sales))
    result = by_sku(response)["KRT-M-BLK"]

    assert result.movement == "fast"
    assert result.xyz == "X"
    assert result.reorder_point == 2
    assert result.suggested_order_qty > 0


def test_dead_stock_ties_up_full_stock_value():
    response = run(data([item("DEAD-M-BLK", opening=5)], []))
    result = by_sku(response)["DEAD-M-BLK"]

    assert result.movement == "dead"
    assert result.cash_tied_up.minor == 500


def test_zero_demand_has_no_days_of_cover_or_division_error():
    response = run(data([item("NEW-M-BLK", opening=5, launched_on=AS_OF - timedelta(days=10))], []))
    result = by_sku(response)["NEW-M-BLK"]

    assert result.days_of_cover is None
    assert result.turnover_bp is None
    assert result.movement == "new"


def test_refunds_reduce_units_sold():
    response = run(
        data(
            [item("REF-M-BLK", opening=10)],
            [sale("REF-M-BLK", AS_OF - timedelta(days=5), 5), sale("REF-M-BLK", AS_OF, -2)],
        )
    )

    assert by_sku(response)["REF-M-BLK"].units_sold_window == 3


def test_abc_classes_cover_all_revenue_basis():
    response = run(
        data(
            [
                item("AAA-M-BLK", opening=50),
                item("BBB-M-BLK", opening=50),
                item("CCC-M-BLK", opening=50),
            ],
            [
                sale("AAA-M-BLK", AS_OF, 10),
                sale("BBB-M-BLK", AS_OF, 5),
                sale("CCC-M-BLK", AS_OF, 1),
            ],
        )
    )

    revenue_by_class = {"A": 0, "B": 0, "C": 0}
    for result in response.items:
        revenue_by_class[result.abc] += result.revenue_window.minor
    assert sum(revenue_by_class.values()) == sum(
        item.revenue_window.minor for item in response.items
    )
    assert set(revenue_by_class) == {"A", "B", "C"}


def test_draft_purchase_orders_group_by_supplier_and_total_lines():
    source = data(
        [
            item("ONE-M-BLK", opening=0, supplier="sup_a"),
            item("TWO-M-BLK", opening=0, supplier="sup_a"),
            item("THR-M-BLK", opening=0, supplier="sup_b"),
        ],
        [sale("ONE-M-BLK", AS_OF - timedelta(days=7 * week), 7) for week in range(8)]
        + [sale("TWO-M-BLK", AS_OF - timedelta(days=7 * week), 7) for week in range(8)]
        + [sale("THR-M-BLK", AS_OF - timedelta(days=7 * week), 7) for week in range(8)],
    )
    response = run(source)

    by_supplier = {po.supplier_id: po for po in response.draft_purchase_orders}
    assert set(by_supplier) == {"sup_a", "sup_b"}
    assert len(by_supplier["sup_a"].lines) == 2
    assert all(
        po.total.minor == sum(line.line_total.minor for line in po.lines)
        for po in by_supplier.values()
    )


def test_real_seed_42_inventory_engine_runs_and_validates():
    source = load_inventory_fixture("ten_karachi_apparel")
    response = run(source)

    assert response.run_id.startswith("inv_")
    assert all(item.on_hand >= 0 for item in response.items)
    assert_money_is_int(response)
    InventoryAnalysisResponse.model_validate(response.model_dump())


def test_inventory_api_uses_real_engine_for_known_tenant(monkeypatch):
    monkeypatch.setenv("FIONA_MODE", "mock")
    client = TestClient(create_app(modules=["forecast"]))

    response = client.get(
        "/v1/inventory/analysis", headers={"X-Fiona-Tenant": "ten_karachi_apparel"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"].startswith("inv_")
    assert body["run_id"] != "inv_ZZ2HNCBRC2XGBRRKB7RTSTXNW2"
    assert body["items"]


def test_inventory_api_unknown_tenant_matches_cash_fallback(monkeypatch):
    monkeypatch.setenv("FIONA_MODE", "mock")
    client = TestClient(create_app(modules=["forecast"]))

    response = client.get("/v1/inventory/analysis", headers={"X-Fiona-Tenant": "ten_nobody"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@given(
    quantities=st.lists(st.integers(min_value=-5, max_value=12), min_size=0, max_size=20),
    opening=st.integers(min_value=0, max_value=100),
)
def test_property_units_sold_equal_sale_quantities_and_cash_tied_up_is_bounded(quantities, opening):
    source_item = item("PROP-M-BLK", opening=opening)
    source = data(
        [source_item],
        [
            sale("PROP-M-BLK", AS_OF - timedelta(days=index % 30), qty)
            for index, qty in enumerate(quantities)
        ],
    )

    result = by_sku(run(source))["PROP-M-BLK"]

    assert result.units_sold_window == sum(quantities)
    assert result.cash_tied_up.minor <= result.stock_value.minor


def test_negative_stock_is_clamped_with_insufficient_data_note():
    source = data(
        [item("NEG-M-BLK", opening=0)],
        [sale("NEG-M-BLK", AS_OF, 3)],
        [StockMovement(AS_OF, "NEG-M-BLK", 0, 100, "adjustment", "adj_1")],
    )

    response = run(source)

    assert by_sku(response)["NEG-M-BLK"].on_hand == 0
    assert response.insufficient_data


def assert_money_is_int(response: InventoryAnalysisResponse):
    for figure in response.summary:
        if figure.money is not None:
            assert isinstance(figure.money.minor, int)
    for item in response.items:
        assert isinstance(item.unit_cost.minor, int)
        assert isinstance(item.price.minor, int)
        assert isinstance(item.stock_value.minor, int)
        assert isinstance(item.revenue_window.minor, int)
        assert isinstance(item.gross_margin_window.minor, int)
        assert isinstance(item.cash_tied_up.minor, int)
    for po in response.draft_purchase_orders:
        assert isinstance(po.total.minor, int)
        for line in po.lines:
            assert isinstance(line.unit_cost.minor, int)
            assert isinstance(line.line_total.minor, int)
    for finding in response.findings:
        assert isinstance(finding.money_at_stake.minor, int)


def test_run_id_changes_with_input_hash():
    source = data([item("RID-M-BLK", opening=1)], [])
    changed = replace(source, source_hash="different")

    assert run(source).run_id != run(changed).run_id
