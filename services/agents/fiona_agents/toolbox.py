"""Each agent's tools: what it may read and the only actions it may take.

Numbers come from tools (blueprint, Agents): every figure an agent sees is computed by the
engine, and the one tool that proposes a payment takes a bill ID, a date and the reasoning.
The amount, payee and evidence are filled in here from the ledger, so a model can never type
a number into a proposal. Tools return compact summaries to keep each agent's context small.

| Agent          | Reads                                                        | May propose      |
|----------------|--------------------------------------------------------------|------------------|
| controller     | reconciliation, bill duplicate checks, open bills            | nothing (report) |
| treasurer      | cash outlook, payment plan, its own open proposals           | payments         |
| cfo_strategist | health, ratios, stage, cash outlook, financing, debt/equity  | nothing (memo)   |
| growth_analyst | inventory, cash outlook, financing                           | nothing (memo)   |
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fiona_agents.engine import Engine

OPEN_STATUSES = {"submitted", "needs_owner", "cleared", "approved", "blocked"}


class ToolError(ValueError):
    """A refusal the model should read and act on (bad argument, duplicate, out of range)."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Engine, dict[str, Any]], Any]


def _money(m: dict[str, Any] | None) -> dict[str, Any] | None:
    """Minor units for exactness, plus a display string so the model never does the division."""
    if not m or m.get("minor") is None:
        return None
    minor, currency = int(m["minor"]), m.get("currency", "")
    sign = "-" if minor < 0 else ""
    major, cents = divmod(abs(minor), 100)
    return {
        "minor": minor,
        "currency": currency,
        "display": f"{sign}{currency} {major:,}.{cents:02d}",
    }


def _with_display(value: Any) -> Any:
    """Every money object anywhere in an engine response gets its display string."""
    if isinstance(value, dict):
        if set(value) >= {"minor", "currency"} and isinstance(value.get("minor"), int):
            return _money(value)
        return {k: _with_display(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_with_display(v) for v in value]
    return value


def _figure(f: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "metric": f.get("metric_id"),
        "label": f.get("label"),
        "status": f.get("status"),
    }
    if f.get("money"):
        out["value"] = _money(f["money"])
    elif f.get("value") is not None:
        value, unit = f["value"], f.get("unit")
        out["value"] = f"{value / 100:.2f}%" if unit == "bp" else f"{value} {unit or ''}".strip()
    return out


def _schema(
    properties: dict[str, Any] | None = None, required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------- shared reads


def cash_outlook(engine: Engine, _: dict[str, Any]) -> dict[str, Any]:
    d = engine.get("/v1/forecast/cash")
    return {
        "as_of": d.get("as_of"),
        "buffer": _money((d.get("buffer") or {}).get("money")),
        "opening": _money((d.get("opening_balance") or {}).get("money")),
        "lowest_closing": _money((d.get("lowest_closing") or {}).get("money")),
        "first_week_below_buffer": d.get("first_week_below_buffer"),
        "weeks": [
            {
                "week": w["week"],
                "from": w["start"],
                "to": w["end"],
                "inflows": _money(w.get("inflows")),
                "outflows": _money(w.get("outflows")),
                "closing": _money(w.get("closing")),
                "below_buffer": w.get("below_buffer"),
            }
            for w in d.get("weeks", [])
        ],
        "method": (d.get("method") or {}).get("name"),
        "data_gaps": [
            g.get("detail") or g.get("message") or str(g) for g in d.get("insufficient_data") or []
        ],
    }


def _open_proposals(engine: Engine, agent: str | None = None) -> list[dict[str, Any]]:
    items = engine.get("/v1/proposals").get("proposals", [])
    return [
        p
        for p in items
        if p.get("status") in OPEN_STATUSES and (agent is None or p.get("agent") == agent)
    ]


# ---------------------------------------------------------------- treasurer


def payment_plan(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
    within = int(args.get("due_within_days", 14))
    limit = int(args.get("limit", 25))
    if not 0 <= within <= 120 or not 1 <= limit <= 60:
        raise ToolError("due_within_days must be 0..120 and limit 1..60")
    d = engine.post("/v1/decisions/payment-timing", {})
    as_of = date.fromisoformat(d["as_of"])
    horizon = as_of + timedelta(days=within)
    proposed = {(p.get("payload") or {}).get("bill_id") for p in _open_proposals(engine)}
    bills = [
        b
        for b in d.get("bills", [])
        if date.fromisoformat(b["due_date"]) <= horizon and b["bill_id"] not in proposed
    ]
    bills.sort(key=lambda b: (b["due_date"], b["bill_id"]))
    return {
        "as_of": d["as_of"],
        "buffer": _money((d.get("buffer") or {}).get("money")),
        "cost_of_money": _figure(d["cost_of_money"]) if d.get("cost_of_money") else None,
        "open_bills_due_within_window": len(bills),
        "already_proposed_bills": len(proposed - {None}),
        "bills": [
            {
                "bill_id": b["bill_id"],
                "supplier": b.get("supplier_name"),
                "supplier_id": b.get("supplier_id"),
                "amount": _money(b.get("amount")),
                "issue_date": b.get("issue_date"),
                "due_date": b["due_date"],
                "overdue": date.fromisoformat(b["due_date"]) < as_of,
                "optimiser_action": b.get("action"),
                "optimiser_pay_on": b.get("pay_on"),
                "early_payment_terms": b.get("terms"),
                "figures": [_figure(f) for f in b.get("figures", [])],
            }
            for b in bills[:limit]
        ],
        "more_not_shown": max(0, len(bills) - limit),
    }


def my_open_proposals(engine: Engine, _: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposals": [
            {
                "id": p["id"],
                "status": p["status"],
                "summary": p.get("summary"),
                "amount": _money(p.get("amount")),
                "bill_id": (p.get("payload") or {}).get("bill_id"),
                "pay_on": (p.get("payload") or {}).get("pay_on"),
                "guardian_outcome": (p.get("verdict") or {}).get("outcome"),
            }
            for p in _open_proposals(engine, engine.agent)
        ]
    }


def _bill_document(engine: Engine, bill_id: str) -> str | None:
    """The source document the bill was taken in from, as the ledger recorded it."""
    return engine.get(f"/v1/bills/{bill_id}")["bill"].get("document_id")


def propose_payment(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
    bill_id = str(args.get("bill_id", ""))
    reasoning = str(args.get("reasoning", "")).strip()
    if not bill_id.startswith("bill_"):
        raise ToolError("bill_id must be an open bill's ID from get_payment_plan")
    if not 20 <= len(reasoning) <= 1_500:
        raise ToolError("reasoning must explain the decision in 20 to 1,500 characters")
    try:
        pay_on = date.fromisoformat(str(args.get("pay_on", "")))
    except ValueError as exc:
        raise ToolError("pay_on must be a date, YYYY-MM-DD") from exc

    plan = engine.post("/v1/decisions/payment-timing", {"bill_ids": [bill_id]})
    as_of = date.fromisoformat(plan["as_of"])
    bill = next((b for b in plan.get("bills", []) if b["bill_id"] == bill_id), None)
    if bill is None:
        raise ToolError(f"{bill_id} is not an open bill (already paid, or unknown)")
    if pay_on < as_of:
        raise ToolError(f"pay_on cannot be before today ({as_of})")
    if pay_on > date.fromisoformat(bill["due_date"]) + timedelta(days=30):
        raise ToolError("pay_on is more than 30 days after the due date; ask the owner instead")
    if any((p.get("payload") or {}).get("bill_id") == bill_id for p in _open_proposals(engine)):
        raise ToolError(f"{bill_id} already has an open proposal; do not propose it twice")

    evidence = [{"kind": "ledger_row", "ref": bill_id}]
    document_id = _bill_document(engine, bill_id)
    if document_id:
        evidence.append({"kind": "document", "ref": document_id})
    draft = {
        "agent": engine.agent,
        "type": "payment",
        "summary": f"Pay {bill.get('supplier_name') or bill['supplier_id']} for {bill_id} on {pay_on}",
        "amount": bill["amount"],
        "payload": {
            "payee_id": bill["supplier_id"],
            "bill_id": bill_id,
            "pay_on": pay_on.isoformat(),
            "channel": "wallet",
        },
        "evidence": evidence,
        "reasoning": reasoning,
    }
    res = engine.post("/v1/proposals", draft)
    proposal, verdict = res["proposal"], res["verdict"]
    return {
        "proposal_id": proposal["id"],
        "status": proposal["status"],
        "amount": _money(proposal.get("amount")),
        "guardian_outcome": verdict.get("outcome"),
        "guardian_concerns": [
            f"{c['rule']}: {c['detail']}"
            for c in verdict.get("checks", [])
            if c.get("outcome") != "approve"
        ],
        "note": "The owner decides every payment; nothing is paid until they approve it.",
    }


# ---------------------------------------------------------------- controller


def run_reconciliation(engine: Engine, _: dict[str, Any]) -> dict[str, Any]:
    r = engine.post("/v1/reconcile/run", {})
    return {
        k: r.get(k)
        for k in (
            "matched_bank_lines",
            "unmatched_bank_lines",
            "exact",
            "rule",
            "one_to_many",
            "fuzzy",
        )
    }


def reconciliation_findings(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit", 10))
    if not 1 <= limit <= 40:
        raise ToolError("limit must be 1..40")
    findings = engine.get("/v1/reconcile/findings").get("findings", [])
    return {
        "total": len(findings),
        "largest": [
            {
                "id": f["id"],
                "title": f.get("title"),
                "detail": f.get("detail"),
                "money_at_stake": _money(f.get("money_at_stake")),
                "evidence": [e.get("ref") for e in f.get("evidence", [])],
            }
            for f in findings[:limit]
        ],
    }


def open_bills(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
    days = int(args.get("issued_within_days", 14))
    if not 1 <= days <= 120:
        raise ToolError("issued_within_days must be 1..120")
    d = engine.post("/v1/decisions/payment-timing", {})
    since = date.fromisoformat(d["as_of"]) - timedelta(days=days)
    recent = [b for b in d.get("bills", []) if date.fromisoformat(b["issue_date"]) >= since]
    return {
        "as_of": d["as_of"],
        "open_bills_total": len(d.get("bills", [])),
        "issued_recently": [
            {
                "bill_id": b["bill_id"],
                "supplier": b.get("supplier_name"),
                "amount": _money(b.get("amount")),
                "issue_date": b["issue_date"],
                "due_date": b["due_date"],
            }
            for b in sorted(recent, key=lambda b: b["issue_date"], reverse=True)[:40]
        ],
    }


def check_bill(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
    bill_id = str(args.get("bill_id", ""))
    if not bill_id.startswith("bill_"):
        raise ToolError("bill_id must look like bill_…")
    check = engine.post("/v1/bills/check", {"bill_id": bill_id})["check"]
    return {
        "bill_id": bill_id,
        "rule": check.get("rule"),
        "result": check.get("result"),
        "detail": check.get("detail"),
    }


# ---------------------------------------------------------------- cfo / growth


def business_health(engine: Engine, _: dict[str, Any]) -> dict[str, Any]:
    stage = engine.get("/v1/stage").get("result") or {}
    health = engine.get("/v1/analysis/health").get("result") or {}
    ratios = engine.get("/v1/analysis/ratios").get("figures", [])
    return {
        "stage": {
            "stage": stage.get("stage"),
            "confidence": stage.get("confidence"),
            "pattern": stage.get("pattern_id"),
        },
        "health": {
            "overall": health.get("overall"),
            "dimensions": {
                k: {"band": v.get("band"), "reasons": v.get("reasons")}
                for k, v in (health.get("dimensions") or {}).items()
            },
        },
        "ratios": [_figure(f) for f in ratios if f.get("status") == "ok"][:20],
    }


def _amount(args: dict[str, Any], key: str = "amount_minor") -> dict[str, Any]:
    value = args.get(key)
    if not isinstance(value, int) or value <= 0:
        raise ToolError(f"{key} must be a positive integer in minor units (paisa)")
    return {"minor": value, "currency": args.get("currency", "PKR")}


def match_financing(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "amount": _amount(args),
        "purpose": args.get("purpose", "working_capital_seasonal"),
    }
    if args.get("pre_money_valuation_minor"):
        body["pre_money_valuation"] = _amount(args, "pre_money_valuation_minor")
    d = engine.post("/v1/financing/match", body)
    options = sorted(
        d.get("options", []), key=lambda o: (o.get("rank") is None, o.get("rank") or 0)
    )
    return {
        "as_of": d.get("as_of"),
        "options": [
            {
                "option_id": o.get("option_id"),
                "name": o.get("name"),
                "kind": o.get("kind"),
                "rank": o.get("rank"),
                "eligible": o.get("eligible"),
                "why": o.get("rank_reasons") or o.get("ineligible_reasons"),
                "figures": [_figure(f) for f in o.get("figures", [])][:6],
            }
            for o in options[:8]
        ],
        "missing_inputs": d.get("insufficient_data"),
    }


def compare_debt_equity(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
    body = {"amount": _amount(args), "purpose": str(args.get("purpose", "working capital"))[:200]}
    d = engine.post("/v1/decisions/debt-equity", body)
    return {
        "recommendation": d.get("recommendation"),
        "options": [
            {
                "option_id": o.get("option_id"),
                "label": o.get("label"),
                "eligible": o.get("eligible"),
                "figures": [_figure(f) for f in o.get("figures", [])][:8],
                "rule_checks": [
                    {
                        "rule": c.get("rule_id"),
                        "passed": c.get("passed"),
                        "description": c.get("description"),
                    }
                    for c in o.get("rule_checks", [])
                ],
            }
            for o in d.get("options", [])
        ],
        "missing_inputs": d.get("insufficient_data"),
    }


def inventory(engine: Engine, _: dict[str, Any]) -> dict[str, Any]:
    d = engine.get("/v1/inventory/analysis")
    keep = ("summary", "totals", "findings", "reorder", "slow_movers")
    return _with_display(
        {"as_of": d.get("as_of"), "window": d.get("window"), **{k: d[k] for k in keep if k in d}}
    )


# ---------------------------------------------------------------- registry

_CASH = Tool(
    "get_cash_outlook",
    "The 13-week cash forecast from the ledger: weekly inflows, outflows, closing cash, the owner's buffer and the first week below it.",
    _schema(),
    cash_outlook,
)
_FINANCING = Tool(
    "match_financing",
    "Rank financing options (Pakistan catalogue) for an amount and purpose: eligibility, cost, repayment capacity after borrowing.",
    _schema(
        {
            "amount_minor": {
                "type": "integer",
                "description": "Amount in paisa (PKR minor units).",
            },
            "purpose": {
                "type": "string",
                "enum": [
                    "working_capital_seasonal",
                    "working_capital_permanent",
                    "capex",
                    "refinancing",
                ],
            },
            "pre_money_valuation_minor": {
                "type": "integer",
                "description": "Optional, to size equity dilution.",
            },
        },
        ["amount_minor", "purpose"],
    ),
    match_financing,
)

TOOLBOXES: dict[str, list[Tool]] = {
    "treasurer": [
        _CASH,
        Tool(
            "get_payment_plan",
            "Open supplier bills due within a window that have no open proposal yet, with the payment-timing optimiser's suggestion for each.",
            _schema(
                {
                    "due_within_days": {"type": "integer", "minimum": 0, "maximum": 120},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 60},
                }
            ),
            payment_plan,
        ),
        Tool(
            "list_my_open_proposals",
            "Your payment proposals that are still open, with their status and Guardian outcome.",
            _schema(),
            my_open_proposals,
        ),
        Tool(
            "propose_payment",
            "Propose paying one open bill on a date. Amount and payee come from the ledger. The Guardian checks it and the owner decides; nothing is paid without the owner.",
            _schema(
                {
                    "bill_id": {"type": "string"},
                    "pay_on": {"type": "string", "description": "YYYY-MM-DD, today or later"},
                    "reasoning": {
                        "type": "string",
                        "description": "Why this bill, why this date, citing tool figures.",
                    },
                },
                ["bill_id", "pay_on", "reasoning"],
            ),
            propose_payment,
        ),
    ],
    "controller": [
        Tool(
            "run_reconciliation",
            "Match bank lines to ledger events (deterministic passes). Safe to repeat; human decisions are kept.",
            _schema(),
            run_reconciliation,
        ),
        Tool(
            "get_reconciliation_findings",
            "Unmatched bank lines, largest money at stake first.",
            _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 40}}),
            reconciliation_findings,
        ),
        Tool(
            "list_open_bills",
            "Open supplier bills issued recently.",
            _schema({"issued_within_days": {"type": "integer", "minimum": 1, "maximum": 120}}),
            open_bills,
        ),
        Tool(
            "check_bill_for_duplicates",
            "Guardian rule G-05 on one bill: is it a duplicate of an earlier one?",
            _schema({"bill_id": {"type": "string"}}, ["bill_id"]),
            check_bill,
        ),
    ],
    "cfo_strategist": [
        Tool(
            "get_business_health",
            "Lifecycle stage, health bands by dimension and key ratios from the ledger.",
            _schema(),
            business_health,
        ),
        _CASH,
        _FINANCING,
        Tool(
            "compare_debt_and_equity",
            "Compare borrowing with raising equity for an amount: cost, cash path, dilution and rule checks.",
            _schema(
                {"amount_minor": {"type": "integer"}, "purpose": {"type": "string"}},
                ["amount_minor", "purpose"],
            ),
            compare_debt_equity,
        ),
    ],
    "growth_analyst": [
        Tool(
            "get_inventory_analysis",
            "Stock analysis: ABC/XYZ classes, slow movers, reorder suggestions.",
            _schema(),
            inventory,
        ),
        _CASH,
        _FINANCING,
    ],
}
# In a council the Treasurer argues; it cannot propose anything from there.
TOOLBOXES["council_treasurer"] = [
    t for t in TOOLBOXES["treasurer"] if t.name != "propose_payment"
] + [_FINANCING]
