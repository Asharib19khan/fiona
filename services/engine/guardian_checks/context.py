"""CheckContext definition for Guardian checks (D5).

Provides a single typed Pydantic input container holding everything Guardian rules need:
proposal, mandate, tenant cash buffer, payee party, bill, prior bills, PO/GRN,
13-week forecast baseline, payments made today, actor IDs, and injected clock.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fiona_contracts.models import Mandate, Proposal, ProposalDraft


class BankDetailChangeContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    confirmed_via: str | None = None  # 'phone', 'email', 'in_person', 'none'
    confirmed_by: str | None = None
    old_iban: str | None = None
    new_iban: str | None = None
    occurred_at: datetime | str | None = None
    days_before_as_of: int | None = None


class PartyContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    party_id: str | None = None
    on_allow_list: bool = True
    bank_iban: str | None = None
    bank_account_changed_at: datetime | str | None = None
    latest_bank_detail_change: BankDetailChangeContext | None = None
    tax_id: str | None = None
    tax_id_type: str | None = None  # e.g. 'NTN'
    country_pack_pattern: str | None = None
    allow_list_changed_at: datetime | str | None = None
    insider_account_matches: bool = False


class PriorBillContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bill_id: str | None = None
    supplier_id: str | None = None
    number: str | None = None
    total_minor: int | None = None
    document_sha256: str | None = None
    issue_date: str | date | None = None
    grn_id: str | None = None
    paid: bool | None = None
    status: str | None = None


class BillLineContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str | None = None
    item: str | None = None
    qty: int | None = None
    unit_price_minor: int | None = None
    unit_cost_minor: int | None = None
    discount_minor: int = 0
    total_minor: int | None = None
    tax_minor: int | None = None


class TaxLineContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str | None = None
    rate_bp: int | None = None
    amount_minor: int | None = None
    base_minor: int | None = None


class BillContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bill_id: str | None = None
    supplier_id: str | None = None
    number: str | None = None
    subtotal_minor: int | None = None
    total_minor: int | None = None
    stated_tax_minor: int | None = None
    tax_rate_bp: int | None = None
    lines: list[BillLineContext] = Field(default_factory=list)
    tax_lines: list[TaxLineContext] = Field(default_factory=list)
    document_sha256: str | None = None
    po_number: str | None = None
    po_id: str | None = None
    grn_id: str | None = None
    category: str | None = None
    contract_ref: str | None = None
    due_date: str | date | None = None
    issue_date: str | date | None = None
    created_by: str | None = None
    approved_by: str | None = None
    supplier_bank_iban: str | None = None
    supplier_tax_id: str | None = None
    notes: str | None = None
    in_baseline_week: int | None = None
    outstanding_balance_minor: int | None = None
    is_partial_payment: bool = False


class POLineContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str | None = None
    item: str | None = None
    qty: int = 0
    unit_cost_minor: int = 0
    unit_price_minor: int | None = None


class POContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    number: str | None = None
    lines: list[POLineContext] = Field(default_factory=list)


class GRNLineContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str | None = None
    item: str | None = None
    qty_received: int = 0
    qty: int | None = None


class GRNContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    po_id: str | None = None
    lines: list[GRNLineContext] = Field(default_factory=list)


class ForecastWeek(BaseModel):
    model_config = ConfigDict(extra="ignore")
    w: int
    start: str
    closing_minor: int


class ForecastContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    as_of: datetime | str | None = None
    weeks: list[ForecastWeek] = Field(default_factory=list)
    created_at: datetime | str | None = None


class JournalLineContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    account: str
    debit_minor: int = 0
    credit_minor: int = 0
    memo: str | None = None


class CheckContext(BaseModel):
    """Unified typed input context for all deterministic Guardian checks."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    proposal: Proposal | ProposalDraft | dict[str, Any]
    mandate: Mandate | dict[str, Any] | None = None
    buffer_minor: int = 200000000  # Default PKR 2,000,000 from tenant policy
    currency: str = "PKR"

    payee: PartyContext | None = None
    bill: BillContext | None = None
    prior_bills: list[PriorBillContext] = Field(default_factory=list)

    po: POContext | None = None
    grn: GRNContext | None = None
    forecast: ForecastContext | None = None

    paid_today_minor: int = 0
    proposer_id: str | None = None
    approver_id: str | None = None
    bill_created_by: str | None = None
    single_person_business: bool = False

    now: datetime | str

    journal_lines: list[JournalLineContext] = Field(default_factory=list)
    bank_balance_as_of: datetime | str | None = None
    extraction_confidence: dict[str, str] = Field(default_factory=dict)
    party_record_version: int | None = None
    enable_proposed: bool = False

    def get_proposal_id(self) -> str:
        p = self.proposal
        if isinstance(p, dict):
            return str(p.get("id", "prop_unknown"))
        if hasattr(p, "root"):
            return str(getattr(p.root, "id", "prop_unknown"))
        return str(getattr(p, "id", "prop_unknown"))

    def get_action_type(self) -> str:
        p = self.proposal
        if isinstance(p, dict):
            return str(p.get("type", ""))
        if hasattr(p, "root"):
            return str(getattr(p.root, "type", ""))
        return str(getattr(p, "type", ""))

    def get_agent(self) -> str:
        p = self.proposal
        if isinstance(p, dict):
            return str(p.get("agent", ""))
        if hasattr(p, "root"):
            return str(getattr(p.root, "agent", ""))
        return str(getattr(p, "agent", ""))

    def get_amount_minor(self) -> int | None:
        p = self.proposal
        if isinstance(p, dict):
            if "amount_minor" in p:
                return int(p["amount_minor"])
            amt = p.get("amount")
            if isinstance(amt, dict) and "minor" in amt:
                return int(amt["minor"])
            payload = p.get("payload")
            if isinstance(payload, dict) and "amount_minor" in payload:
                return int(payload["amount_minor"])
            return None
        # Pydantic contract
        target = p.root if hasattr(p, "root") else p
        if hasattr(target, "amount") and target.amount is not None:
            return int(target.amount.minor)
        if hasattr(target, "amount_minor") and target.amount_minor is not None:
            return int(target.amount_minor)
        payload = getattr(target, "payload", None)
        if payload is not None and hasattr(payload, "amount_minor"):
            val = payload.amount_minor
            if val is not None:
                return int(val)
        return None

    def get_currency(self) -> str:
        p = self.proposal
        if isinstance(p, dict):
            if p.get("currency"):
                return str(p["currency"])
            amt = p.get("amount")
            if isinstance(amt, dict) and "currency" in amt:
                return str(amt["currency"])
            return self.currency
        target = p.root if hasattr(p, "root") else p
        if hasattr(target, "amount") and target.amount is not None:
            return str(target.amount.currency)
        if hasattr(target, "currency") and target.currency is not None:
            return str(target.currency)
        return self.currency

    def get_payee_id(self) -> str | None:
        p = self.proposal
        if isinstance(p, dict):
            if "payee_id" in p:
                return str(p["payee_id"])
            payload = p.get("payload")
            if isinstance(payload, dict) and "payee_id" in payload:
                return str(payload["payee_id"])
            return None
        target = p.root if hasattr(p, "root") else p
        payload = getattr(target, "payload", None)
        if payload is not None and hasattr(payload, "payee_id"):
            val = payload.payee_id
            if val is not None:
                return str(val)
        if hasattr(target, "payee_id"):
            val = target.payee_id
            if val is not None:
                return str(val)
        return None

    def get_to_iban(self) -> str | None:
        p = self.proposal
        if isinstance(p, dict):
            if "to_iban" in p:
                return str(p["to_iban"])
            payload = p.get("payload")
            if isinstance(payload, dict) and "to_iban" in payload:
                return str(payload["to_iban"])
            return None
        target = p.root if hasattr(p, "root") else p
        payload = getattr(target, "payload", None)
        if payload is not None and hasattr(payload, "to_iban"):
            val = payload.to_iban
            if val is not None:
                return str(val)
        return None

    def get_pay_on(self) -> str | None:
        p = self.proposal
        if isinstance(p, dict):
            if "pay_on" in p:
                return str(p["pay_on"])
            payload = p.get("payload")
            if isinstance(payload, dict) and "pay_on" in payload:
                return str(payload["pay_on"])
            return None
        target = p.root if hasattr(p, "root") else p
        payload = getattr(target, "payload", None)
        if payload is not None and hasattr(payload, "pay_on"):
            val = payload.pay_on
            if val is not None:
                return str(val)
        return None

    def get_category(self) -> str | None:
        p = self.proposal
        if isinstance(p, dict):
            if "category" in p:
                return str(p["category"])
            payload = p.get("payload")
            if isinstance(payload, dict) and "category" in payload:
                return str(payload["category"])
            return None
        target = p.root if hasattr(p, "root") else p
        payload = getattr(target, "payload", None)
        if payload is not None and hasattr(payload, "category"):
            val = payload.category
            if val is not None:
                return str(val)
        return None

    def get_evidence(self) -> list[dict[str, Any]]:
        p = self.proposal
        if isinstance(p, dict):
            ev = p.get("evidence", [])
            return [e if isinstance(e, dict) else e.model_dump() for e in ev]
        target = p.root if hasattr(p, "root") else p
        ev = getattr(target, "evidence", []) or []
        res = []
        for e in ev:
            if isinstance(e, dict):
                res.append(e)
            elif hasattr(e, "model_dump"):
                res.append(e.model_dump())
            elif hasattr(e, "__dict__"):
                res.append(dict(e.__dict__))
        return res

    def get_reasoning(self) -> str:
        p = self.proposal
        if isinstance(p, dict):
            return str(p.get("reasoning", ""))
        target = p.root if hasattr(p, "root") else p
        return str(getattr(target, "reasoning", ""))

    def get_now_dt(self) -> datetime:
        if isinstance(self.now, datetime):
            if self.now.tzinfo is None:
                return self.now.replace(tzinfo=UTC)
            return self.now
        # ISO string
        s = str(self.now)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
