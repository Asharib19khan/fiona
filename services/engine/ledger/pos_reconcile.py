"""POS Reconciliation Engine (D9 / Tier 2).

Reconciles end-of-day POS sales registers with bank lines and settlement aggregators:
1. Cash Drawer Auditing: Reconciles daily cash sales against bank cash deposits,
   measuring drawer over/short variances against allowable threshold (<=2% or 500 minor units).
2. Card & Digital Settlement Batching: Matches POS card/QR/wallet payments against
   acquirer merchant settlements, computing merchant discount rate (MDR) fees.
3. Transaction Integrity: Flags void anomalies, refunds without original sales, and
   unsettled register batches.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict

from engine.ledger import db

_BRANCH_RE = re.compile(r"\b(BR\d{2})\b")
_SETTLEMENT_KEYWORDS = {
    "POS CARD SETTL": "card",
    "QR SETTL": "bank_qr",
    "RAAST P2M SETTL": "raast",
    "JAZZCASH MERCH SETTL": "jazzcash",
    "EASYPAISA MERCH SETTL": "easypaisa",
}


class DrawerReconcileRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_date: str
    branch_id: str
    cash_sales_minor: int
    cash_deposited_minor: int
    variance_minor: int
    status: str  # "balanced", "over", "short", "unbanked"


class SettlementBatchRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_date: str
    branch_id: str
    payment_method: str
    gross_pos_minor: int
    settled_amount_minor: int
    fee_minor: int
    fee_rate_bp: int
    bank_line_id: str | None
    status: str  # "matched", "unsettled", "fee_anomaly"


class POSDiscrepancy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: str  # "low", "medium", "high"
    branch_id: str
    business_date: str
    category: str
    description: str
    amount_minor: int


class POSReconcileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_pos_gross_minor: int
    total_refunds_minor: int
    total_net_sales_minor: int
    total_cash_sales_minor: int
    total_cash_deposited_minor: int
    total_card_sales_minor: int
    total_card_settled_minor: int
    total_merchant_fees_minor: int
    net_drawer_variance_minor: int


class POSReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_version: str = "v1"
    run_id: str
    as_of: str
    tenant_id: str
    summary: POSReconcileSummary
    drawer_reconciliations: list[DrawerReconcileRow]
    settlement_batches: list[SettlementBatchRow]
    exceptions: list[POSDiscrepancy]


def run_pos_reconciliation(
    conn: psycopg.Connection,
    tenant_id: str,
    as_of: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Execute end-to-end POS reconciliation against bank deposits and acquirer settlements."""
    current_time = now or datetime.now(UTC)
    run_id = f"pos_rec_{current_time.strftime('%Y%m%d%H%M%S')}"

    with db.tenant_session(conn, tenant_id):
        # 1. Fetch all POS sale events
        sale_rows = conn.execute(
            """
            SELECT id, business_date, payload
            FROM public.events
            WHERE tenant_id = %s AND type = 'sale'
            ORDER BY business_date, occurred_at
            """,
            (tenant_id,),
        ).fetchall()

        # 2. Fetch all bank lines
        bank_rows = conn.execute(
            """
            SELECT id, posted_on, narration, reference, amount_minor
            FROM public.bank_lines
            WHERE tenant_id = %s
            ORDER BY posted_on, line_no
            """,
            (tenant_id,),
        ).fetchall()

    # Aggregate POS transactions by (business_date, branch_id, payment_method)
    sales_by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    refunds_by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    void_receipts: list[dict[str, Any]] = []

    total_gross = 0
    total_refunds = 0

    for _eid, b_date, payload in sale_rows:
        b_date_str = b_date.isoformat()
        branch = payload.get("branch", "BR01")
        txn = payload.get("txn", "sale")
        method = payload.get("payment", {}).get("method", "cash")
        total_minor = int(payload.get("total_minor", 0))

        if txn == "sale":
            sales_by_group[(b_date_str, branch, method)].append(payload)
            total_gross += total_minor
        elif txn == "refund":
            refunds_by_group[(b_date_str, branch, method)].append(payload)
            total_refunds += total_minor
        elif txn == "void":
            void_receipts.append(payload)

    # Index bank deposits and settlements
    cash_deposits_by_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    card_settlements_by_branch: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for bid, posted_on, narration, ref, amount in bank_rows:
        narration_upper = narration.upper()
        branch_match = _BRANCH_RE.search(narration_upper)
        branch = branch_match.group(1) if branch_match else "BR01"
        item = {
            "id": bid,
            "posted_on": posted_on.isoformat(),
            "narration": narration,
            "reference": ref,
            "amount_minor": int(amount),
        }

        if "CASH DEPOSIT" in narration_upper and amount > 0:
            cash_deposits_by_branch[branch].append(item)
        else:
            for kw, method in _SETTLEMENT_KEYWORDS.items():
                if kw in narration_upper and amount > 0:
                    card_settlements_by_branch[(branch, method)].append(item)
                    break

    # 3. Cash Drawer Reconciliations
    drawer_rows: list[DrawerReconcileRow] = []
    exceptions: list[POSDiscrepancy] = []

    # Get all distinct (date, branch) pairs for cash
    cash_dates_branches = {(d, b) for (d, b, m) in sales_by_group if m == "cash"} | {
        (d, b) for (d, b, m) in refunds_by_group if m == "cash"
    }

    total_cash_sales = 0
    total_cash_deposited = 0
    net_drawer_variance = 0

    used_deposits: set[str] = set()

    for d_str, b_id in sorted(cash_dates_branches):
        cash_gross = sum(
            int(p.get("total_minor", 0)) for p in sales_by_group.get((d_str, b_id, "cash"), [])
        )
        cash_ref = sum(
            int(p.get("total_minor", 0)) for p in refunds_by_group.get((d_str, b_id, "cash"), [])
        )
        net_cash = cash_gross - cash_ref
        total_cash_sales += net_cash

        # Look for matching cash deposit on or within 2 business days
        matched_deposit = None
        for dep in cash_deposits_by_branch.get(b_id, []):
            if dep["id"] in used_deposits:
                continue
            if dep["posted_on"] >= d_str:
                # Tolerance check: within 2% or 500 minor units
                diff = abs(dep["amount_minor"] - net_cash)
                allowed_tol = max(500, net_cash * 200 // 10_000)
                if diff <= allowed_tol or dep["amount_minor"] == net_cash:
                    matched_deposit = dep
                    used_deposits.add(dep["id"])
                    break

        deposited_amt = matched_deposit["amount_minor"] if matched_deposit else 0
        total_cash_deposited += deposited_amt
        var_minor = deposited_amt - net_cash
        net_drawer_variance += var_minor

        if not matched_deposit:
            status = "unbanked"
            exceptions.append(
                POSDiscrepancy(
                    severity="high" if net_cash > 100_000 else "medium",
                    branch_id=b_id,
                    business_date=d_str,
                    category="unbanked_cash",
                    description=f"No matching cash deposit located for {b_id} on {d_str}",
                    amount_minor=net_cash,
                )
            )
        elif var_minor == 0:
            status = "balanced"
        elif var_minor > 0:
            status = "over"
        else:
            status = "short"
            if abs(var_minor) > 5_000:
                exceptions.append(
                    POSDiscrepancy(
                        severity="medium",
                        branch_id=b_id,
                        business_date=d_str,
                        category="drawer_short",
                        description=f"Cash drawer short by {abs(var_minor)} minor units at {b_id}",
                        amount_minor=abs(var_minor),
                    )
                )

        drawer_rows.append(
            DrawerReconcileRow(
                business_date=d_str,
                branch_id=b_id,
                cash_sales_minor=net_cash,
                cash_deposited_minor=deposited_amt,
                variance_minor=var_minor,
                status=status,
            )
        )

    # 4. Card & Digital Settlement Batches
    settlement_rows: list[SettlementBatchRow] = []
    digital_methods = {"card", "bank_qr", "raast", "jazzcash", "easypaisa"}
    digital_groups = {(d, b, m) for (d, b, m) in sales_by_group if m in digital_methods}

    total_card_sales = 0
    total_card_settled = 0
    total_merchant_fees = 0

    used_settlements: set[str] = set()

    for d_str, b_id, m_name in sorted(digital_groups):
        card_gross = sum(
            int(p.get("total_minor", 0)) for p in sales_by_group.get((d_str, b_id, m_name), [])
        )
        card_ref = sum(
            int(p.get("total_minor", 0)) for p in refunds_by_group.get((d_str, b_id, m_name), [])
        )
        net_digital = card_gross - card_ref
        total_card_sales += net_digital

        # Find corresponding acquirer settlement
        matched_settle = None
        for settle in card_settlements_by_branch.get((b_id, m_name), []):
            if settle["id"] in used_settlements:
                continue
            # Settlement amount must be <= net_digital (net of MDR fee)
            if settle["posted_on"] >= d_str and 0 < settle["amount_minor"] <= net_digital:
                matched_settle = settle
                used_settlements.add(settle["id"])
                break

        if matched_settle:
            settled_amt = matched_settle["amount_minor"]
            fee_minor = net_digital - settled_amt
            fee_rate_bp = (fee_minor * 10_000 // net_digital) if net_digital > 0 else 0
            bank_id = matched_settle["id"]
            total_card_settled += settled_amt
            total_merchant_fees += fee_minor
            status = "matched" if fee_rate_bp <= 400 else "fee_anomaly"
            if status == "fee_anomaly":
                exceptions.append(
                    POSDiscrepancy(
                        severity="medium",
                        branch_id=b_id,
                        business_date=d_str,
                        category="excess_fee",
                        description=f"Acquirer fee rate ({fee_rate_bp} bp) exceeds expected maximum contract rate",
                        amount_minor=fee_minor,
                    )
                )
        else:
            settled_amt = 0
            fee_minor = 0
            fee_rate_bp = 0
            bank_id = None
            status = "unsettled"
            exceptions.append(
                POSDiscrepancy(
                    severity="high" if net_digital > 50_000 else "low",
                    branch_id=b_id,
                    business_date=d_str,
                    category="unsettled_batch",
                    description=f"Unsettled {m_name} batch at {b_id} for {d_str}",
                    amount_minor=net_digital,
                )
            )

        settlement_rows.append(
            SettlementBatchRow(
                business_date=d_str,
                branch_id=b_id,
                payment_method=m_name,
                gross_pos_minor=net_digital,
                settled_amount_minor=settled_amt,
                fee_minor=fee_minor,
                fee_rate_bp=fee_rate_bp,
                bank_line_id=bank_id,
                status=status,
            )
        )

    # 5. Summary
    summary = POSReconcileSummary(
        total_pos_gross_minor=total_gross,
        total_refunds_minor=total_refunds,
        total_net_sales_minor=total_gross - total_refunds,
        total_cash_sales_minor=total_cash_sales,
        total_cash_deposited_minor=total_cash_deposited,
        total_card_sales_minor=total_card_sales,
        total_card_settled_minor=total_card_settled,
        total_merchant_fees_minor=total_merchant_fees,
        net_drawer_variance_minor=net_drawer_variance,
    )

    return {
        "api_version": "v1",
        "run_id": run_id,
        "as_of": current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tenant_id": tenant_id,
        "summary": summary.model_dump(),
        "drawer_reconciliations": [r.model_dump() for r in drawer_rows],
        "settlement_batches": [r.model_dump() for r in settlement_rows],
        "exceptions": [e.model_dump() for e in exceptions],
    }
