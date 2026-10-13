"""Day-by-day simulation of one synthetic business (generator v0, D2a).

The simulation keeps stock, payables, receivables and the bank balance consistent, so every
bank line really is a POS settlement, a cash deposit, a supplier payment, a customer receipt
or a known recurring cost. Everything is driven by the persona config and the seed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from data.generator import core
from data.generator.render import render_bill

GENERATOR_VERSION = "0.1.0"
WALLETS = ("jazzcash", "easypaisa")
NON_CASH = ("card", "bank_qr", "raast", "jazzcash", "easypaisa")
SETTLEMENT_NARRATION = {
    "card": "POS CARD SETTL MID {mid} BATCH {batch}",
    "bank_qr": "QR SETTL {branch} BATCH {batch}",
    "raast": "RAAST P2M SETTL {branch} BATCH {batch}",
    "jazzcash": "JAZZCASH MERCH SETTL BATCH {batch}",
    "easypaisa": "EASYPAISA MERCH SETTL BATCH {batch}",
}


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


@dataclass
class Output:
    tenant: dict
    mandates: list[dict]
    accounts: list[list[str]]
    parties: list[dict]
    items: list[dict]
    purchase_orders: list[dict]
    goods_received: list[dict]
    bills: list[dict]
    documents: dict[str, bytes]
    invoices: list[dict]
    bank_rows: list[dict]
    pos_rows: list[dict]
    z_rows: list[dict]
    events: list[dict]
    answer_key: dict


class Simulation:
    def __init__(self, config: dict, seed: int, months: int, mandates: list[dict]) -> None:
        self.cfg, self.seed, self.mandates = config, seed, mandates
        t = config["tenant"]
        self.tenant_id, self.currency = t["id"], t["currency"]
        self.offset = t["utc_offset_hours"]
        self.gst_bp = config["country_pack_draft"]["gst_rate_bp"]
        self.end = date.fromisoformat(t["as_of"])
        self.start = core.add_months(self.end, -months) + timedelta(1)
        self.country = t["country"]
        demo = config.get("demo", {})
        reserved_bills = {
            d[k]
            for d in demo.values()
            for k in ("bill_id", "original_bill_id", "resend_bill_id")
            if k in d
        }
        reserved_docs = {
            d[k]
            for d in demo.values()
            for k in ("document_id", "original_document_id", "resend_document_id")
            if k in d
        }
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
        self.scenarios: list[dict] = []
        self.unpaid_bill_ids: set[str] = set()
        self._build_parties()
        self._build_items()

    # ------------------------------------------------------------ setup
    def _account_digits(self, rng) -> str:
        return "".join(str(rng.randint(0, 9)) for _ in range(16))

    def _build_parties(self) -> None:
        rng = core.stream(self.seed, "parties")
        bank = self.cfg["bank"]
        self.own_iban = core.iban(self.country, bank["iban_bank_code"], self._account_digits(rng))
        self.parties: dict[str, dict] = {}
        for i, s in enumerate(self.cfg["suppliers"]):
            ntn = f"{rng.randint(1_000_000, 9_999_999)}-{rng.randint(0, 9)}"
            code = "SYNB" if i % 2 == 0 else "SYND"
            self.parties[s["id"]] = {
                "party_id": s["id"],
                "kind": "supplier",
                "code": "S-" + s["id"][4:],
                "name": s["name"],
                "tax_id": ntn,
                "tax_id_type": "NTN",
                "bank_iban": core.iban(self.country, code, self._account_digits(rng)),
                "bank_account_changed_at": None,
                "on_allow_list": s["allow_list"],
                "payment_terms_days": s["terms_days"],
                "credit_limit_minor": None,
                "phone": f"+92-000-000-{s['id'][4:].zfill(4)}",
                "city": s["city"],
            }
        loyalty = self.cfg["pos"]["loyalty_customers"]
        for n in range(1, loyalty + 1):
            pid = f"cus_{n:04d}"
            self.parties[pid] = {
                "party_id": pid,
                "kind": "customer",
                "code": f"C-{n:04d}",
                "name": f"Customer C-{n:04d}",
                "tax_id": None,
                "tax_id_type": None,
                "bank_iban": None,
                "bank_account_changed_at": None,
                "on_allow_list": False,
                "payment_terms_days": 0,
                "credit_limit_minor": None,
                "phone": None,
                "city": "Karachi",
            }
        for c in self.cfg["b2b"]["customers"]:
            self.parties[c["id"]] = {
                "party_id": c["id"],
                "kind": "customer",
                "code": c["code"],
                "name": c["name"],
                "tax_id": f"{rng.randint(1_000_000, 9_999_999)}-{rng.randint(0, 9)}",
                "tax_id_type": "NTN",
                "bank_iban": core.iban(self.country, "SYNE", self._account_digits(rng)),
                "bank_account_changed_at": None,
                "on_allow_list": False,
                "payment_terms_days": c["terms_days"],
                "credit_limit_minor": c["credit_limit_minor"],
                "phone": None,
                "city": "Karachi",
            }
        for o in self.cfg["others"]:
            self.parties[o["id"]] = {
                "party_id": o["id"],
                "kind": o["kind"],
                "code": o["id"].upper().replace("_", "-"),
                "name": o["name"],
                "tax_id": None,
                "tax_id_type": None,
                "bank_iban": core.iban(self.country, "SYNF", self._account_digits(rng)),
                "bank_account_changed_at": None,
                "on_allow_list": True,
                "payment_terms_days": 0,
                "credit_limit_minor": None,
                "phone": None,
                "city": "Karachi",
            }
        self.supplier_cfg = {s["id"]: s for s in self.cfg["suppliers"]}
        self.invoice_counter = {s["id"]: s["invoice_start"] for s in self.cfg["suppliers"]}

    def _build_items(self) -> None:
        pos = self.cfg["pos"]
        size_weights = pos["size_weights"]
        self.items: dict[str, dict] = {}
        self.weights: dict[str, int] = {}
        for cat in self.cfg["categories"]:
            variants = [(s, c) for s in cat["sizes"] for c in cat["colours"]]
            total_size = sum(size_weights[s] for s, _ in variants)
            for size, colour in variants:
                sku = f"{cat['code']}-{size}-{colour}"
                supplier = self.supplier_cfg[cat["supplier"]]
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
                    "supplier_id": cat["supplier"],
                    "lead_time_days": supplier["lead_time_days"],
                    "launched_on": cat["launched_on"],
                }
                # Integer weight per SKU, in 1/10000 of the category weight.
                self.weights[sku] = cat["weight"] * 10_000 * size_weights[size] // total_size
        self.units_per_day_x100 = self._expected_units_x100()
        stock_cfg = self.cfg["purchasing"]
        self.stock: dict[str, int] = {}
        self.on_order: dict[str, int] = dict.fromkeys(self.items, 0)
        for sku, item in self.items.items():
            per_day = self._demand_x100(sku, self.start)
            opening = -(-per_day * stock_cfg["opening_cover_days"] // 100)
            item["opening_stock_qty"] = opening
            item["reorder_level"] = -(
                -per_day * (item["lead_time_days"] + stock_cfg["reorder_days"]) // 100
            )
            self.stock[sku] = opening

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

    def _season_pct(self, sku: str, day: date) -> int:
        if self.items[sku]["season"] == "winter":
            return self.cfg["pos"]["winter_month_pct"][day.month - 1]
        return 100

    def _demand_x100(self, sku: str, day: date) -> int:
        """Expected units per day for one SKU, times 100 (integer)."""
        weighted = {s: self.weights[s] * self._season_pct(s, day) for s in self.items}
        return self.units_per_day_x100 * weighted[sku] // sum(weighted.values())

    # ------------------------------------------------------------ events
    def _event(
        self,
        kind: str,
        occurred_at: datetime,
        business_date: date,
        source_type: str,
        key: str,
        fields: dict,
        source_extra: dict | None = None,
        prefix: str = "evt",
    ) -> dict:
        event_id = core.source_ulid(prefix, occurred_at, self.tenant_id, source_type, key)
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

    # ------------------------------------------------------------ purchasing
    def _supplier_number(self, supplier_id: str, rng) -> str:
        cfg = self.supplier_cfg[supplier_id]
        number = self.invoice_counter[supplier_id]
        self.invoice_counter[supplier_id] += rng.randint(2, 6)
        return f"{cfg['invoice_prefix']}{number}"

    def _create_po(
        self, day: date, supplier_id: str, lines: list[dict], forced: dict | None = None
    ) -> dict:
        po_id = self.po_ids.take()
        lead = self.supplier_cfg[supplier_id]["lead_time_days"]
        expected = (
            date.fromisoformat(forced["received_on"])
            if forced and "received_on" in forced
            else day + timedelta(lead)
        )
        po = {
            "po_id": po_id,
            "number": "PO-" + po_id[3:],
            "supplier_id": supplier_id,
            "ordered_on": day.isoformat(),
            "expected_on": expected.isoformat(),
            "status": "open",
            "currency": self.currency,
            "lines": lines,
            "total_minor": sum(line["qty"] * line["unit_cost_minor"] for line in lines),
            "_forced": forced,
        }
        for line in lines:
            if line.get("sku"):
                self.on_order[line["sku"]] += line["qty"]
        self.pos.append(po)
        return po

    def _order_day(self, day: date, rng) -> None:
        purchasing = self.cfg["purchasing"]
        forced_today = {}
        for name, demo in self.cfg.get("demo", {}).items():
            if demo.get("ordered_on") == day.isoformat():
                forced_today[demo["supplier"]] = (name, demo)
        for supplier_id, (name, demo) in sorted(forced_today.items()):
            if name == "duplicate_bill":
                lines = [
                    {
                        "sku": ln.get("sku"),
                        "description": ln.get(
                            "description", self.items[ln["sku"]]["name"] if ln.get("sku") else ""
                        ),
                        "qty": ln["qty"],
                        "unit_cost_minor": ln["unit_price_minor"],
                    }
                    for ln in demo["lines"]
                ]
            else:
                skus = sorted(
                    s for s, it in self.items.items() if it["category"] == demo["category"]
                )
                lines = [
                    {
                        "sku": s,
                        "description": self.items[s]["name"],
                        "qty": demo["qty_per_sku"],
                        "unit_cost_minor": self.items[s]["unit_cost_minor"],
                    }
                    for s in skus
                ]
            self._create_po(day, supplier_id, lines, forced={"name": name, **demo})
        if day.weekday() not in purchasing["order_weekdays"]:
            return
        by_supplier: dict[str, list[str]] = {}
        for sku, item in self.items.items():
            by_supplier.setdefault(item["supplier_id"], []).append(sku)
        for supplier_id in sorted(by_supplier):
            if supplier_id in forced_today:
                continue
            lines = []
            for sku in sorted(by_supplier[supplier_id]):
                item = self.items[sku]
                per_day = self._demand_x100(sku, day + timedelta(item["lead_time_days"]))
                projected = self.stock[sku] + self.on_order[sku]
                reorder_at = per_day * (item["lead_time_days"] + purchasing["reorder_days"]) // 100
                if projected > reorder_at:
                    continue
                target = -(-per_day * (item["lead_time_days"] + purchasing["cover_days"]) // 100)
                pack = purchasing["pack_size"]
                qty = -(-(target - projected) // pack) * pack
                if qty > 0:
                    lines.append(
                        {
                            "sku": sku,
                            "description": item["name"],
                            "qty": qty,
                            "unit_cost_minor": item["unit_cost_minor"],
                        }
                    )
            if lines:
                self._create_po(day, supplier_id, lines)

    def _receive_goods(self, day: date, rng) -> None:
        for po in self.pos:
            if po["expected_on"] != day.isoformat() or po["status"] != "open":
                continue
            grn_id = "grn_" + po["po_id"][3:]
            lines = [
                {"sku": ln["sku"], "qty_received": ln["qty"]} for ln in po["lines"] if ln.get("sku")
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
            po["status"] = "received"
            moment = core.local_time(day, 11 * 60, 0, self.offset)
            for ln in lines:
                self.stock[ln["sku"]] += ln["qty_received"]
                self.on_order[ln["sku"]] -= ln["qty_received"]
                self._event(
                    "stock_movement",
                    moment,
                    day,
                    "manual",
                    f"{grn_id}#{ln['sku']}",
                    {
                        "item": ln["sku"],
                        "qty": ln["qty_received"],
                        "unit_cost_minor": self.items[ln["sku"]]["unit_cost_minor"],
                        "reason": "goods_received",
                        "ref": grn_id,
                    },
                )
            forced = po["_forced"]
            if forced and forced["name"] == "duplicate_bill":
                self._bill(
                    po,
                    date.fromisoformat(forced["original_issue_date"]),
                    forced["original_number"],
                    bill_id=forced["original_bill_id"],
                    doc_id=forced["original_document_id"],
                    due=date.fromisoformat(forced["original_due_date"]),
                )
            elif forced:
                self._bill(
                    po,
                    day,
                    self._supplier_number(po["supplier_id"], rng),
                    bill_id=forced["bill_id"],
                    doc_id=forced["document_id"],
                )
            else:
                self._bill(po, day, self._supplier_number(po["supplier_id"], rng))

    def _bill(
        self,
        po: dict,
        issue: date,
        number: str,
        *,
        bill_id: str | None = None,
        doc_id: str | None = None,
        due: date | None = None,
        received_at: datetime | None = None,
        iban: str | None = None,
        notes: str = "",
        pay: bool = True,
    ) -> dict:
        supplier = self.parties[po["supplier_id"]]
        terms = self.supplier_cfg[po["supplier_id"]]["terms_days"]
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
        tax = core.tax_on(subtotal, self.gst_bp)
        bill = {
            "bill_id": bill_id or self.bill_ids.take(),
            "document_id": doc_id or self.doc_ids.take(),
            "document_sha256": "",
            "received_at": core.iso(
                received_at or core.local_time(issue + timedelta(1), 10 * 60 + 10, 0, self.offset)
            ),
            "supplier_id": po["supplier_id"],
            "supplier": {
                "name": supplier["name"],
                "tax_id": supplier["tax_id"],
                "bank_iban": iban or supplier["bank_iban"],
            },
            "number": number,
            "issue_date": issue.isoformat(),
            "due_date": (due or issue + timedelta(terms)).isoformat(),
            "po_number": po["number"],
            "currency": self.currency,
            "lines": lines,
            "subtotal_minor": subtotal,
            "tax": [{"code": "GST", "rate_bp": self.gst_bp, "amount_minor": tax}],
            "total_minor": subtotal + tax,
            "notes": notes,
            "extraction": {"method": "synthetic_ground_truth"},
        }
        document = render_bill(bill, supplier, self.cfg["tenant"]["name"])
        bill["document_sha256"] = hashlib.sha256(document).hexdigest()
        self.documents[bill["document_id"]] = document
        self.bills.append(bill)
        if not pay:
            self.unpaid_bill_ids.add(bill["bill_id"])
        self._event(
            "purchase_bill",
            datetime.fromisoformat(bill["received_at"].replace("Z", "+00:00")),
            date.fromisoformat(bill["received_at"][:10]),
            "bill_extraction",
            bill["bill_id"],
            {
                "party": bill["supplier_id"],
                "bill_id": bill["bill_id"],
                "number": number,
                "issue_date": bill["issue_date"],
                "due_date": bill["due_date"],
                "po_number": po["number"],
                "lines": lines,
                "subtotal_minor": subtotal,
                "tax_minor": tax,
                "total_minor": bill["total_minor"],
                "document_id": bill["document_id"],
                "document_sha256": bill["document_sha256"],
            },
            {"file": "bills.json"},
        )
        return bill

    def _planted_resend(self, day: date) -> None:
        demo = self.cfg.get("demo", {}).get("duplicate_bill")
        if not demo:
            return
        if day.isoformat() == demo["bank_change_at"][:10]:
            party = self.parties[demo["supplier"]]
            rng = core.stream(self.seed, "demo-bank-change")
            new_iban = core.iban(
                self.country, demo["new_iban_bank_code"], self._account_digits(rng)
            )
            changed_at = datetime.fromisoformat(demo["bank_change_at"].replace("Z", "+00:00"))
            self._event(
                "bank_detail_change",
                changed_at,
                day,
                "manual",
                f"bdc:{party['party_id']}:{day.isoformat()}",
                {
                    "party": party["party_id"],
                    "old_iban": party["bank_iban"],
                    "new_iban": new_iban,
                    "confirmed_via": demo["bank_change_confirmed_via"],
                    "confirmed_by": "supplier email",
                },
            )
            party["bank_iban"], party["bank_account_changed_at"] = new_iban, demo["bank_change_at"]
        if day.isoformat() == demo["resend_received_at"][:10]:
            original = next(b for b in self.bills if b["bill_id"] == demo["original_bill_id"])
            po = next(p for p in self.pos if p["number"] == original["po_number"])
            rng = core.stream(self.seed, "demo-resend-iban")
            printed_iban = core.iban(
                self.country, demo["new_iban_bank_code"], self._account_digits(rng)
            )
            self._bill(
                po,
                date.fromisoformat(demo["resend_issue_date"]),
                demo["resend_number"],
                bill_id=demo["resend_bill_id"],
                doc_id=demo["resend_document_id"],
                due=date.fromisoformat(demo["resend_due_date"]),
                received_at=datetime.fromisoformat(
                    demo["resend_received_at"].replace("Z", "+00:00")
                ),
                iban=printed_iban,
                notes=demo["resend_notes"],
                pay=False,
            )

    # ------------------------------------------------------------ POS
    def _pos_day(
        self, day: date, rng, receipt_seq: dict[str, int], recent: dict[str, list[dict]]
    ) -> None:
        pos = self.cfg["pos"]
        methods = list(pos["payment_mix"])
        method_weights = [pos["payment_mix"][m] for m in methods]
        # Both branches share one stock, so the day's receipts are processed in time order.
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
        arrivals = []
        for branch in self.cfg["branches"]:
            n = branch["daily_receipts"] * pos["weekday_pct"][day.weekday()] // 100 + rng.randint(
                -6, 6
            )
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
            roll = rng.randint(1, 1000)
            if roll <= pos["refund_per_mille"] and recent[branch["id"]]:
                self._refund(
                    day, moment, branch, register, cashier, rng, receipt_seq, recent, drawer
                )
                continue
            txn = "void" if roll <= pos["refund_per_mille"] + pos["void_per_mille"] else "sale"
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
    ):
        pos = self.cfg["pos"]
        in_stock = [s for s in self.items if self.stock[s] > 0]
        if not in_stock:
            return
        n_lines = rng.choices([1, 2, 3], weights=pos["lines_weights"])[0]
        weights = [self.weights[s] * self._season_pct(s, day) for s in in_stock]
        chosen: list[str] = []
        for _ in range(n_lines):
            sku = rng.choices(in_stock, weights=weights)[0]
            if sku not in chosen:
                chosen.append(sku)
        method = rng.choices(methods, weights=method_weights)[0]
        customer = None
        if rng.randint(1, 100) <= pos["loyalty_share_pct"]:
            customer = f"C-{rng.randint(1, pos['loyalty_customers']):04d}"
        discount_bp = pos["discount_bp"] if rng.randint(1, 100) <= pos["discount_share_pct"] else 0
        receipt_seq[register] += 1
        receipt_no = f"{register}-{receipt_seq[register]:06d}"
        lines = []
        for sku in chosen:
            qty = min(rng.choices([1, 2], weights=pos["qty_weights"])[0], self.stock[sku])
            price = self.items[sku]["price_minor"]
            discount = (
                core.div_half_up(qty * price * discount_bp, 10_000 * 100) * 100
            )  # whole rupees
            total = qty * price - discount
            lines.append(
                {
                    "item": sku,
                    "qty": qty,
                    "price_minor": price,
                    "discount_minor": discount,
                    "total_minor": total,
                    "tax_minor": core.tax_within(total, self.gst_bp),
                    "cost_minor": self.items[sku]["unit_cost_minor"],
                }
            )
            if txn == "sale":
                self.stock[sku] -= qty
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

    def _refund(self, day, moment, branch, register, cashier, rng, receipt_seq, recent, drawer):
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
    ):
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
                "tax_minor": sum(ln["tax_minor"] for ln in lines),
                "payment": {"method": method, "status": status},
            },
            {"file": "pos_sales.csv", "row": first_row},
        )
        d = drawer[register]
        if txn == "void":
            d["voids"] += 1
            return
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

    def _z_report(self, day, branch, register, d, rng):
        pos = self.cfg["pos"]
        expected = pos["opening_float_minor"] + d["cash_sales"] + d["cash_refunds"]
        over_short = 0
        if d["receipts"] and rng.randint(1, 100) <= pos["over_short_share_pct"]:
            low, high = pos["over_short_range_minor"]
            over_short = rng.randint(low // 100, high // 100) * 100
        counted = expected + over_short
        z_no = f"Z-{register}-{day.strftime('%y%m%d')}"
        self.z_rows.append(
            {
                "z_no": z_no,
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
            unit = (
                self.items[sku]["price_minor"] * 10_000 // (10_000 + self.gst_bp)
            )  # ex-GST trade price
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
                "pay_on": core.on_or_before_business_day(pay_on),
                "combine": rng.randint(1, 100) <= b2b["combine_share_pct"],
            }
        )

    # ------------------------------------------------------------ bank
    def _settle(self, day: date) -> None:
        lags = self.cfg["pos"]["settlement_lag_business_days"]
        due = [
            p
            for p in self.pending
            if p["method"] != "cash" and core.next_business_day(p["day"], lags[p["method"]]) <= day
        ]
        self.pending = [p for p in self.pending if p not in due]
        groups: dict[tuple[str, str], list[dict]] = {}
        for p in due:
            key = (p["method"], "ALL" if p["method"] in WALLETS else p["branch"])
            groups.setdefault(key, []).append(p)
        for (method, branch_id), group in sorted(groups.items()):
            mid = next((b["card_mid"] for b in self.cfg["branches"] if b["id"] == branch_id), "")
            batch = day.strftime("%m%d")
            narration = SETTLEMENT_NARRATION[method].format(mid=mid, branch=branch_id, batch=batch)
            self.bank.append(
                BankTxn(
                    day,
                    narration,
                    f"ST{day.strftime('%y%m%d')}{method[:2].upper()}{branch_id[-2:]}",
                    sum(p["amount"] for p in group),
                    "pos_settlement",
                    [p["event_id"] for p in group],
                )
            )
            self.mdr_base.setdefault((day.year, day.month), {}).setdefault(method, 0)
            self.mdr_base[(day.year, day.month)][method] += sum(p["amount"] for p in group)
        # Cash: each branch deposits the counted cash of all days since its last deposit.
        cash_events = [p for p in self.pending if p["method"] == "cash" and p["day"] < day]
        self.pending = [p for p in self.pending if p not in cash_events]
        drawers = [c for c in self.pending_cash if c["day"] < day]
        self.pending_cash = [c for c in self.pending_cash if c not in drawers]
        for branch in self.cfg["branches"]:
            mine = [c for c in drawers if c["branch"] == branch["id"]]
            if not mine:
                continue
            events = [p["event_id"] for p in cash_events if p["branch"] == branch["id"]]
            if not events and not sum(c["amount"] for c in mine):
                continue
            self.slip += 1
            self.bank.append(
                BankTxn(
                    day,
                    f"CASH DEPOSIT {branch['id']} SLIP {self.slip:05d}",
                    f"CD{self.slip:07d}",
                    sum(c["amount"] for c in mine),
                    "cash_deposit",
                    events,
                    extra={"over_short_minor": sum(c["over_short"] for c in mine)},
                )
            )

    def _pay_suppliers(self, day: date) -> None:
        for bill in self.bills:
            if bill["bill_id"] in self.unpaid_bill_ids or bill.get("_paid"):
                continue
            if core.on_or_before_business_day(date.fromisoformat(bill["due_date"])) != day:
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
            bill["_paid"] = True
            narration = f"IBFT TO {party['name'].upper()} {bill['number'].replace('-', ' ').replace('/', ' ')}"
            self.bank.append(
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
                continue  # this customer will pay it together with the next invoice
            by_customer.setdefault(r["invoice"]["customer_id"], []).append(r)
        for customer_id, group in sorted(by_customer.items()):
            for r in group:
                r["paid"] = True
            party = self.parties[customer_id]
            numbers = " ".join(r["invoice"]["number"] for r in group)
            # Some customers write the invoice numbers in the transfer, some only their name.
            narration = f"IBFT FROM {party['name'].upper()}" + (
                f" {numbers}" if rng.randint(1, 100) <= 70 else ""
            )
            self.bank.append(
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

    def _recurring(self, day: date, rng) -> None:
        rec = self.cfg["recurring"]
        mon = day.strftime("%b-%Y").upper()
        if day == core.nth_business_day_of_month(day.year, day.month, rec["payroll_day"]):
            self.bank.append(
                BankTxn(
                    day,
                    f"SALARY BULK TRF {mon}",
                    f"SAL{day.strftime('%y%m')}",
                    -rec["payroll_minor"],
                    "payroll",
                )
            )
        if day == core.on_or_before_business_day(date(day.year, day.month, rec["rent_day"])):
            for b in self.cfg["branches"]:
                self.bank.append(
                    BankTxn(
                        day,
                        f"RENT {mon} {b['id']}",
                        f"RNT{day.strftime('%y%m')}{b['id']}",
                        -b["rent_minor"],
                        "rent",
                        party=b["landlord"],
                    )
                )
        if day == core.on_or_before_business_day(date(day.year, day.month, rec["loan_day"])):
            first = date.fromisoformat(rec["loan_first_instalment"])
            number = (day.year - first.year) * 12 + day.month - first.month + 1
            if 1 <= number <= rec["loan_instalments"]:
                self.bank.append(
                    BankTxn(
                        day,
                        f"LOAN INSTALMENT {number:02d}/{rec['loan_instalments']}",
                        f"LN{day.strftime('%y%m')}",
                        -rec["loan_instalment_minor"],
                        "loan",
                        party="pty_005",
                    )
                )
        if day == core.on_or_before_business_day(date(day.year, day.month, rec["electricity_day"])):
            low, high = rec["electricity_range_minor"]
            self.bank.append(
                BankTxn(
                    day,
                    f"ELECTRICITY BILL {mon}",
                    f"EL{day.strftime('%y%m')}",
                    -rng.randint(low // 100, high // 100) * 100,
                    "utilities",
                    party="pty_003",
                )
            )
        if day == core.on_or_before_business_day(date(day.year, day.month, rec["gas_day"])):
            low, high = rec["gas_range_minor"]
            self.bank.append(
                BankTxn(
                    day,
                    f"GAS BILL {mon}",
                    f"GS{day.strftime('%y%m')}",
                    -rng.randint(low // 100, high // 100) * 100,
                    "utilities",
                    party="pty_004",
                )
            )
        if day == core.on_or_before_business_day(
            date(day.year, day.month, rec["bank_charges_day"])
        ):
            self.bank.append(
                BankTxn(
                    day,
                    f"BANK CHARGES {mon}",
                    f"BC{day.strftime('%y%m')}",
                    -rec["bank_charges_minor"],
                    "bank_charges",
                )
            )
        prev_year, prev_month = (day.year, day.month - 1) if day.month > 1 else (day.year - 1, 12)
        prev = f"{date(prev_year, prev_month, 1).strftime('%b-%Y').upper()}"
        if (
            day == core.nth_business_day_of_month(day.year, day.month, rec["mdr_day"])
            and (prev_year, prev_month) in self.mdr_base
        ):
            mdr = self.cfg["pos"]["mdr_bp"]
            fee = sum(
                core.div_half_up(amount * mdr[m], 10_000)
                for m, amount in sorted(self.mdr_base[(prev_year, prev_month)].items())
            )
            if fee:
                self.bank.append(
                    BankTxn(
                        day, f"MDR CHARGES {prev}", f"MDR{day.strftime('%y%m')}", -fee, "mdr_fees"
                    )
                )
        if day == core.on_or_before_business_day(date(day.year, day.month, rec["tax_day"])):
            net = self._sales_tax_due(prev_year, prev_month)
            if net > 0:
                self.bank.append(
                    BankTxn(
                        day,
                        f"FBR SALES TAX {prev}",
                        f"FBR{day.strftime('%y%m')}",
                        -net,
                        "tax",
                        party="pty_006",
                    )
                )

    def _sales_tax_due(self, year: int, month: int) -> int:
        prefix = f"{year:04d}-{month:02d}"
        output = sum(
            e["tax_minor"]
            for e in self.events
            if e["event"] in ("sale", "customer_invoice")
            and e["date"].startswith(prefix)
            and e.get("txn", "sale") != "void"
        )
        inputs = sum(
            b["tax"][0]["amount_minor"] for b in self.bills if b["issue_date"].startswith(prefix)
        )
        observed = {
            e["date"] for e in self.events if e["event"] == "sale" and e["date"].startswith(prefix)
        }
        if not observed:
            return 0
        # ASSUMPTION: a month only partly inside the generated period is scaled up to a full month.
        days_in_month = (core.add_months(date(year, month, 1), 1) - date(year, month, 1)).days
        return core.div_half_up((output - inputs) * days_in_month, len(observed))

    # ------------------------------------------------------------ run
    def run(self) -> Output:
        self.pending: list[dict] = []
        self.pending_cash: list[dict] = []
        self.receivables: list[dict] = []
        self.mdr_base: dict[tuple[int, int], dict[str, int]] = {}
        self.slip = 0
        receipt_seq = {r: 0 for b in self.cfg["branches"] for r in b["registers"]}
        recent: dict[str, list[dict]] = {b["id"]: [] for b in self.cfg["branches"]}
        purchasing_rng = core.stream(self.seed, "purchasing")
        pos_rng = core.stream(self.seed, "pos")
        b2b_rng = core.stream(self.seed, "b2b")
        bank_rng = core.stream(self.seed, "bank")
        self._opening_balances()
        for day in core.days(self.start, self.end):
            self._order_day(day, purchasing_rng)
            self._receive_goods(day, purchasing_rng)
            self._planted_resend(day)
            self._pos_day(day, pos_rng, receipt_seq, recent)
            self._invoice_day(day, b2b_rng)
            if core.is_business_day(day):
                self._settle(day)
                self._pay_suppliers(day)
                self._collect_receivables(day, bank_rng)
                self._recurring(day, bank_rng)
        return self._finish()

    def _opening_balances(self) -> None:
        bank_cfg, rec = self.cfg["bank"], self.cfg["recurring"]
        inventory = sum(
            it["opening_stock_qty"] * it["unit_cost_minor"] for it in self.items.values()
        )
        floats = self.cfg["pos"]["opening_float_minor"] * sum(
            len(b["registers"]) for b in self.cfg["branches"]
        )
        loan = rec["loan_outstanding_principal_minor"]
        cash = bank_cfg["opening_balance_minor"]
        equity = cash + floats + inventory - loan
        lines = [
            {"account": "1000", "debit_minor": cash, "credit_minor": 0},
            {"account": "1010", "debit_minor": floats, "credit_minor": 0},
            {"account": "1200", "debit_minor": inventory, "credit_minor": 0},
            {"account": "2200", "debit_minor": 0, "credit_minor": loan},
            {"account": "3000", "debit_minor": 0, "credit_minor": equity},
        ]
        moment = core.local_time(self.start, 5 * 60, 0, 0)
        self._event(
            "journal_adjustment",
            moment,
            self.start,
            "manual",
            "opening_balances",
            {"lines": lines, "reason": "opening_balances", "approver": "owner"},
        )

    # ------------------------------------------------------------ outputs
    def _finish(self) -> Output:
        t = self.cfg["tenant"]
        order = {"credit": 0, "debit": 1}
        self.bank.sort(
            key=lambda b: (
                b.posted_on,
                order["credit" if b.amount_minor > 0 else "debit"],
                b.narration,
                b.reference,
            )
        )
        balance = self.cfg["bank"]["opening_balance_minor"]
        bank_rows, matches, unmatched = [], [], []
        for line_no, txn in enumerate(self.bank, start=1):
            balance += txn.amount_minor
            if balance < 0:
                raise RuntimeError(
                    f"bank balance went negative on {txn.posted_on}; raise opening_balance_minor"
                )
            key = f"{self.own_iban}#{line_no}"
            moment = core.local_time(txn.posted_on, 0, 0, 0)
            row = {
                "account_iban": self.own_iban,
                "line_no": line_no,
                "posted_on": txn.posted_on.isoformat(),
                "value_date": txn.posted_on.isoformat(),
                "narration": txn.narration,
                "reference": txn.reference,
                "amount_minor": txn.amount_minor,
                "balance_minor": balance,
                "currency": self.currency,
            }
            bank_rows.append(row)
            bank_line_id = core.source_ulid("bln", moment, self.tenant_id, "bank_statement", key)
            self._event(
                "bank_line",
                moment,
                txn.posted_on,
                "bank_statement",
                key,
                {
                    "bank_line_id": bank_line_id,
                    "account_iban": self.own_iban,
                    "line_no": line_no,
                    "narration": txn.narration,
                    "reference": txn.reference,
                    "amount_minor": txn.amount_minor,
                    "balance_minor": balance,
                },
                {"file": "bank_statement.csv", "row": line_no},
            )
            if txn.event_ids:
                matches.append(
                    {
                        "bank_line_id": bank_line_id,
                        "line_no": line_no,
                        "kind": txn.kind,
                        "event_ids": txn.event_ids,
                        **txn.extra,
                    }
                )
            else:
                unmatched.append(
                    {"bank_line_id": bank_line_id, "line_no": line_no, "category": txn.kind}
                )
        self.events.sort(key=lambda e: (e["occurred_at"], e["id"]))
        for po in self.pos:
            po.pop("_forced", None)
        for bill in self.bills:
            bill.pop("_paid", None)
        events_by_key = {(e["event"], e["source"]["key"]): e["id"] for e in self.events}
        tenant = {
            "synthetic": True,
            "id": self.tenant_id,
            "name": t["name"],
            "country": t["country"],
            "currency": self.currency,
            "minor_unit": t["minor_unit"],
            "framework": t["framework"],
            "fiscal_year_start_month": t["fiscal_year_start_month"],
            "timezone": t["timezone"],
            "as_of": self.end.isoformat(),
            "period": {"start": self.start.isoformat(), "end": self.end.isoformat()},
            "branches": [
                {
                    "id": b["id"],
                    "name": b["name"],
                    "registers": b["registers"],
                    "card_mid": b["card_mid"],
                }
                for b in self.cfg["branches"]
            ],
            "bank_accounts": [
                {
                    "iban": self.own_iban,
                    "name": self.cfg["bank"]["name"],
                    "opening_balance_minor": self.cfg["bank"]["opening_balance_minor"],
                }
            ],
            "policies": self.cfg["policies"],
            "country_pack_draft": self.cfg["country_pack_draft"],
        }
        mandates = self.mandates
        return Output(
            tenant=tenant,
            mandates=mandates,
            accounts=self.cfg["chart"]["accounts"],
            parties=list(self.parties.values()),
            items=list(self.items.values()),
            purchase_orders=self.pos,
            goods_received=self.grns,
            bills=self.bills,
            documents=self.documents,
            invoices=self.invoices,
            bank_rows=bank_rows,
            pos_rows=self.pos_rows,
            z_rows=self.z_rows,
            events=self.events,
            answer_key=self._answer_key(matches, unmatched, events_by_key, mandates),
        )

    def _answer_key(self, matches, unmatched, events_by_key, mandates) -> dict:
        demo = self.cfg.get("demo", {})
        scenarios, planted = [], set()
        if "duplicate_bill" in demo:
            d = demo["duplicate_bill"]
            planted |= {d["resend_bill_id"]}
            scenarios.append(
                {
                    "id": "DEMO-1",
                    "rules": ["G-03", "G-05", "G-12"],
                    "expected_outcome": "block",
                    "refs": {
                        "bill_ids": [d["resend_bill_id"], d["original_bill_id"]],
                        "document_ids": [d["resend_document_id"], d["original_document_id"]],
                        "party_ids": [d["supplier"]],
                        "event_ids": [
                            events_by_key[("purchase_bill", d["resend_bill_id"])],
                            events_by_key[("purchase_bill", d["original_bill_id"])],
                            events_by_key[
                                (
                                    "bank_detail_change",
                                    f"bdc:{d['supplier']}:{d['bank_change_at'][:10]}",
                                )
                            ],
                        ],
                    },
                    "also_fires": self._also_fires_cap(
                        events_by_key, d["resend_bill_id"], mandates
                    ),
                    "note": (
                        f"{d['resend_number']} re-sends {d['original_number']} ({d['original_bill_id']}), paid on "
                        f"{d['original_due_date']}; {d['supplier']} changed its bank account on {d['bank_change_at'][:10]} "
                        f"(confirmed by {d['bank_change_confirmed_via']} only); the bill presses for urgent payment."
                    ),
                }
            )
        if "over_cap_bill" in demo:
            d = demo["over_cap_bill"]
            bill = next(b for b in self.bills if b["bill_id"] == d["bill_id"])
            cap = next(m["per_payment_cap_minor"] for m in mandates if m["agent"] == "treasurer")
            planted.add(d["bill_id"])
            scenarios.append(
                {
                    "id": "S-01",
                    "rules": ["G-01"],
                    "expected_outcome": "escalate",
                    "refs": {
                        "bill_ids": [d["bill_id"]],
                        "document_ids": [d["document_id"]],
                        "party_ids": [d["supplier"]],
                        "event_ids": [events_by_key[("purchase_bill", d["bill_id"])]],
                    },
                    "note": f"Clean bill of {bill['total_minor']} minor, above the treasurer cap of {cap}; owner approves by phone.",
                }
            )
        dup = demo.get("duplicate_bill", {})
        clean = sorted(
            b["bill_id"]
            for b in self.bills
            if b["bill_id"] not in planted and b["bill_id"] != dup.get("original_bill_id")
        )
        return {
            "synthetic": True,
            "tenant_id": self.tenant_id,
            "seed": self.seed,
            "as_of": self.end.isoformat(),
            "generator_version": GENERATOR_VERSION,
            "scenarios": scenarios,
            "matches": matches,
            "unmatched_bank_lines": unmatched,
            "clean_bill_ids": clean,
            "open_bill_ids": sorted(
                b["bill_id"]
                for b in self.bills
                if b["bill_id"] in self.unpaid_bill_ids or b["due_date"] > self.end.isoformat()
            ),
            "other_lanes": {},
            "notes": "v0 (D2a): demo threads only. D2 adds S-01..S-12 in full, the other lanes' truths and held-out weeks.",
        }

    def _also_fires_cap(self, events_by_key, bill_id: str, mandates: list[dict]) -> list[str]:
        bill = next(b for b in self.bills if b["bill_id"] == bill_id)
        cap = next(m["per_payment_cap_minor"] for m in mandates if m["agent"] == "treasurer")
        return ["G-01"] if bill["total_minor"] > cap else []


def generate(config: dict, seed: int, months: int, mandates: list[dict]) -> Output:
    return Simulation(config, seed, months, mandates).run()
