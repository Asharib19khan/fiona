"""Day-by-day simulation of one synthetic business (generator v1, D2).

The history starts at the fiscal-year start on or before `as_of - months`, so whole fiscal years
are available for cash-flow statements, and runs `holdout_days` past `as_of`. Everything after
`as_of` is withheld from the published fixtures and written only to the held-out folder for
backtests.

Stock, payables, receivables, taxes, the loan, the leases and the bank balance stay consistent,
so every bank line really is a settlement, a deposit, a payment or a known recurring item.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from data.generator import core, finance
from data.generator.render import render_bill, render_bill_pdf

GENERATOR_VERSION = "1.0.0"
WALLETS = ("jazzcash", "easypaisa")
NON_CASH = ("card", "bank_qr", "raast", "jazzcash", "easypaisa")
SETTLEMENT_NARRATION = {
    "card": "POS CARD SETTL MID {mid} BATCH {batch}",
    "bank_qr": "QR SETTL {branch} BATCH {batch}",
    "raast": "RAAST P2M SETTL {branch} BATCH {batch}",
    "jazzcash": "JAZZCASH MERCH SETTL BATCH {batch}",
    "easypaisa": "EASYPAISA MERCH SETTL BATCH {batch}",
}


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class BankTxn:
    posted_on: date
    narration: str
    reference: str
    amount_minor: int
    kind: str  # matched kind or unmatched category
    event_ids: list[str] = field(default_factory=list)
    party: str | None = None
    extra: dict = field(default_factory=dict)


class Simulation:
    def __init__(
        self, config: dict, seed: int, months: int, mandates: list[dict], scenarios: dict
    ) -> None:
        self.cfg, self.seed, self.mandates, self.scenarios = config, seed, mandates, scenarios
        t = config["tenant"]
        self.tenant_id, self.currency = t["id"], t["currency"]
        self.offset = t["utc_offset_hours"]
        self.gst_bp = config["country_pack_draft"]["gst_rate_bp"]
        self.as_of = date.fromisoformat(t["as_of"])
        earliest = core.add_months(self.as_of, -months)
        fy_month = t["fiscal_year_start_month"]
        start_year = earliest.year if earliest.month >= fy_month else earliest.year - 1
        self.start = date(start_year, fy_month, 1)
        self.end = self.as_of + timedelta(t["holdout_days"])
        self.country = t["country"]
        self.cal = core.Calendar(config["calendar"]["bank_holidays"])
        reserved_bills = {p["bill_id"] for p in config.get("plants", [])}
        reserved_docs = {p["document_id"] for p in config.get("plants", [])}
        demo = config.get("demo", {}).get("duplicate_bill", {})
        reserved_bills |= {demo.get("original_bill_id"), demo.get("resend_bill_id")} - {None}
        reserved_docs |= {demo.get("original_document_id"), demo.get("resend_document_id")} - {None}
        self.bill_ids = core.IdAllocator("bill", 1001, 4, reserved_bills)
        self.doc_ids = core.IdAllocator("doc", 1, 1, reserved_docs)
        self.po_ids = core.IdAllocator("po", 1001, 4)
        self.pay_ids = core.IdAllocator("pay", 1, 4)
        self.inv_ids = core.IdAllocator("inv", 1, 4)
        self.events: list[dict] = []
        self.bank: list[BankTxn] = []
        self.pos_rows: list[dict] = []
        self.z_rows: list[dict] = []
        self.pos: list[dict] = []
        self.grns: list[dict] = []
        self.bills: list[dict] = []
        self.documents: dict[str, bytes] = {}
        self.invoices: list[dict] = []
        self.never_pay: set[str] = set()
        self.output_tax: dict[int, int] = {}
        self.input_tax: dict[int, int] = {}
        self.tax_credit = 0
        self.demand_actual: dict[tuple[date, str], int] = {}
        self.nrv_allowance: dict[str, int] = {}
        self.nrv_events: list[str] = []
        self.nrv_records: list[dict] = []
        self.nrv_unit_shortfall: dict[str, int] = {}
        self.loan = finance.loan_schedule(config["loan"], self.cal)
        self.loan["currency"] = self.currency
        self._weights_cache: dict[date, tuple[dict[str, int], int]] = {}
        self._cost_cache: dict[tuple, int] = {}
        self._price_cache: dict[tuple, int] = {}
        self._growth_cache: dict[int, int] = {}
        self._build_parties()
        self._build_items()

    # ------------------------------------------------------------ setup
    def _digits(self, rng) -> str:
        return "".join(str(rng.randint(0, 9)) for _ in range(16))

    def _party(
        self,
        pid: str,
        kind: str,
        code: str,
        name: str,
        *,
        iban: str | None,
        tax_id: str | None,
        allow: bool,
        terms: int = 0,
        credit: int | None = None,
        phone: str | None = None,
        city: str = "Karachi",
    ) -> dict:
        return {
            "party_id": pid,
            "kind": kind,
            "code": code,
            "name": name,
            "tax_id": tax_id,
            "tax_id_type": "NTN" if tax_id else None,
            "bank_iban": iban,
            "bank_account_changed_at": None,
            "on_allow_list": allow,
            "payment_terms_days": terms,
            "credit_limit_minor": credit,
            "phone": phone,
            "city": city,
        }

    def scenario_given(self, scenario_id: str) -> dict:
        return (
            next(s for s in self.scenarios["scenarios"] if s["id"] == scenario_id).get("given")
            or {}
        )

    def _build_parties(self) -> None:
        rng = core.stream(self.seed, "parties")
        self.own_iban = core.iban(
            self.country, self.cfg["bank"]["iban_bank_code"], self._digits(rng)
        )
        self.parties: dict[str, dict] = {}
        self.supplier_cfg = {s["id"]: s for s in self.cfg["suppliers"]}
        for i, s in enumerate(self.cfg["suppliers"]):
            ntn = f"{rng.randint(1_000_000, 9_999_999)}-{rng.randint(0, 9)}"
            bank = "SYNB" if i % 2 == 0 else "SYND"
            self.parties[s["id"]] = self._party(
                s["id"],
                "supplier",
                "S-" + s["id"][4:],
                s["name"],
                iban=core.iban(self.country, bank, self._digits(rng)),
                tax_id=ntn,
                allow=s["allow_list"],
                terms=s["terms_days"],
                phone=f"+92-000-000-{s['id'][4:].zfill(4)}",
                city=s["city"],
            )
        for plant in self.cfg.get("plants", []):  # S-11: a malformed NTN on file
            if plant.get("scenario") == "S-11":
                self.parties[plant["supplier"]]["tax_id"] = self.scenario_given("S-11")["party"][
                    "tax_id"
                ]
        for n in range(1, self.cfg["pos"]["loyalty_customers"] + 1):
            self.parties[f"cus_{n:04d}"] = self._party(
                f"cus_{n:04d}",
                "customer",
                f"C-{n:04d}",
                f"Customer C-{n:04d}",
                iban=None,
                tax_id=None,
                allow=False,
            )
        for c in self.cfg["b2b"]["customers"]:
            self.parties[c["id"]] = self._party(
                c["id"],
                "customer",
                c["code"],
                c["name"],
                iban=core.iban(self.country, "SYNE", self._digits(rng)),
                tax_id=f"{rng.randint(1_000_000, 9_999_999)}-{rng.randint(0, 9)}",
                allow=False,
                terms=c["terms_days"],
                credit=c["credit_limit_minor"],
            )
        for o in self.cfg["others"]:
            self.parties[o["id"]] = self._party(
                o["id"],
                o["kind"],
                o["id"].upper().replace("_", "-"),
                o["name"],
                iban=core.iban(self.country, "SYNF", self._digits(rng)),
                tax_id=None,
                allow=True,
            )
        self.invoice_counter = {s["id"]: s["invoice_start"] for s in self.cfg["suppliers"]}
        self.invoice_year: dict[str, int | None] = {s["id"]: None for s in self.cfg["suppliers"]}

    def _build_items(self) -> None:
        size_weights = self.cfg["pos"]["size_weights"]
        self.items: dict[str, dict] = {}
        self.base_weight: dict[str, int] = {}
        self.category_cfg = {c["code"]: c for c in self.cfg["categories"]}
        for cat in self.cfg["categories"]:
            variants = [(s, c) for s in cat["sizes"] for c in cat["colours"]]
            total_size = sum(size_weights[s] for s, _ in variants)
            for size, colour in variants:
                sku = f"{cat['code']}-{size}-{colour}"
                supplier = cat["suppliers"][cat["colours"].index(colour) % len(cat["suppliers"])]
                self.items[sku] = {
                    "sku": sku,
                    "name": f"{cat['name']} - {size} - {colour}",
                    "category": cat["code"],
                    "size": size,
                    "colour": colour,
                    "season": cat["season"],
                    "unit_cost_minor": cat["unit_cost_minor"],
                    "price_minor": cat["price_minor"],
                    "currency": self.currency,
                    "opening_stock_qty": 0,
                    "reorder_level": 0,
                    "supplier_id": supplier,
                    "lead_time_days": self.supplier_cfg[supplier]["lead_time_days"],
                    "launched_on": cat["launched_on"],
                }
                self.base_weight[sku] = 10_000 * size_weights[size] // total_size
        self.units_per_day_x100 = self._expected_units_x100()
        self.stock = dict.fromkeys(self.items, 0)
        self.on_order = dict.fromkeys(self.items, 0)
        self.layer_cost: dict[str, int] = {}
        purchasing = self.cfg["purchasing"]
        for sku, item in self.items.items():
            if self.category_cfg[item["category"]].get("reorder", True) is False:
                continue
            per_day = self._demand_x100(sku, self.start)
            item["opening_stock_qty"] = -(-per_day * purchasing["opening_cover_days"] // 100)
            item["reorder_level"] = -(
                -per_day * (item["lead_time_days"] + purchasing["reorder_days"]) // 100
            )
            self.stock[sku] = item["opening_stock_qty"]
            self.layer_cost[sku] = self.cost_at(sku, self.start)

    def _expected_units_x100(self) -> int:
        pos = self.cfg["pos"]
        receipts = sum(b["daily_receipts"] for b in self.cfg["branches"])
        lines_x100 = (
            sum((i + 1) * w for i, w in enumerate(pos["lines_weights"]))
            * 100
            // sum(pos["lines_weights"])
        )
        qty_x100 = (
            sum((i + 1) * w for i, w in enumerate(pos["qty_weights"]))
            * 100
            // sum(pos["qty_weights"])
        )
        return receipts * lines_x100 * qty_x100 // 100

    # ------------------------------------------------------------ prices, costs, demand
    def cost_at(self, sku: str, day: date) -> int:
        key = (sku, core.month_index(day))
        if key not in self._cost_cache:
            self._cost_cache[key] = self._cost_at(sku, day)
        return self._cost_cache[key]

    def _cost_at(self, sku: str, day: date) -> int:
        steps = core.month_index(day) - core.month_index(self.as_of)
        factor = core.compound_ppm(steps, self.cfg["inflation"]["purchase_cost_ppm_per_month"])
        return core.div_half_up(self.items[sku]["unit_cost_minor"] * factor, 1_000_000 * 100) * 100

    def price_at(self, sku: str, day: date) -> int:
        key = (sku, core.month_index(day), day < self.as_of)
        if key not in self._price_cache:
            self._price_cache[key] = self._price_at(sku, day)
        return self._price_cache[key]

    def _price_at(self, sku: str, day: date) -> int:
        months = self.cfg["inflation"]["retail_price_step_months"]
        lo, hi = min(day, self.as_of), max(day, self.as_of)
        steps, cursor = 0, date(lo.year, lo.month, 1)
        while cursor <= hi:
            if cursor.month in months and lo < cursor <= hi:
                steps += 1
            cursor = core.add_months(cursor, 1)
        price, pct = self.items[sku]["price_minor"], self.cfg["inflation"]["retail_price_step_pct"]
        for _ in range(steps):
            price = price * 100 // (100 + pct) if day < self.as_of else price * (100 + pct) // 100
        return core.div_half_up(price, 5_000) * 5_000  # whole PKR 50

    def traffic_pct(self, day: date) -> int:
        pct = 100
        for season in self.cfg["calendar"]["seasons"]:
            if season["start"] <= day.isoformat() <= season["end"] and "categories" not in season:
                pct = pct * season["traffic_pct"] // 100
        return pct

    def growth_ppm(self, day: date) -> int:
        month = core.month_index(day)
        if month not in self._growth_cache:
            self._growth_cache[month] = self._growth_ppm(day)
        return self._growth_cache[month]

    def _growth_ppm(self, day: date) -> int:
        steps = core.month_index(day) - core.month_index(self.as_of)
        # (1 + yearly growth)^(1/12) - 1, kept as an integer ppm in the persona-independent table
        monthly_ppm = {14: 10_978, 10: 7_974, 0: 0}[
            self.cfg["calendar"]["traffic_growth_pct_per_year"]
        ]
        return core.compound_ppm(steps, monthly_ppm)

    def _weights(self, day: date) -> tuple[dict[str, int], int]:
        if day not in self._weights_cache:
            weights, iso_day = {}, day.isoformat()
            winter = self.cfg["pos"]["winter_month_pct"][day.month - 1]
            for sku, item in self.items.items():
                cat = self.category_cfg[item["category"]]
                weight = cat["weight"]
                if cat.get("windows"):
                    weight = next(
                        (w["weight"] for w in cat["windows"] if w["start"] <= iso_day <= w["end"]),
                        0,
                    )
                w = weight * self.base_weight[sku]
                if item["season"] == "winter":
                    w = w * winter // 100
                for season in self.cfg["calendar"]["seasons"]:
                    if season["start"] <= iso_day <= season["end"] and item[
                        "category"
                    ] in season.get("categories", []):
                        w = w * season["mix_pct"] // 100
                weights[sku] = w
            self._weights_cache[day] = (weights, sum(weights.values()))
        return self._weights_cache[day]

    def _demand_x100(self, sku: str, day: date) -> int:
        weights, total = self._weights(day)
        units = (
            self.units_per_day_x100
            * self.traffic_pct(day)
            // 100
            * self.growth_ppm(day)
            // 1_000_000
        )
        return units * weights[sku] // total if total else 0

    def _window_discount_bp(self, sku: str, day: date) -> int:
        for window in self.category_cfg[self.items[sku]["category"]].get("windows", []):
            if window["start"] <= day.isoformat() <= window["end"]:
                return window.get("discount_bp", 0)
        return 0

    # ------------------------------------------------------------ events and taxes
    def _event(
        self,
        kind: str,
        occurred_at: datetime,
        business_date: date,
        source_type: str,
        key: str,
        fields: dict,
        source_extra: dict | None = None,
    ) -> dict:
        event_id = core.source_ulid("evt", occurred_at, self.tenant_id, source_type, key)
        event = {
            "id": event_id,
            "tenant_id": self.tenant_id,
            "event": kind,
            "occurred_at": core.iso(occurred_at),
            "date": business_date.isoformat(),
            "currency": self.currency,
        }
        event.update(fields)
        event["source"] = {"type": source_type, **(source_extra or {}), "key": key}
        self.events.append(event)
        return event

    def _add_tax(self, ledger: dict[int, int], day: date, amount: int) -> None:
        month = core.month_index(day)
        ledger[month] = ledger.get(month, 0) + amount

    def _local_date(self, moment: datetime) -> date:
        return (moment + timedelta(hours=self.offset)).date()

    # ------------------------------------------------------------ purchasing
    def _supplier_number(self, supplier_id: str, rng, day: date) -> str:
        cfg = self.supplier_cfg[supplier_id]
        if cfg.get("invoice_yearly_reset") and self.invoice_year[supplier_id] != day.year:
            self.invoice_year[supplier_id] = day.year
            self.invoice_counter[supplier_id] = cfg["invoice_start"]
        number = self.invoice_counter[supplier_id]
        self.invoice_counter[supplier_id] += (
            1 if cfg.get("invoice_yearly_reset") else rng.randint(2, 6)
        )
        return cfg["invoice_format"].format(n=number, yy=f"{day.year % 100:02d}", yyyy=day.year)

    def _create_po(
        self,
        day: date,
        supplier_id: str,
        lines: list[dict],
        *,
        expected: date | None = None,
        plant: dict | None = None,
    ) -> dict:
        po_id = self.po_ids.take()
        lead = self.supplier_cfg[supplier_id]["lead_time_days"]
        po = {
            "po_id": po_id,
            "number": "PO-" + po_id[3:],
            "supplier_id": supplier_id,
            "ordered_on": day.isoformat(),
            "expected_on": (expected or day + timedelta(lead)).isoformat(),
            "status": "open",
            "currency": self.currency,
            "lines": lines,
            "total_minor": sum(ln["qty"] * ln["unit_cost_minor"] for ln in lines),
            "_plant": plant,
        }
        for line in lines:
            if line.get("sku"):
                self.on_order[line["sku"]] += line["qty"]
        self.pos.append(po)
        return po

    def _stock_lines(self, skus: list[str], qty: int, day: date) -> list[dict]:
        return [
            {
                "sku": s,
                "description": self.items[s]["name"],
                "qty": qty,
                "unit_cost_minor": self.cost_at(s, day),
            }
            for s in skus
        ]

    def _plant_lines(self, plant: dict, day: date) -> list[dict]:
        if "lines" in plant:
            return [
                {
                    "sku": ln.get("sku"),
                    "description": ln.get("description") or self.items[ln["sku"]]["name"],
                    "qty": ln["qty"],
                    "unit_cost_minor": ln["unit_price_minor"],
                }
                for ln in plant["lines"]
            ]
        if "category" in plant:
            skus = sorted(s for s, it in self.items.items() if it["category"] == plant["category"])
            return self._stock_lines(skus, plant["qty_per_sku"], day)
        if "sku" in plant:
            unit, sku, description = (
                self.cost_at(plant["sku"], day),
                plant["sku"],
                self.items[plant["sku"]]["name"],
            )
        else:
            unit, sku, description = plant["unit_price_minor"], None, plant["description"]
        lines = core.lines_for_total(
            plant["target_total_minor"], self.gst_bp, unit, sku=sku, description=description
        )
        return [
            {
                "sku": ln["sku"],
                "description": ln["description"],
                "qty": ln["qty"],
                "unit_cost_minor": ln["unit_price_minor"],
            }
            for ln in lines
        ]

    def _order_day(self, day: date, rng) -> None:
        iso_day = day.isoformat()
        planted_suppliers: set[str] = set()
        demo = self.cfg.get("demo", {}).get("duplicate_bill")
        if demo and demo["ordered_on"] == iso_day:
            lines = [
                {
                    "sku": ln.get("sku"),
                    "description": ln.get("description") or self.items[ln["sku"]]["name"],
                    "qty": ln["qty"],
                    "unit_cost_minor": ln["unit_price_minor"],
                }
                for ln in demo["lines"]
            ]
            self._create_po(
                day,
                demo["supplier"],
                lines,
                expected=date.fromisoformat(demo["received_on"]),
                plant={"demo": True, **demo},
            )
            planted_suppliers.add(demo["supplier"])
        for plant in self.cfg.get("plants", []):
            if plant.get("ordered_on") == iso_day:
                self._create_po(
                    day,
                    plant["supplier"],
                    self._plant_lines(plant, day),
                    expected=date.fromisoformat(plant["received_on"]),
                    plant=plant,
                )
                planted_suppliers.add(plant["supplier"])
        for build in self.cfg.get("stock_builds", []):
            if build["ordered_on"] == iso_day:
                skus = sorted(
                    s for s, it in self.items.items() if it["category"] == build["category"]
                )
                expected = (
                    date.fromisoformat(build["received_on"]) if "received_on" in build else None
                )
                self._create_po(
                    day,
                    build["supplier"],
                    self._stock_lines(skus, build["qty_per_sku"], day),
                    expected=expected,
                    plant={"stock_build": True, **build},
                )
        self._packaging_orders(day, rng)
        if day.weekday() not in self.cfg["purchasing"]["order_weekdays"]:
            return
        purchasing = self.cfg["purchasing"]
        by_supplier: dict[str, list[str]] = {}
        for sku, item in self.items.items():
            if self.category_cfg[item["category"]].get("reorder", True):
                by_supplier.setdefault(item["supplier_id"], []).append(sku)
        for supplier_id in sorted(by_supplier):
            if supplier_id in planted_suppliers:
                continue
            lines = []
            for sku in sorted(by_supplier[supplier_id]):
                item = self.items[sku]
                per_day = self._demand_x100(sku, day + timedelta(item["lead_time_days"]))
                projected = self.stock[sku] + self.on_order[sku]
                if projected * 100 > per_day * (
                    item["lead_time_days"] + purchasing["reorder_days"]
                ):
                    continue
                target = -(-per_day * (item["lead_time_days"] + purchasing["cover_days"]) // 100)
                qty = -(-(target - projected) // purchasing["pack_size"]) * purchasing["pack_size"]
                if qty > 0:
                    lines += self._stock_lines([sku], qty, day)
            if lines:
                self._create_po(day, supplier_id, lines)

    def _packaging_orders(self, day: date, rng) -> None:
        if day != self.cal.nth_business_day(day.year, day.month, 1):
            return
        for supplier_id, months, unit, description in (
            ("sup_010", range(1, 13), 50_000, "Printed shopping bags and boxes"),
            ("sup_011", (1, 4, 7, 10), 2_400_000, "Wooden hangers, branded (box of 100)"),
        ):
            if day.month not in months:
                continue
            if any(
                p.get("supplier") == supplier_id
                and p.get("ordered_on", "")[:7] == day.isoformat()[:7]
                for p in self.cfg.get("plants", [])
            ):
                continue  # the planted bills replace this month's routine order
            low, high = self.supplier_cfg[supplier_id].get(
                "packaging_monthly_range_minor", [4_800_000, 7_200_000]
            )
            qty = max(1, rng.randint(low, high) // unit)
            self._create_po(
                day,
                supplier_id,
                [{"sku": None, "description": description, "qty": qty, "unit_cost_minor": unit}],
            )

    def _receive_goods(self, day: date, rng) -> None:
        for po in self.pos:
            if po["expected_on"] != day.isoformat() or po["status"] != "open":
                continue
            plant = po["_plant"] or {}
            grn_id = "grn_" + po["po_id"][3:]
            qty_override = plant.get("grn_qty", {})
            lines = [
                {
                    "sku": ln["sku"],
                    "description": ln["description"],
                    "qty_received": qty_override.get(ln["sku"], ln["qty"]),
                }
                for ln in po["lines"]
            ]
            self.grns.append(
                {
                    "grn_id": grn_id,
                    "po_id": po["po_id"],
                    "supplier_id": po["supplier_id"],
                    "received_on": day.isoformat(),
                    "lines": lines,
                }
            )
            po["status"] = "partially_received" if qty_override else "received"
            moment = core.local_time(day, 11 * 60, 0, self.offset)
            for ln, po_line in zip(lines, po["lines"], strict=True):
                if not ln["sku"]:
                    continue
                received, cost = ln["qty_received"], po_line["unit_cost_minor"]
                old_qty = self.stock[ln["sku"]]
                old_cost = self.layer_cost.get(ln["sku"], cost)
                self.layer_cost[ln["sku"]] = (old_qty * old_cost + received * cost) // max(
                    old_qty + received, 1
                )
                self.stock[ln["sku"]] += received
                self.on_order[ln["sku"]] -= po_line["qty"]
                self._event(
                    "stock_movement",
                    moment,
                    day,
                    "manual",
                    f"{grn_id}#{ln['sku']}",
                    {
                        "item": ln["sku"],
                        "qty": received,
                        "unit_cost_minor": cost,
                        "reason": "goods_received",
                        "ref": grn_id,
                    },
                )
            if plant.get("demo"):
                self._bill(
                    po,
                    date.fromisoformat(plant["original_issue_date"]),
                    plant["original_number"],
                    bill_id=plant["original_bill_id"],
                    doc_id=plant["original_document_id"],
                    due=date.fromisoformat(plant["original_due_date"]),
                    pdf=True,
                )
            elif plant.get("stock_build"):
                terms = plant.get("terms_days", self.supplier_cfg[po["supplier_id"]]["terms_days"])
                self._bill(
                    po,
                    day,
                    self._supplier_number(po["supplier_id"], rng, day),
                    due=day + timedelta(terms),
                )
            elif plant.get("bill_id"):
                number = plant.get("number") or self._supplier_number(po["supplier_id"], rng, day)
                due = date.fromisoformat(plant["due_date"]) if "due_date" in plant else None
                bill = self._bill(
                    po,
                    day,
                    number,
                    bill_id=plant["bill_id"],
                    doc_id=plant["document_id"],
                    due=due,
                    notes=plant.get("notes", ""),
                    stated_tax=plant.get("stated_tax_minor"),
                    entry=plant.get("entry", "extraction"),
                    entered_by=plant.get("entered_by"),
                    pdf=plant.get("pdf", False),
                )
                if "stated_tax_minor" in plant:
                    self.never_pay.add(
                        bill["bill_id"]
                    )  # S-07: a wrong bill is never paid as stated
            else:
                self._bill(po, day, self._supplier_number(po["supplier_id"], rng, day))

    def _bill(
        self,
        po: dict | None,
        issue: date,
        number: str,
        *,
        supplier_id: str | None = None,
        lines: list[dict] | None = None,
        bill_id: str | None = None,
        doc_id: str | None = None,
        due: date | None = None,
        received_at: datetime | None = None,
        iban: str | None = None,
        notes: str = "",
        stated_tax: int | None = None,
        entry: str = "extraction",
        entered_by: str | None = None,
        category: str = "inventory_supplier",
        contract_ref: str | None = None,
        taxable: bool = True,
        pdf: bool = False,
        document: bytes | None = None,
    ) -> dict:
        supplier_id = supplier_id or po["supplier_id"]
        supplier = self.parties[supplier_id]
        terms = (
            self.supplier_cfg[supplier_id]["terms_days"] if supplier_id in self.supplier_cfg else 0
        )
        if lines is None:
            lines = [
                {
                    "sku": ln["sku"],
                    "description": ln["description"],
                    "qty": ln["qty"],
                    "unit_price_minor": ln["unit_cost_minor"],
                    "line_total_minor": ln["qty"] * ln["unit_cost_minor"],
                }
                for ln in po["lines"]
            ]
        subtotal = sum(ln["line_total_minor"] for ln in lines)
        stated = (
            stated_tax
            if stated_tax is not None
            else (core.tax_on(subtotal, self.gst_bp) if taxable else 0)
        )
        received = received_at or core.local_time(
            issue + timedelta(1), 10 * 60 + 10, 0, self.offset
        )
        bill = {
            "bill_id": bill_id or self.bill_ids.take(),
            "document_id": doc_id or self.doc_ids.take(),
            "document_sha256": "",
            "document_path": "",
            "received_at": core.iso(received),
            "supplier_id": supplier_id,
            "supplier": {
                "name": supplier["name"],
                "tax_id": supplier["tax_id"],
                "bank_iban": iban or supplier["bank_iban"],
            },
            "number": number,
            "issue_date": issue.isoformat(),
            "due_date": (due or issue + timedelta(terms)).isoformat(),
            "po_number": po["number"] if po else None,
            "contract_ref": contract_ref,
            "category": category,
            "currency": self.currency,
            "lines": lines,
            "subtotal_minor": subtotal,
            "tax": [{"code": "GST", "rate_bp": self.gst_bp, "amount_minor": stated}]
            if taxable
            else [],
            "total_minor": subtotal + stated,
            "notes": notes,
            "entry": entry,
            "entered_by": entered_by or "svc_extraction",
            "extraction": {"method": "synthetic_ground_truth"},
        }
        if document is None:
            render = render_bill_pdf if pdf else render_bill
            document = render(bill, supplier, self.cfg["tenant"]["name"])
        bill["document_path"] = f"documents/{bill['document_id']}.{'pdf' if pdf else 'txt'}"
        bill["document_sha256"] = hashlib.sha256(document).hexdigest()
        self.documents[bill["document_path"]] = document
        self.bills.append(bill)
        self._add_tax(self.input_tax, issue, stated)
        actor = {
            "kind": "user" if bill["entered_by"].startswith("usr_") else "system",
            "id": bill["entered_by"],
        }
        self._event(
            "purchase_bill",
            received,
            self._local_date(received),
            "bill_extraction",
            bill["bill_id"],
            {
                "party": supplier_id,
                "bill_id": bill["bill_id"],
                "number": number,
                "issue_date": bill["issue_date"],
                "due_date": bill["due_date"],
                "po_number": bill["po_number"],
                "lines": lines,
                "subtotal_minor": subtotal,
                "tax_minor": stated,
                "total_minor": bill["total_minor"],
                "document_id": bill["document_id"],
                "document_sha256": bill["document_sha256"],
                "created_by": actor,
            },
            {"file": "bills.json"},
        )
        return bill

    def _bill_by_id(self, bill_id: str) -> dict:
        return next(b for b in self.bills if b["bill_id"] == bill_id)

    def _planted_followups(self, day: date) -> None:
        """Bank changes, the DEMO-1 resend and the S-05 / S-05b duplicates, each on its own date."""
        iso_day = day.isoformat()
        for change in self.cfg.get("bank_changes", []):
            if change["changed_at"][:10] != iso_day:
                continue
            party = self.parties[change["supplier"]]
            rng = core.stream(self.seed, f"bank-change:{change['supplier']}")
            new_iban = core.iban(self.country, change["new_bank_code"], self._digits(rng))
            self._event(
                "bank_detail_change",
                _ts(change["changed_at"]),
                day,
                "manual",
                f"bdc:{party['party_id']}:{iso_day}",
                {
                    "party": party["party_id"],
                    "old_iban": party["bank_iban"],
                    "new_iban": new_iban,
                    "confirmed_via": change["confirmed_via"],
                    "confirmed_by": change["confirmed_by"],
                },
            )
            party["bank_iban"], party["bank_account_changed_at"] = new_iban, change["changed_at"]
        demo = self.cfg.get("demo", {}).get("duplicate_bill")
        if demo and demo["resend_received_at"][:10] == iso_day:
            original = self._bill_by_id(demo["original_bill_id"])
            po = next(p for p in self.pos if p["number"] == original["po_number"])
            bill = self._bill(
                po,
                date.fromisoformat(demo["resend_issue_date"]),
                demo["resend_number"],
                bill_id=demo["resend_bill_id"],
                doc_id=demo["resend_document_id"],
                due=date.fromisoformat(demo["resend_due_date"]),
                received_at=_ts(demo["resend_received_at"]),
                iban=self.parties[demo["supplier"]]["bank_iban"],
                notes=demo["resend_notes"],
                pdf=True,
            )
            self.never_pay.add(bill["bill_id"])
        for plant in self.cfg.get("plants", []):
            if plant.get("role") != "duplicate" or plant["received_at"][:10] != iso_day:
                continue
            source = self._bill_by_id(plant.get("same_file_as") or plant["resend_of"])
            po = next((p for p in self.pos if p["number"] == source["po_number"]), None)
            if (
                "same_file_as" in plant
            ):  # S-05: the identical file arrives again through email intake
                bill = self._bill(
                    po,
                    date.fromisoformat(source["issue_date"]),
                    source["number"],
                    supplier_id=source["supplier_id"],
                    lines=source["lines"],
                    bill_id=plant["bill_id"],
                    doc_id=plant["document_id"],
                    due=date.fromisoformat(source["due_date"]),
                    received_at=_ts(plant["received_at"]),
                    entry=plant["entry"],
                    document=self.documents[source["document_path"]],
                    pdf=source["document_path"].endswith(".pdf"),
                )
            else:  # S-05b: re-sent with a reformatted number and a small extra line
                lines = [dict(ln) for ln in source["lines"]]
                extra = (
                    core.subtotal_for_total(plant["target_total_minor"], self.gst_bp)
                    - source["subtotal_minor"]
                )
                lines.append(
                    {
                        "sku": None,
                        "description": "Freight surcharge",
                        "qty": 1,
                        "unit_price_minor": extra,
                        "line_total_minor": extra,
                    }
                )
                bill = self._bill(
                    po,
                    date.fromisoformat(plant["issue_date"]),
                    plant["number"],
                    supplier_id=source["supplier_id"],
                    lines=lines,
                    bill_id=plant["bill_id"],
                    doc_id=plant["document_id"],
                    received_at=_ts(plant["received_at"]),
                    pdf=plant.get("pdf", False),
                )
            self.never_pay.add(bill["bill_id"])

    def _rent_bill(self, day: date) -> None:
        lease = next((ls for ls in self.cfg["leases"] if ls.get("billed")), None)
        if lease is None or day != self.cal.nth_business_day(day.year, day.month, 1):
            return
        amount = lease["rent_by_year_minor"][str(day.year)]
        description = f"Shop rent, {lease['asset']}, {day.strftime('%B %Y')}"
        self._bill(
            None,
            day,
            f"RNT-{day.year}-{day.month:02d}",
            supplier_id=lease["lessor"],
            lines=[
                {
                    "sku": None,
                    "description": description,
                    "qty": 1,
                    "unit_price_minor": amount,
                    "line_total_minor": amount,
                }
            ],
            due=date(day.year, day.month, lease["payment_day"]),
            category="rent",
            contract_ref=lease["id"],
            taxable=False,
        )

    # ------------------------------------------------------------ NRV assessments (facts, not treatments)
    def _nrv_day(self, day: date) -> None:
        for assessment in self.cfg.get("nrv_assessments", []):
            if assessment["on"] != day.isoformat():
                continue
            details, needed = [], 0
            for sku in sorted(
                s for s, it in self.items.items() if it["category"] == assessment["category"]
            ):
                qty = self.stock[sku]
                cost = self.layer_cost.get(sku, self.cost_at(sku, day))
                price_ex_tax = self.price_at(sku, day) * 10_000 // (10_000 + self.gst_bp)
                esp = price_ex_tax * assessment["estimated_selling_price_pct"] // 100
                nrv = esp - esp * assessment["costs_to_sell_pct"] // 100
                gap = max(0, cost - nrv) * qty
                needed += gap
                details.append(
                    {
                        "item": sku,
                        "qty_on_hand": qty,
                        "unit_cost_minor": cost,
                        "estimated_selling_price_minor": esp,
                        "nrv_per_unit_minor": nrv,
                        "shortfall_minor": gap,
                    }
                )
            category = assessment["category"]
            previous = self.nrv_allowance.get(category, 0)
            # Allowance still attached to the units on hand; the rest was used up by units sold since.
            carried = sum(
                self.nrv_unit_shortfall.get(d["item"], 0) * d["qty_on_hand"] for d in details
            )
            consumed = previous - carried
            change = (
                needed - carried
            )  # > 0 further write-down, < 0 reversal (recovery) on units on hand
            self.nrv_allowance[category] = needed
            for d in details:
                self.nrv_unit_shortfall[d["item"]] = d["shortfall_minor"] // max(
                    d["qty_on_hand"], 1
                )
            lines = []
            if consumed:
                lines += [
                    {"account": "1290", "debit_minor": consumed, "credit_minor": 0},
                    {"account": "5000", "debit_minor": 0, "credit_minor": consumed},
                ]
            if change > 0:
                lines += [
                    {"account": "5100", "debit_minor": change, "credit_minor": 0},
                    {"account": "1290", "debit_minor": 0, "credit_minor": change},
                ]
            elif change < 0:
                lines += [
                    {"account": "1290", "debit_minor": -change, "credit_minor": 0},
                    {"account": "5100", "debit_minor": 0, "credit_minor": -change},
                ]
            if not lines:
                continue
            reason = "nrv_writedown" if change > 0 else "nrv_writedown_reversal"
            event = self._event(
                "journal_adjustment",
                core.local_time(day, 18 * 60, 0, self.offset),
                day,
                "manual",
                f"nrv:{category}:{day.isoformat()}",
                {"lines": lines, "reason": reason, "approver": "usr_owner"},
            )
            self.nrv_events.append(event["id"])
            self.nrv_records.append(
                {
                    "event_id": event["id"],
                    "category": category,
                    "assessment_date": day.isoformat(),
                    "allowance_before_minor": previous,
                    "used_by_sales_minor": consumed,
                    "allowance_after_minor": needed,
                    "writedown_minor": max(change, 0),
                    "reversal_minor": max(-change, 0),
                    "items": details,
                }
            )

    # ------------------------------------------------------------ POS
    def _anomaly(self, kind: str, register: str, day: date) -> dict | None:
        for a in self.cfg["pos"].get("anomalies", []):
            if (
                a["kind"] == kind
                and a["register"] == register
                and a["start"] <= day.isoformat() <= a["end"]
            ):
                return a
        return None

    def _pos_day(
        self, day: date, rng, receipt_seq: dict[str, int], recent: dict[str, list[dict]]
    ) -> None:
        pos = self.cfg["pos"]
        methods = list(pos["payment_mix"])
        method_weights = [pos["payment_mix"][m] for m in methods]
        drawer = {
            r: {
                "cash_sales": 0,
                "cash_refunds": 0,
                **dict.fromkeys(NON_CASH, 0),
                "receipts": 0,
                "refunds": 0,
                "voids": 0,
            }
            for b in self.cfg["branches"]
            for r in b["registers"]
        }
        traffic = self.traffic_pct(day) * self.growth_ppm(day) // 1_000_000
        arrivals = []
        for branch in self.cfg["branches"]:
            n = branch["daily_receipts"] * pos["weekday_pct"][
                day.weekday()
            ] * traffic // 10_000 + rng.randint(-5, 5)
            arrivals += [
                (rng.randint(pos["open_minute"] * 60, pos["close_minute"] * 60), branch["id"])
                for _ in range(n)
            ]
        branches = {b["id"]: b for b in self.cfg["branches"]}
        for second_of_day, branch_id in sorted(arrivals):
            branch = branches[branch_id]
            register = rng.choice(branch["registers"])
            minute = second_of_day // 60
            shift = 1 if minute < pos["shift_change_minute"] else 2
            cashier = f"CSH-{int(register[1:]) * 2 - 2 + shift:02d}"
            moment = core.local_time(day, minute, second_of_day % 60, self.offset)
            spike = self._anomaly("refund_spike", register, day)
            refund_rate = (
                spike["refund_per_mille"]
                if spike and spike["cashier"] == cashier
                else pos["refund_per_mille"]
            )
            roll = rng.randint(1, 1000)
            if roll <= refund_rate and recent[branch["id"]]:
                self._refund(
                    day, moment, branch, register, cashier, rng, receipt_seq, recent, drawer
                )
                continue
            txn = "void" if roll <= refund_rate + pos["void_per_mille"] else "sale"
            self._sale(
                day,
                moment,
                branch,
                register,
                cashier,
                txn,
                rng,
                methods,
                method_weights,
                receipt_seq,
                recent,
                drawer,
            )
        for branch in self.cfg["branches"]:
            for register in branch["registers"]:
                self._z_report(day, branch, register, drawer[register], rng)

    def _sale(
        self,
        day,
        moment,
        branch,
        register,
        cashier,
        txn,
        rng,
        methods,
        method_weights,
        receipt_seq,
        recent,
        drawer,
    ) -> None:
        pos = self.cfg["pos"]
        weights_all, _ = self._weights(day)
        in_stock = [s for s in self.items if self.stock[s] > 0 and weights_all[s] > 0]
        if not in_stock:
            return
        n_lines = rng.choices([1, 2, 3], weights=pos["lines_weights"])[0]
        weights = [weights_all[s] for s in in_stock]
        chosen: list[str] = []
        for _ in range(n_lines):
            sku = rng.choices(in_stock, weights=weights)[0]
            if sku not in chosen:
                chosen.append(sku)
        method = rng.choices(methods, weights=method_weights)[0]
        customer = None
        if rng.randint(1, 100) <= pos["loyalty_share_pct"]:
            customer = f"C-{rng.randint(1, pos['loyalty_customers']):04d}"
        promo_bp = pos["discount_bp"] if rng.randint(1, 100) <= pos["discount_share_pct"] else 0
        receipt_seq[register] += 1
        receipt_no = f"{register}-{receipt_seq[register]:06d}"
        lines = []
        for sku in chosen:
            qty = min(rng.choices([1, 2], weights=pos["qty_weights"])[0], self.stock[sku])
            price = self.price_at(sku, day)
            discount_bp = max(promo_bp, self._window_discount_bp(sku, day))
            discount = core.div_half_up(qty * price * discount_bp, 10_000 * 100) * 100
            total = qty * price - discount
            lines.append(
                {
                    "item": sku,
                    "qty": qty,
                    "price_minor": price,
                    "discount_minor": discount,
                    "total_minor": total,
                    "tax_minor": core.tax_within(total, self.gst_bp),
                    "cost_minor": self.layer_cost.get(sku, self.cost_at(sku, day)),
                }
            )
            if txn == "sale":
                self.stock[sku] -= qty
                self.demand_actual[(day, sku)] = self.demand_actual.get((day, sku), 0) + qty
        self._record_receipt(
            day,
            moment,
            branch,
            register,
            cashier,
            receipt_no,
            txn,
            None,
            customer,
            lines,
            method,
            drawer,
        )
        if txn == "sale":
            recent[branch["id"]].append(
                {"receipt_no": receipt_no, "day": day, "lines": lines, "customer": customer}
            )
            recent[branch["id"]][:] = [
                r for r in recent[branch["id"]] if (day - r["day"]).days <= 7
            ]

    def _refund(
        self, day, moment, branch, register, cashier, rng, receipt_seq, recent, drawer
    ) -> None:
        original = rng.choice(recent[branch["id"]])
        line = rng.choice(original["lines"])
        receipt_seq[register] += 1
        receipt_no = f"{register}-{receipt_seq[register]:06d}"
        refund_line = {
            **line,
            "qty": -line["qty"],
            "discount_minor": -line["discount_minor"],
            "total_minor": -line["total_minor"],
            "tax_minor": -line["tax_minor"],
        }
        self.stock[line["item"]] += line["qty"]
        self._record_receipt(
            day,
            moment,
            branch,
            register,
            cashier,
            receipt_no,
            "refund",
            original["receipt_no"],
            original["customer"],
            [refund_line],
            "cash",
            drawer,
        )

    def _record_receipt(
        self,
        day,
        moment,
        branch,
        register,
        cashier,
        receipt_no,
        txn,
        original,
        customer,
        lines,
        method,
        drawer,
    ) -> None:
        status = "settled" if txn == "sale" else "reversed"
        first_row = len(self.pos_rows) + 1
        for i, ln in enumerate(lines, start=1):
            self.pos_rows.append(
                {
                    "receipt_no": receipt_no,
                    "line_no": i,
                    "txn_type": txn,
                    "original_receipt_no": original,
                    "occurred_at": core.iso(moment),
                    "business_date": day.isoformat(),
                    "branch_id": branch["id"],
                    "register_id": register,
                    "cashier_id": cashier,
                    "customer_code": customer,
                    "sku": ln["item"],
                    "qty": ln["qty"],
                    "unit_price_minor": ln["price_minor"],
                    "discount_minor": ln["discount_minor"],
                    "line_total_minor": ln["total_minor"],
                    "tax_minor": ln["tax_minor"],
                    "payment_method": method,
                    "payment_status": status,
                    "currency": self.currency,
                }
            )
        total = sum(ln["total_minor"] for ln in lines)
        tax = sum(ln["tax_minor"] for ln in lines)
        event = self._event(
            "sale",
            moment,
            day,
            "pos_export",
            receipt_no,
            {
                "party": "cus_" + customer[2:] if customer else None,
                "receipt_no": receipt_no,
                "txn": txn,
                "original_receipt_no": original,
                "branch": branch["id"],
                "register": register,
                "cashier": cashier,
                "lines": lines,
                "total_minor": total,
                "tax_minor": tax,
                "payment": {"method": method, "status": status},
            },
            {"file": "pos_sales.csv", "row": first_row},
        )
        d = drawer[register]
        if txn == "void":
            d["voids"] += 1
            return
        self._add_tax(self.output_tax, day, tax)
        if txn == "refund":
            d["refunds"] += 1
            d["cash_refunds"] += total
        else:
            d["receipts"] += 1
            if method == "cash":
                d["cash_sales"] += total
            else:
                d[method] += total
        self.pending.append(
            {
                "day": day,
                "branch": branch["id"],
                "method": method,
                "amount": total,
                "event_id": event["id"],
            }
        )

    def _z_report(self, day, branch, register, d, rng) -> None:
        pos = self.cfg["pos"]
        expected = pos["opening_float_minor"] + d["cash_sales"] + d["cash_refunds"]
        over_short = 0
        shortage = self._anomaly("cash_shortage", register, day)
        if d["receipts"] and shortage and rng.randint(1, 100) <= shortage["shortage_share_pct"]:
            low, high = shortage["shortage_range_minor"]
            over_short = rng.randint(low // 100, high // 100) * 100
        elif d["receipts"] and rng.randint(1, 100) <= pos["over_short_share_pct"]:
            low, high = pos["over_short_range_minor"]
            over_short = rng.randint(low // 100, high // 100) * 100
        counted = expected + over_short
        self.z_rows.append(
            {
                "z_no": f"Z-{register}-{day.strftime('%y%m%d')}",
                "business_date": day.isoformat(),
                "branch_id": branch["id"],
                "register_id": register,
                "opening_float_minor": pos["opening_float_minor"],
                "cash_sales_minor": d["cash_sales"],
                "cash_refunds_minor": d["cash_refunds"],
                "expected_cash_minor": expected,
                "counted_cash_minor": counted,
                "over_short_minor": over_short,
                "card_total_minor": d["card"],
                "bank_qr_total_minor": d["bank_qr"],
                "raast_total_minor": d["raast"],
                "jazzcash_total_minor": d["jazzcash"],
                "easypaisa_total_minor": d["easypaisa"],
                "receipt_count": d["receipts"],
                "refund_count": d["refunds"],
                "void_count": d["voids"],
                "currency": self.currency,
            }
        )
        self.pending_cash.append(
            {
                "day": day,
                "branch": branch["id"],
                "amount": counted - pos["opening_float_minor"],
                "over_short": over_short,
            }
        )

    # ------------------------------------------------------------ B2B invoices
    def _invoice_day(self, day: date, rng) -> None:
        b2b = self.cfg["b2b"]
        if (day - self.start).days % b2b["every_days"] != 2:
            return
        customer = rng.choice(b2b["customers"])
        skus = sorted(
            s
            for s, it in self.items.items()
            if it["category"] in b2b["categories"] and self.stock[s] > 10
        )
        if not skus:
            return
        lines = []
        for sku in sorted(rng.sample(skus, min(len(skus), rng.randint(1, 2)))):
            qty = min(rng.randint(*b2b["qty_range"]), self.stock[sku] - 5)
            unit = self.price_at(sku, day) * 10_000 // (10_000 + self.gst_bp)
            self.stock[sku] -= qty
            lines.append(
                {
                    "sku": sku,
                    "description": self.items[sku]["name"],
                    "qty": qty,
                    "unit_price_minor": unit,
                    "line_total_minor": qty * unit,
                }
            )
        subtotal = sum(ln["line_total_minor"] for ln in lines)
        tax = core.tax_on(subtotal, self.gst_bp)
        invoice_id = self.inv_ids.take()
        invoice = {
            "invoice_id": invoice_id,
            "number": "KAC-INV-" + invoice_id[4:],
            "customer_id": customer["id"],
            "issue_date": day.isoformat(),
            "due_date": (day + timedelta(customer["terms_days"])).isoformat(),
            "currency": self.currency,
            "lines": lines,
            "subtotal_minor": subtotal,
            "tax": [{"code": "GST", "rate_bp": self.gst_bp, "amount_minor": tax}],
            "total_minor": subtotal + tax,
        }
        self.invoices.append(invoice)
        self._add_tax(self.output_tax, day, tax)
        event = self._event(
            "customer_invoice",
            core.local_time(day, 21 * 60 + 45, 0, self.offset),
            day,
            "invoicing",
            invoice_id,
            {
                "party": customer["id"],
                "invoice_id": invoice_id,
                "number": invoice["number"],
                "issue_date": invoice["issue_date"],
                "due_date": invoice["due_date"],
                "lines": lines,
                "subtotal_minor": subtotal,
                "tax_minor": tax,
                "total_minor": invoice["total_minor"],
            },
            {"file": "customer_invoices.json"},
        )
        pay_on = date.fromisoformat(invoice["due_date"]) + timedelta(
            rng.randint(*b2b["pay_offset_days"])
        )
        self.receivables.append(
            {
                "invoice": invoice,
                "event_id": event["id"],
                "pay_on": self.cal.on_or_before(pay_on),
                "combine": rng.randint(1, 100) <= b2b["combine_share_pct"],
            }
        )

    # ------------------------------------------------------------ bank
    def _settle(self, day: date) -> None:
        lags = self.cfg["pos"]["settlement_lag_business_days"]
        due_ids = {
            id(p)
            for p in self.pending
            if p["method"] != "cash"
            and self.cal.next_business_day(p["day"], lags[p["method"]]) <= day
        }
        groups: dict[tuple[str, str], list[dict]] = {}
        for p in self.pending:
            if id(p) in due_ids:
                groups.setdefault(
                    (p["method"], "ALL" if p["method"] in WALLETS else p["branch"]), []
                ).append(p)
        for (method, branch_id), group in sorted(groups.items()):
            mid = next((b["card_mid"] for b in self.cfg["branches"] if b["id"] == branch_id), "")
            narration = SETTLEMENT_NARRATION[method].format(
                mid=mid, branch=branch_id, batch=day.strftime("%m%d")
            )
            amount = sum(p["amount"] for p in group)
            self._post(
                BankTxn(
                    day,
                    narration,
                    f"ST{day.strftime('%y%m%d')}{method[:2].upper()}{branch_id[-2:]}",
                    amount,
                    "pos_settlement",
                    [p["event_id"] for p in group],
                )
            )
            month = self.mdr_base.setdefault(core.month_index(day), {})
            month[method] = month.get(method, 0) + amount
        cash_ids = {id(p) for p in self.pending if p["method"] == "cash" and p["day"] < day}
        cash_events = [p for p in self.pending if id(p) in cash_ids]
        self.pending = [p for p in self.pending if id(p) not in due_ids and id(p) not in cash_ids]
        drawers = [c for c in self.pending_cash if c["day"] < day]
        self.pending_cash = [c for c in self.pending_cash if c["day"] >= day]
        for branch in self.cfg["branches"]:
            mine = [c for c in drawers if c["branch"] == branch["id"]]
            events = [p["event_id"] for p in cash_events if p["branch"] == branch["id"]]
            amount = sum(c["amount"] for c in mine)
            if not mine or (not events and not amount):
                continue
            self.slip += 1
            self._post(
                BankTxn(
                    day,
                    f"CASH DEPOSIT {branch['id']} SLIP {self.slip:05d}",
                    f"CD{self.slip:07d}",
                    amount,
                    "cash_deposit",
                    events,
                    extra={"over_short_minor": sum(c["over_short"] for c in mine)},
                )
            )

    def _pay_suppliers(self, day: date) -> None:
        for bill in self.bills:
            if bill["bill_id"] in self.never_pay or bill.get("_paid_on"):
                continue
            if (
                self.cal.on_or_before(date.fromisoformat(bill["due_date"])) > day
                or bill["received_at"][:10] > day.isoformat()
            ):
                continue
            party = self.parties[bill["supplier_id"]]
            pay_id = self.pay_ids.take()
            moment = core.local_time(day, 10 * 60, 0, self.offset)
            event = self._event(
                "supplier_payment",
                moment,
                day,
                "manual",
                pay_id,
                {
                    "party": bill["supplier_id"],
                    "payment_id": pay_id,
                    "bill_id": bill["bill_id"],
                    "amount_minor": bill["total_minor"],
                    "from_iban": self.own_iban,
                    "to_iban": party["bank_iban"],
                    "method": "ibft",
                    "wallet_ref": None,
                },
            )
            bill["_paid_on"] = day.isoformat()
            narration = f"IBFT TO {party['name'].upper()} {bill['number'].replace('-', ' ').replace('/', ' ')}"
            self._post(
                BankTxn(
                    day,
                    narration,
                    f"FT{day.strftime('%y%m%d')}{pay_id[4:]}",
                    -bill["total_minor"],
                    "supplier_payment",
                    [event["id"]],
                    bill["supplier_id"],
                )
            )

    def _collect_receivables(self, day: date, rng) -> None:
        due = [r for r in self.receivables if r["pay_on"] <= day and not r.get("paid")]
        by_customer: dict[str, list[dict]] = {}
        for r in due:
            if r["combine"] and any(
                o is not r
                and o["invoice"]["customer_id"] == r["invoice"]["customer_id"]
                and not o.get("paid")
                and o["pay_on"] > day
                for o in self.receivables
            ):
                continue
            by_customer.setdefault(r["invoice"]["customer_id"], []).append(r)
        for customer_id, group in sorted(by_customer.items()):
            for r in group:
                r["paid"] = True
            party = self.parties[customer_id]
            numbers = " ".join(r["invoice"]["number"] for r in group)
            narration = f"IBFT FROM {party['name'].upper()}" + (
                f" {numbers}" if rng.randint(1, 100) <= 70 else ""
            )
            self._post(
                BankTxn(
                    day,
                    narration,
                    f"FT{day.strftime('%y%m%d')}{customer_id[4:]}",
                    sum(r["invoice"]["total_minor"] for r in group),
                    "customer_receipt",
                    [r["event_id"] for r in group],
                    customer_id,
                    extra={"invoice_ids": [r["invoice"]["invoice_id"] for r in group]},
                )
            )

    def _post(self, txn: BankTxn) -> None:
        self.bank.append(txn)
        self.balance += txn.amount_minor

    def _on(self, day: date, nominal: date) -> bool:
        return day == self.cal.on_or_before(nominal)

    def _recurring(self, day: date, rng) -> None:
        rec, cfg = self.cfg["recurring"], self.cfg
        mon = day.strftime("%b-%Y").upper()
        payroll = cfg["payroll"]
        if day == self.cal.nth_business_day(day.year, day.month, payroll["day"]):
            gross = finance.payroll_gross(payroll, day)
            wht = gross * payroll["wht_bp"] // 10_000
            self.payroll_rows.append(
                {
                    "month": day.strftime("%Y-%m"),
                    "paid_on": day.isoformat(),
                    "headcount": payroll["headcount"],
                    "gross_minor": gross,
                    "wht_minor": wht,
                    "net_minor": gross - wht,
                }
            )
            self._post(
                BankTxn(
                    day,
                    f"SALARY BULK TRF {mon}",
                    f"SAL{day.strftime('%y%m')}",
                    -(gross - wht),
                    "payroll",
                )
            )
            self.wht_due.append((date(day.year, day.month, rec["wht_day"]), wht, mon))
        for nominal, amount, label in list(self.wht_due):
            if self._on(day, nominal):
                self._post(
                    BankTxn(
                        day,
                        f"FBR WHT SALARIES {label}",
                        f"WHT{day.strftime('%y%m')}",
                        -amount,
                        "tax",
                        party="pty_006",
                    )
                )
                self.wht_due.remove((nominal, amount, label))
        for row in self.lease_rows:
            if row["paid_on"] == day.isoformat():
                self._post(
                    BankTxn(
                        day,
                        f"RENT {mon} BR02 CLIFTON",
                        f"RNT{day.strftime('%y%m')}BR02",
                        -row["amount_minor"],
                        "rent",
                        party="pty_002",
                    )
                )
        for row in self.loan["schedule"]:
            if row["paid_on"] == day.isoformat():
                self._post(
                    BankTxn(
                        day,
                        f"LOAN INSTALMENT {row['n']:02d}/{self.loan['instalments']}",
                        f"LN{day.strftime('%y%m')}",
                        -row["instalment_minor"],
                        "loan",
                        party="pty_005",
                        extra={
                            "principal_minor": row["principal_minor"],
                            "interest_minor": row["interest_minor"],
                        },
                    )
                )
        if self._on(day, date.fromisoformat(cfg["loan"]["disbursed_on"])):
            self._post(
                BankTxn(
                    day,
                    "LOAN DISBURSEMENT SME FINANCE",
                    "LNDISB",
                    cfg["loan"]["principal_minor"],
                    "loan_disbursement",
                    party="pty_005",
                )
            )
        summer = 5 <= day.month <= 9
        if self._on(day, date(day.year, day.month, rec["electricity_day"])):
            low, high = rec[
                "electricity_summer_range_minor" if summer else "electricity_winter_range_minor"
            ]
            self._post(
                BankTxn(
                    day,
                    f"ELECTRICITY BILL {mon}",
                    f"EL{day.strftime('%y%m')}",
                    -rng.randint(low // 100, high // 100) * 100,
                    "utilities",
                    party="pty_003",
                )
            )
        if self._on(day, date(day.year, day.month, rec["gas_day"])):
            low, high = rec["gas_range_minor"]
            self._post(
                BankTxn(
                    day,
                    f"GAS BILL {mon}",
                    f"GS{day.strftime('%y%m')}",
                    -rng.randint(low // 100, high // 100) * 100,
                    "utilities",
                    party="pty_004",
                )
            )
        for kind, label in (
            ("security", "SECURITY AND CLEANING"),
            ("marketing", "DIGITAL MARKETING"),
            ("drawings", "OWNER DRAWINGS TRF"),
        ):
            # The owner skips a month's drawings when the account would fall below the comfort level.
            if (
                kind == "drawings"
                and self.balance - rec["drawings_minor"] < rec["drawings_min_balance_minor"]
            ):
                continue
            if self._on(day, date(day.year, day.month, rec[f"{kind}_day"])):
                self._post(
                    BankTxn(
                        day,
                        f"{label} {mon}",
                        f"{kind[:3].upper()}{day.strftime('%y%m')}",
                        -rec[f"{kind}_minor"],
                        kind,
                    )
                )
        if self._on(day, date(day.year, day.month, rec["bank_charges_day"])):
            self._post(
                BankTxn(
                    day,
                    f"BANK CHARGES {mon}",
                    f"BC{day.strftime('%y%m')}",
                    -rec["bank_charges_minor"],
                    "bank_charges",
                )
            )
        prev_month = core.month_index(day) - 1
        prev_label = date(prev_month // 12, prev_month % 12 + 1, 1).strftime("%b-%Y").upper()
        if (
            day == self.cal.nth_business_day(day.year, day.month, rec["mdr_day"])
            and prev_month in self.mdr_base
        ):
            mdr = self.cfg["pos"]["mdr_bp"]
            fee = sum(
                core.div_half_up(amount * mdr[m], 10_000)
                for m, amount in sorted(self.mdr_base[prev_month].items())
            )
            if fee:
                self._post(
                    BankTxn(
                        day,
                        f"MDR CHARGES {prev_label}",
                        f"MDR{day.strftime('%y%m')}",
                        -fee,
                        "mdr_fees",
                    )
                )
        if self._on(day, date(day.year, day.month, rec["tax_day"])):
            if prev_month < core.month_index(self.start):
                net = rec["opening_sales_tax_payable_minor"]
            else:
                net = (
                    self.output_tax.get(prev_month, 0)
                    - self.input_tax.get(prev_month, 0)
                    - self.tax_credit
                )
            self.tax_credit = max(0, -net)  # excess input tax carries forward
            if net > 0:
                self._post(
                    BankTxn(
                        day,
                        f"FBR SALES TAX {prev_label}",
                        f"FBR{day.strftime('%y%m')}",
                        -net,
                        "tax",
                        party="pty_006",
                    )
                )
        for instalment in rec["advance_tax"]:
            nominal = date(day.year, int(instalment["due"][:2]), int(instalment["due"][3:]))
            if self._on(day, nominal):
                self._post(
                    BankTxn(
                        day,
                        f"FBR ADVANCE INCOME TAX {mon}",
                        f"ADV{day.strftime('%y%m')}",
                        -instalment["minor"],
                        "income_tax",
                        party="pty_006",
                    )
                )
        for asset in self.cfg["fixed_assets"]:
            acquired = date.fromisoformat(asset["acquired_on"])
            if asset.get("payee") and acquired >= self.start and self._on(day, acquired):
                payee = self.parties[asset["payee"]]
                self._post(
                    BankTxn(
                        day,
                        f"IBFT TO {payee['name'].upper()} {asset['id'].upper()}",
                        f"CPX{asset['id'][3:]}",
                        -asset["cost_minor"],
                        "capex",
                        party=asset["payee"],
                        extra={"asset_id": asset["id"]},
                    )
                )

    # ------------------------------------------------------------ run
    def run(self) -> dict:
        self.pending: list[dict] = []
        self.pending_cash: list[dict] = []
        self.receivables: list[dict] = []
        self.mdr_base: dict[int, dict[str, int]] = {}
        self.payroll_rows: list[dict] = []
        self.wht_due: list[tuple[date, int, str]] = []
        self.slip = 0
        self.balance = self.cfg["bank"]["opening_balance_minor"]
        self.lease_rows = finance.lease_payments(
            next(ls for ls in self.cfg["leases"] if not ls.get("billed")),
            self.start,
            self.end,
            self.cal,
        )
        receipt_seq = {r: 0 for b in self.cfg["branches"] for r in b["registers"]}
        recent: dict[str, list[dict]] = {b["id"]: [] for b in self.cfg["branches"]}
        streams = {
            name: core.stream(self.seed, name) for name in ("purchasing", "pos", "b2b", "bank")
        }
        self._opening_balances()
        for day in core.days(self.start, self.end):
            self._order_day(day, streams["purchasing"])
            self._receive_goods(day, streams["purchasing"])
            self._planted_followups(day)
            self._rent_bill(day)
            self._pos_day(day, streams["pos"], receipt_seq, recent)
            self._invoice_day(day, streams["b2b"])
            if self.cal.is_business_day(day):
                self._settle(day)
                self._pay_suppliers(day)
                self._collect_receivables(day, streams["bank"])
                self._recurring(day, streams["bank"])
            self._nrv_day(day)
            if day == self.as_of:
                self.stock_at_as_of = dict(self.stock)
        from data.generator.outputs import build_outputs

        return build_outputs(self)

    def _opening_balances(self) -> None:
        rec = self.cfg["recurring"]
        register = finance.asset_register(self.cfg["fixed_assets"], self.start, self.as_of)
        prior = [a for a in register if not a["in_period"]]
        ppe = sum(a["cost_minor"] for a in prior)
        acc_dep = sum(a["accumulated_depreciation_at_start_minor"] for a in prior)
        inventory = sum(
            it["opening_stock_qty"] * self.layer_cost.get(s, 0) for s, it in self.items.items()
        )
        floats = self.cfg["pos"]["opening_float_minor"] * sum(
            len(b["registers"]) for b in self.cfg["branches"]
        )
        deposit = next(
            (
                ls.get("security_deposit_minor", 0)
                for ls in self.cfg["leases"]
                if not ls.get("billed")
            ),
            0,
        )
        cash = self.cfg["bank"]["opening_balance_minor"]
        tax_payable = rec["opening_sales_tax_payable_minor"]
        equity = cash + floats + inventory + deposit + ppe - acc_dep - tax_payable
        self.opening_lines = [
            {"account": "1000", "debit_minor": cash, "credit_minor": 0},
            {"account": "1010", "debit_minor": floats, "credit_minor": 0},
            {"account": "1200", "debit_minor": inventory, "credit_minor": 0},
            {"account": "1400", "debit_minor": deposit, "credit_minor": 0},
            {"account": "1500", "debit_minor": ppe, "credit_minor": 0},
            {"account": "1510", "debit_minor": 0, "credit_minor": acc_dep},
            {"account": "2100", "debit_minor": 0, "credit_minor": tax_payable},
            {"account": "3000", "debit_minor": 0, "credit_minor": equity},
        ]
        self._event(
            "journal_adjustment",
            core.local_time(self.start, 0, 0, 0),
            self.start,
            "manual",
            "opening_balances",
            {"lines": self.opening_lines, "reason": "opening_balances", "approver": "owner"},
        )


def generate(
    config: dict,
    seed: int,
    months: int,
    mandates: list[dict],
    scenarios: dict,
    mandates_source: str = "rulebook/mandates.yaml",
) -> dict:
    sim = Simulation(config, seed, months, mandates, scenarios)
    sim.mandates_source = mandates_source
    return sim.run()
