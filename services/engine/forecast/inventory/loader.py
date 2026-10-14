"""Fixture loader for the inventory analytics engine."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from engine.forecast.ledger_source import FIXTURES_ROOT, TenantDataMissing


@dataclass(frozen=True)
class InventoryItemRecord:
    sku: str
    name: str
    category: str
    size: str | None
    colour: str | None
    season: str
    unit_cost_minor: int
    price_minor: int
    currency: str
    opening_stock_qty: int
    reorder_level: int
    supplier_id: str
    lead_time_days: int
    launched_on: date


@dataclass(frozen=True)
class SaleLine:
    event_id: str
    date: date
    receipt_no: str
    sku: str
    qty: int
    price_minor: int
    total_minor: int
    cost_minor: int
    source_ref: str


@dataclass(frozen=True)
class StockMovement:
    date: date
    sku: str
    qty: int
    unit_cost_minor: int
    reason: str
    ref: str


@dataclass(frozen=True)
class PurchaseOrderLine:
    sku: str
    qty: int
    unit_cost_minor: int


@dataclass(frozen=True)
class PurchaseOrder:
    po_id: str
    supplier_id: str
    ordered_on: date
    expected_on: date
    status: str
    lines: tuple[PurchaseOrderLine, ...]


@dataclass(frozen=True)
class GoodsReceivedLine:
    sku: str
    qty_received: int


@dataclass(frozen=True)
class GoodsReceived:
    grn_id: str
    po_id: str
    supplier_id: str
    received_on: date
    lines: tuple[GoodsReceivedLine, ...]


@dataclass(frozen=True)
class InventoryData:
    tenant_id: str
    currency: str
    as_of: date
    items: dict[str, InventoryItemRecord]
    sales: list[SaleLine]
    stock_movements: list[StockMovement]
    purchase_orders: list[PurchaseOrder]
    goods_received: list[GoodsReceived]
    source: str
    source_hash: str
    notes: list[str] = field(default_factory=list)


def load_inventory_fixture(tenant_id: str, root: Path = FIXTURES_ROOT) -> InventoryData:
    folder = root / tenant_id
    if not (folder / "tenant.json").is_file():
        raise TenantDataMissing(tenant_id)

    tenant = _read_json(folder / "tenant.json")
    as_of = _d(tenant["as_of"])
    currency = tenant["currency"]

    items = _read_items(folder / "items.csv")
    purchase_orders = _read_purchase_orders(folder / "purchase_orders.json", as_of)
    goods_received = _read_goods_received(folder / "goods_received.json", as_of)
    sales, stock_movements = _read_events(folder / "events.jsonl", as_of)

    source_files = [
        "tenant.json",
        "items.csv",
        "events.jsonl",
        "purchase_orders.json",
        "goods_received.json",
    ]
    digest = hashlib.sha256()
    for name in source_files:
        path = folder / name
        digest.update(name.encode())
        digest.update(path.read_bytes())

    return InventoryData(
        tenant_id=tenant_id,
        currency=currency,
        as_of=as_of,
        items=items,
        sales=sales,
        stock_movements=stock_movements,
        purchase_orders=purchase_orders,
        goods_received=goods_received,
        source=f"fixtures:{folder.relative_to(root.parent.parent).as_posix()}",
        source_hash=digest.hexdigest(),
    )


def _read_items(path: Path) -> dict[str, InventoryItemRecord]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = csv.DictReader(fh)
        return {
            row["sku"]: InventoryItemRecord(
                sku=row["sku"],
                name=row["name"],
                category=row["category"],
                size=row["size"] or None,
                colour=row["colour"] or None,
                season=row["season"],
                unit_cost_minor=int(row["unit_cost_minor"]),
                price_minor=int(row["price_minor"]),
                currency=row["currency"],
                opening_stock_qty=int(row["opening_stock_qty"]),
                reorder_level=int(row["reorder_level"]),
                supplier_id=row["supplier_id"],
                lead_time_days=int(row["lead_time_days"]),
                launched_on=_d(row["launched_on"]),
            )
            for row in rows
        }


def _read_purchase_orders(path: Path, as_of: date) -> list[PurchaseOrder]:
    raw = _read_json(path)
    orders = []
    for po in raw.get("purchase_orders", []):
        ordered_on = _d(po["ordered_on"])
        if ordered_on > as_of:
            continue
        orders.append(
            PurchaseOrder(
                po_id=po["po_id"],
                supplier_id=po["supplier_id"],
                ordered_on=ordered_on,
                expected_on=_d(po["expected_on"]),
                status=po["status"],
                lines=tuple(
                    PurchaseOrderLine(
                        sku=line["sku"],
                        qty=int(line["qty"]),
                        unit_cost_minor=int(line["unit_cost_minor"]),
                    )
                    for line in po.get("lines", [])
                ),
            )
        )
    return orders


def _read_goods_received(path: Path, as_of: date) -> list[GoodsReceived]:
    raw = _read_json(path)
    receipts = []
    for grn in raw.get("goods_received", []):
        received_on = _d(grn["received_on"])
        if received_on > as_of:
            continue
        receipts.append(
            GoodsReceived(
                grn_id=grn["grn_id"],
                po_id=grn["po_id"],
                supplier_id=grn["supplier_id"],
                received_on=received_on,
                lines=tuple(
                    GoodsReceivedLine(
                        sku=line["sku"],
                        qty_received=int(line["qty_received"]),
                    )
                    for line in grn.get("lines", [])
                ),
            )
        )
    return receipts


def _read_events(path: Path, as_of: date) -> tuple[list[SaleLine], list[StockMovement]]:
    sales: list[SaleLine] = []
    movements: list[StockMovement] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            event = json.loads(raw)
            event_date = _d(event["date"])
            if event_date > as_of:
                continue
            if event["event"] == "sale":
                source = event.get("source") or {}
                source_ref = (
                    f"{source.get('file', 'events.jsonl')}#{source.get('key', event['id'])}"
                )
                for line in event.get("lines", []):
                    sales.append(
                        SaleLine(
                            event_id=event["id"],
                            date=event_date,
                            receipt_no=event["receipt_no"],
                            sku=line["item"],
                            qty=int(line["qty"]),
                            price_minor=int(line["price_minor"]),
                            total_minor=int(line["total_minor"]),
                            cost_minor=int(line["cost_minor"]),
                            source_ref=source_ref,
                        )
                    )
            elif event["event"] == "stock_movement":
                movements.append(
                    StockMovement(
                        date=event_date,
                        sku=event["item"],
                        qty=int(event["qty"]),
                        unit_cost_minor=int(event["unit_cost_minor"]),
                        reason=event["reason"],
                        ref=event["ref"],
                    )
                )
    return sales, movements


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _d(value: str) -> date:
    return date.fromisoformat(value)
