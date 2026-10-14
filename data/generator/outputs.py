"""Turn a finished simulation into the published fixtures, the answer key and the held-out truth.

Everything dated after `as_of` is cut from the published files. The held-out folder keeps the
13 weeks after `as_of` (cash outcomes and demand) for backtests (Y7) and the dip check (Y1).
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from data.generator import core, finance
from data.generator.build import GENERATOR_VERSION, _ts


def _money(minor: int) -> str:
    return "PKR " + core.fmt_money(minor)


def build_outputs(sim) -> dict:
    as_of, iso_as_of = sim.as_of, sim.as_of.isoformat()
    # ---------------------------------------------------------------- bank statement (full run)
    order = {True: 0, False: 1}
    sim.bank.sort(key=lambda b: (b.posted_on, order[b.amount_minor > 0], b.narration, b.reference))
    balance = sim.cfg["bank"]["opening_balance_minor"]
    bank_rows, matches, unmatched, daily_balance, holdout_lines = [], [], [], {}, []
    for line_no, txn in enumerate(sim.bank, start=1):
        balance += txn.amount_minor
        if balance < 0 and not os.environ.get("FIONA_GEN_TUNE"):
            raise RuntimeError(
                f"bank balance went negative on {txn.posted_on}; adjust the persona's cash levers"
            )
        daily_balance[txn.posted_on] = balance
        if txn.posted_on > as_of:
            holdout_lines.append((txn, balance))
            continue
        key = f"{sim.own_iban}#{line_no}"
        moment = core.local_time(txn.posted_on, 0, 0, 0)
        bank_rows.append(
            {
                "account_iban": sim.own_iban,
                "line_no": line_no,
                "posted_on": txn.posted_on.isoformat(),
                "value_date": txn.posted_on.isoformat(),
                "narration": txn.narration,
                "reference": txn.reference,
                "amount_minor": txn.amount_minor,
                "balance_minor": balance,
                "currency": sim.currency,
            }
        )
        bank_line_id = core.source_ulid("bln", moment, sim.tenant_id, "bank_statement", key)
        sim._event(
            "bank_line",
            moment,
            txn.posted_on,
            "bank_statement",
            key,
            {
                "bank_line_id": bank_line_id,
                "account_iban": sim.own_iban,
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
                {
                    "bank_line_id": bank_line_id,
                    "line_no": line_no,
                    "category": txn.kind,
                    **txn.extra,
                }
            )

    # ---------------------------------------------------------------- cutoff at as_of
    events = sorted(
        (e for e in sim.events if e["date"] <= iso_as_of), key=lambda e: (e["occurred_at"], e["id"])
    )
    event_ids = {e["id"] for e in events}
    for match in matches:
        if not set(match["event_ids"]) <= event_ids:
            raise RuntimeError(f"match cites events after as_of: {match}")
    bills = [b for b in sim.bills if sim._local_date(_ts(b["received_at"])) <= as_of]
    published_bills = []
    for bill in bills:
        clean = {k: v for k, v in bill.items() if not k.startswith("_")}
        published_bills.append(clean)
    grns = [g for g in sim.grns if g["received_on"] <= iso_as_of]
    received_po = {g["po_id"]: g for g in grns}
    pos_out = []
    for po in sim.pos:
        if po["ordered_on"] > iso_as_of:
            continue
        status = "open"
        if po["po_id"] in received_po:
            grn = received_po[po["po_id"]]
            short = any(
                g["qty_received"] < p["qty"] for g, p in zip(grn["lines"], po["lines"], strict=True)
            )
            status = "partially_received" if short else "received"
        pos_out.append({**{k: v for k, v in po.items() if not k.startswith("_")}, "status": status})
    documents = {b["document_path"]: sim.documents[b["document_path"]] for b in published_bills}
    invoices = [i for i in sim.invoices if i["issue_date"] <= iso_as_of]
    pos_rows = [r for r in sim.pos_rows if r["business_date"] <= iso_as_of]
    z_rows = [z for z in sim.z_rows if z["business_date"] <= iso_as_of]
    paid_by_as_of = {
        b["bill_id"] for b in sim.bills if b.get("_paid_on") and b["_paid_on"] <= iso_as_of
    }

    t = sim.cfg["tenant"]
    tenant = {
        "synthetic": True,
        "id": sim.tenant_id,
        "name": t["name"],
        "country": t["country"],
        "currency": sim.currency,
        "minor_unit": t["minor_unit"],
        "framework": t["framework"],
        "fiscal_year_start_month": t["fiscal_year_start_month"],
        "timezone": t["timezone"],
        "as_of": iso_as_of,
        "period": {"start": sim.start.isoformat(), "end": iso_as_of},
        "branches": [
            {
                "id": b["id"],
                "name": b["name"],
                "registers": b["registers"],
                "card_mid": b["card_mid"],
            }
            for b in sim.cfg["branches"]
        ],
        "bank_accounts": [
            {
                "iban": sim.own_iban,
                "name": sim.cfg["bank"]["name"],
                "opening_balance_minor": sim.cfg["bank"]["opening_balance_minor"],
            }
        ],
        "policies": sim.cfg["policies"],
        "country_pack_draft": sim.cfg["country_pack_draft"],
    }
    register = finance.asset_register(sim.cfg["fixed_assets"], sim.start, as_of)
    leases = [
        finance.lease_record(ls, finance.lease_payments(ls, sim.start, as_of, sim.cal))
        for ls in sim.cfg["leases"]
    ]
    opening = {
        "synthetic": True,
        "as_of": sim.start.isoformat(),
        "currency": sim.currency,
        "lines": sim.opening_lines,
        "note": "Opening trial balance at the start of the period; accounts in accounts.csv. Trade payables "
        "and receivables are nil (ASSUMPTION: June bills were settled by 30 June).",
    }

    files = {
        "tenant.json": tenant,
        "mandates.json": {
            "synthetic": True,
            "source": sim.mandates_source,
            "mandates": sim.mandates,
        },
        "accounts.csv": sim.cfg["chart"]["accounts"],
        "parties.csv": list(sim.parties.values()),
        "items.csv": list(sim.items.values()),
        "purchase_orders.json": {"synthetic": True, "purchase_orders": pos_out},
        "goods_received.json": {"synthetic": True, "goods_received": grns},
        "bills.json": {"synthetic": True, "bills": published_bills},
        "customer_invoices.json": {"synthetic": True, "invoices": invoices},
        "bank_statement.csv": bank_rows,
        "pos_sales.csv": pos_rows,
        "pos_z_reports.csv": z_rows,
        "events.jsonl": events,
        "loans.json": {"synthetic": True, "loans": [sim.loan]},
        "leases.json": {"synthetic": True, "leases": leases},
        "fixed_assets.json": {"synthetic": True, "assets": register},
        "payroll.json": {
            "synthetic": True,
            "months": [r for r in sim.payroll_rows if r["paid_on"] <= iso_as_of],
        },
        "opening_balances.json": opening,
        "nrv_assessments.json": {
            "synthetic": True,
            "assessments": [r for r in sim.nrv_records if r["assessment_date"] <= iso_as_of],
        },
    }
    holdout = _holdout(sim, daily_balance, holdout_lines, bank_rows)
    files["answer_key.json"] = _answer_key(
        sim,
        published_bills,
        paid_by_as_of,
        matches,
        unmatched,
        events,
        bank_rows,
        holdout,
        pos_rows,
    )
    return {"files": files, "documents": documents, "holdout": holdout}


# ---------------------------------------------------------------- held-out truth
def _weeks(as_of: date, n: int = 13) -> list[tuple[int, date, date]]:
    return [
        (w, as_of + timedelta(1 + 7 * (w - 1)), as_of + timedelta(7 * w)) for w in range(1, n + 1)
    ]


def _holdout(
    sim, daily_balance: dict[date, int], holdout_lines: list, bank_rows: list[dict]
) -> dict:
    closing = (
        bank_rows[-1]["balance_minor"] if bank_rows else sim.cfg["bank"]["opening_balance_minor"]
    )
    weeks = []
    for w, start, end in _weeks(sim.as_of):
        lines = [(t, b) for t, b in holdout_lines if start <= t.posted_on <= end]
        inflow = sum(t.amount_minor for t, _ in lines if t.amount_minor > 0)
        outflow = -sum(t.amount_minor for t, _ in lines if t.amount_minor < 0)
        opening = closing
        closing = opening + inflow - outflow
        low = min([b for _, b in lines] + [opening])
        weeks.append(
            {
                "w": w,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "opening_minor": opening,
                "inflows_minor": inflow,
                "outflows_minor": outflow,
                "closing_minor": closing,
                "lowest_balance_minor": low,
                "largest_outflows": [
                    {
                        "date": t.posted_on.isoformat(),
                        "narration": t.narration,
                        "amount_minor": -t.amount_minor,
                    }
                    for t, _ in sorted(
                        (x for x in lines if x[0].amount_minor < 0), key=lambda x: x[0].amount_minor
                    )[:6]
                ],
            }
        )
    demand = []
    for w, start, _end in _weeks(sim.as_of):
        for sku in sorted(sim.items):
            actual = sum(sim.demand_actual.get((start + timedelta(d), sku), 0) for d in range(7))
            expected = sum(sim._demand_x100(sku, start + timedelta(d)) for d in range(7)) // 100
            if actual or expected:
                demand.append(
                    {
                        "week": w,
                        "week_start": start.isoformat(),
                        "sku": sku,
                        "actual_units": actual,
                        "expected_units": expected,
                    }
                )
    return {"weeks": weeks, "demand": demand}


# ---------------------------------------------------------------- answer key
def _proposal(sim, spec: dict, bills: dict[str, dict], treasurer: dict) -> dict:
    agent = spec.get("agent", "treasurer")
    mandate = next((m for m in sim.mandates if m["agent"] == agent), treasurer)
    if "bill_id" in spec:
        bill = bills[spec["bill_id"]]
        payee, amount = bill["supplier_id"], bill["total_minor"]
        evidence = [
            {"kind": "ledger_row", "ref": bill["bill_id"]},
            {"kind": "document", "ref": bill["document_id"]},
        ]
        summary = f"Pay {bill['supplier']['name']} bill {bill['number']}"
        reasoning = f"Bill {bill['number']} for {_money(amount)} is due on {bill['due_date']}."
        category, bill_id = bill["category"], bill["bill_id"]
    else:
        payee, amount = spec["payee"], spec["amount_minor"]
        evidence, summary = spec.get("evidence", []), spec["summary"]
        reasoning = spec.get("reasoning", f"{summary}: {_money(amount)}.")
        category, bill_id = spec.get("category"), spec.get("bill_ref")
    return {
        "agent": agent,
        "type": "payment",
        "summary": summary[:200],
        "amount": {"minor": amount, "currency": sim.currency},
        "payload": {
            "payee_id": payee,
            "bill_id": bill_id,
            "pay_on": spec["pay_on"],
            "channel": "wallet",
            "category": category,
        },
        "evidence": evidence,
        "reasoning": reasoning,
        "mandate_ref": mandate["id"],
        "created_by": {"kind": "agent", "id": agent},
    }


def _answer_key(
    sim, bills: list[dict], paid: set[str], matches, unmatched, events, bank_rows, holdout, pos_rows
) -> dict:
    by_id = {b["bill_id"]: b for b in bills}
    treasurer = next(m for m in sim.mandates if m["agent"] == "treasurer")
    cap = treasurer["per_payment_cap_minor"]
    spec_by_scenario: dict[str, list[dict]] = {}
    for spec in sim.cfg.get("proposals", []):
        spec_by_scenario.setdefault(spec["scenario"], []).append(spec)
    plants_by_scenario: dict[str, list[dict]] = {}
    for plant in sim.cfg.get("plants", []):
        plants_by_scenario.setdefault(plant["scenario"], []).append(plant)
    events_by_key = {(e["event"], e["source"]["key"]): e["id"] for e in events}

    scenarios, problem_bills = [], set()
    for case in sim.scenarios["scenarios"] + sim.scenarios["controls"]:
        sid = case["id"]
        bill_ids = [p["bill_id"] for p in plants_by_scenario.get(sid, [])]
        if sid == "DEMO-1":
            demo = sim.cfg["demo"]["duplicate_bill"]
            bill_ids = [demo["resend_bill_id"], demo["original_bill_id"]]
        party_ids = sorted({by_id[b]["supplier_id"] for b in bill_ids if b in by_id})
        changes = [
            e for e in events if e["event"] == "bank_detail_change" and e.get("party") in party_ids
        ]
        refs = {
            "bill_ids": bill_ids,
            "document_ids": [by_id[b]["document_id"] for b in bill_ids if b in by_id],
            "party_ids": party_ids,
            "event_ids": [
                events_by_key[("purchase_bill", b)]
                for b in bill_ids
                if ("purchase_bill", b) in events_by_key
            ]
            + [e["id"] for e in changes],
        }
        entry = {
            "id": sid,
            "name": case.get("name"),
            "rules": case.get("rules", []),
            "expected_outcome": case.get("expected_outcome"),
            "refs": refs,
            "proposals": [
                {
                    "proposal": _proposal(sim, spec, by_id, treasurer),
                    **({"approval": spec["approval"]} if "approval" in spec else {}),
                }
                for spec in spec_by_scenario.get(sid, [])
            ],
        }
        if sid != "DEMO-1" and not sid.startswith("C-"):
            problem_bills |= {
                b for b in bill_ids if sid not in ("S-01", "S-02", "S-04", "S-08a", "S-08b", "S-10")
            }
        if sid == "DEMO-1":
            problem_bills.add(sim.cfg["demo"]["duplicate_bill"]["resend_bill_id"])
            totals = [by_id[b]["total_minor"] for b in bill_ids]
            entry["also_fires"] = ["G-01"] if max(totals) > cap else []
        scenarios.append(entry)
    for plant in sim.cfg.get("plants", []):
        if plant.get("role") == "duplicate":
            problem_bills.add(plant["bill_id"])
    # Suppliers whose bank change was never confirmed by phone make all their open bills fail G-03.
    unconfirmed = {
        c["supplier"] for c in sim.cfg.get("bank_changes", []) if c["confirmed_via"] != "phone"
    }
    open_ids = sorted(b["bill_id"] for b in bills if b["bill_id"] not in paid)
    clean = sorted(
        b["bill_id"]
        for b in bills
        if b["bill_id"] not in problem_bills
        and not (b["supplier_id"] in unconfirmed and b["bill_id"] in open_ids)
        and b["supplier_id"] not in {"sup_013", "sup_018"}
    )
    stock_bills = [b for b in bills if b["category"] == "inventory_supplier"]
    within_cap = sum(1 for b in stock_bills if b["total_minor"] <= cap)
    return {
        "synthetic": True,
        "tenant_id": sim.tenant_id,
        "seed": sim.seed,
        "as_of": sim.as_of.isoformat(),
        "generator_version": GENERATOR_VERSION,
        "scenario_source": "rulebook/scenarios.yaml",
        "scenarios": scenarios,
        "matches": matches,
        "unmatched_bank_lines": unmatched,
        "clean_bill_ids": clean,
        "open_bill_ids": open_ids,
        "bill_size": {
            "supplier_bills": len(stock_bills),
            "within_per_payment_cap": within_cap,
            "share_within_cap_bp": within_cap * 10_000 // max(len(stock_bills), 1),
            "cap_minor": cap,
        },
        "other_lanes": _other_lanes(sim, events, holdout, bank_rows, pos_rows),
        "notes": "Real totals that cannot be produced as subtotal + round_half_up(18 %) are 1 minor unit above the "
        "scenario figure (e.g. 14,950,001). Unit-test `given` values in scenarios.yaml are unaffected.",
    }


def _fiscal_years(sim) -> list[tuple[str, date, date]]:
    years, start = [], sim.start
    while core.add_months(start, 12) - timedelta(1) <= sim.as_of:
        end = core.add_months(start, 12) - timedelta(1)
        years.append((f"FY{end.year % 100:02d}", start, end))
        start = end + timedelta(1)
    return years


def _other_lanes(sim, events, holdout, bank_rows, pos_rows) -> dict:
    buffer = sim.cfg["policies"]["cash_buffer_minor"]
    weeks = holdout["weeks"]
    below = [w for w in weeks if w["closing_minor"] < buffer]
    low = min(weeks, key=lambda w: w["closing_minor"])
    open_bills = {}
    for bill in sim.bills:
        if bill["received_at"][:10] <= sim.as_of.isoformat() and not (
            bill.get("_paid_on") and bill["_paid_on"] <= sim.as_of.isoformat()
        ):
            due = sim.cal.on_or_before(date.fromisoformat(bill["due_date"]))
            for w in weeks:
                if (
                    w["start"] <= due.isoformat() <= w["end"]
                    and bill["bill_id"] not in sim.never_pay
                ):
                    open_bills.setdefault(w["w"], []).append(
                        {
                            "bill_id": bill["bill_id"],
                            "due": due.isoformat(),
                            "amount_minor": bill["total_minor"],
                        }
                    )
    cash_dip = {
        "week_definition": "week 1 starts the day after as_of; 7-day weeks (same as the Y1 forecast)",
        "buffer_minor": buffer,
        "first_week_below_buffer": below[0]["w"] if below else None,
        "week_of_min": low["w"],
        "min_closing_minor": low["closing_minor"],
        "shortfall_minor": max(0, buffer - low["closing_minor"]),
        "weekly_closing_minor": [
            {"w": w["w"], "start": w["start"], "closing_minor": w["closing_minor"]} for w in weeks
        ],
        "drivers_in_week_of_min": low["largest_outflows"],
        "open_bills_due_by_week": {str(k): v for k, v in sorted(open_bills.items())},
    }
    # Fiscal-year cash flows, direct method from the bank statement (truth for the Stage Detector).
    fy = []
    for label, start, end in _fiscal_years(sim):
        rows = [r for r in bank_rows if start.isoformat() <= r["posted_on"] <= end.isoformat()]
        kinds = {}
        for txn in sim.bank:
            if start <= txn.posted_on <= end:
                kinds.setdefault(txn.kind, []).append(txn)
        cfi = sum(t.amount_minor for t in kinds.get("capex", []))
        principal = sum(t.extra.get("principal_minor", 0) for t in kinds.get("loan", []))
        interest = sum(t.extra.get("interest_minor", 0) for t in kinds.get("loan", []))
        cff = (
            sum(t.amount_minor for t in kinds.get("loan_disbursement", []))
            + sum(t.amount_minor for t in kinds.get("drawings", []))
            - principal
        )
        total = sum(r["amount_minor"] for r in rows)
        cfo = total - cfi - cff
        revenue = sum(
            e["total_minor"] - e["tax_minor"]
            for e in sim.events
            if e["event"] == "sale"
            and e["txn"] != "void"
            and start.isoformat() <= e["date"] <= end.isoformat()
        )
        revenue += sum(
            e["subtotal_minor"]
            for e in sim.events
            if e["event"] == "customer_invoice"
            and start.isoformat() <= e["date"] <= end.isoformat()
        )
        fy.append(
            {
                "fiscal_year": label,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "revenue_ex_tax_minor": revenue,
                "cfo_minor": cfo,
                "cfi_minor": cfi,
                "cff_minor": cff,
                "interest_paid_minor": interest,
                "principal_repaid_minor": principal,
                "cfo_share_of_revenue_bp": cfo * 10_000 // max(revenue, 1),
            }
        )
    # Stock health at as_of: dead = stock on hand and nothing sold for 90 days; slow = > 120 days of cover.
    window = [sim.as_of - timedelta(d) for d in range(90)]
    stock = sim.stock_at_as_of
    dead, slow = [], []
    for sku in sorted(sim.items):
        sold = sum(sim.demand_actual.get((d, sku), 0) for d in window)
        if stock[sku] > 0 and sold == 0:
            dead.append({"sku": sku, "stock_on_hand": stock[sku]})
        elif sold and stock[sku] * 90 // sold > 120:
            slow.append(
                {
                    "sku": sku,
                    "stock_on_hand": stock[sku],
                    "units_sold_90d": sold,
                    "days_of_cover": stock[sku] * 90 // sold,
                }
            )
    anomalies = []
    for a in sim.cfg["pos"].get("anomalies", []):
        rows = [
            r
            for r in pos_rows
            if a["start"] <= r["business_date"] <= a["end"] and r["register_id"] == a["register"]
        ]
        receipts = {r["receipt_no"]: r["txn_type"] for r in rows if r["cashier_id"] == a["cashier"]}
        refunds = sum(1 for t in receipts.values() if t == "refund")
        anomalies.append({**a, "measured_receipts": len(receipts), "measured_refunds": refunds})
    seasons = [
        s
        for s in sim.cfg["calendar"]["seasons"]
        if s["start"] <= sim.as_of.isoformat()
        and s["start"] >= sim.start.isoformat()
        and s.get("traffic_pct", 100) > 100
    ]
    return {
        "cash_dip": cash_dip,
        "fiscal_year_cash_flows": fy,
        "dead_stock": dead,
        "slow_stock": slow,
        "nrv_events": sim.nrv_events,
        "pos_anomalies": anomalies,
        "seasonal_peaks": [
            {
                "name": s["name"],
                "start": s["start"],
                "end": s["end"],
                "traffic_pct": s["traffic_pct"],
            }
            for s in seasons
        ],
        "launch_lab_history_categories": ["SHL", "SCF", "LWN"],
        "loan_id": sim.loan["id"],
        "lease_ids": [ls["id"] for ls in sim.cfg["leases"]],
    }
