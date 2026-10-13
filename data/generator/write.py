"""Writers for the fixture files in FORMATS.md: UTF-8, LF, deterministic bytes."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

from data.generator.build import GENERATOR_VERSION, Output

PARTY_COLUMNS = [
    "party_id",
    "kind",
    "code",
    "name",
    "tax_id",
    "tax_id_type",
    "bank_iban",
    "bank_account_changed_at",
    "on_allow_list",
    "payment_terms_days",
    "phone",
    "city",
]
ITEM_COLUMNS = [
    "sku",
    "name",
    "category",
    "size",
    "colour",
    "season",
    "unit_cost_minor",
    "price_minor",
    "currency",
    "opening_stock_qty",
    "reorder_level",
    "supplier_id",
    "lead_time_days",
    "launched_on",
]
BANK_COLUMNS = [
    "account_iban",
    "line_no",
    "posted_on",
    "value_date",
    "narration",
    "reference",
    "amount_minor",
    "balance_minor",
    "currency",
]
POS_COLUMNS = [
    "receipt_no",
    "line_no",
    "txn_type",
    "original_receipt_no",
    "occurred_at",
    "business_date",
    "branch_id",
    "register_id",
    "cashier_id",
    "customer_code",
    "sku",
    "qty",
    "unit_price_minor",
    "discount_minor",
    "line_total_minor",
    "tax_minor",
    "payment_method",
    "payment_status",
    "currency",
]
Z_COLUMNS = [
    "z_no",
    "business_date",
    "branch_id",
    "register_id",
    "opening_float_minor",
    "cash_sales_minor",
    "cash_refunds_minor",
    "expected_cash_minor",
    "counted_cash_minor",
    "over_short_minor",
    "card_total_minor",
    "bank_qr_total_minor",
    "raast_total_minor",
    "jazzcash_total_minor",
    "easypaisa_total_minor",
    "receipt_count",
    "refund_count",
    "void_count",
    "currency",
]
ACCOUNT_COLUMNS = ["code", "name", "class", "neutral_class"]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def csv_bytes(columns: list[str], rows: list[dict] | list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        values = row if isinstance(row, list) else [row.get(c) for c in columns]
        writer.writerow([_cell(v) for v in values])
    return buffer.getvalue().encode("utf-8")


def json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def jsonl_bytes(rows: list[dict]) -> bytes:
    return "".join(
        json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows
    ).encode("utf-8")


def render_files(out: Output, mandates_source: str) -> dict[str, bytes]:
    files = {
        "tenant.json": json_bytes(out.tenant),
        "mandates.json": json_bytes(
            {"synthetic": True, "source": mandates_source, "mandates": out.mandates}
        ),
        "accounts.csv": csv_bytes(ACCOUNT_COLUMNS, out.accounts),
        "parties.csv": csv_bytes(PARTY_COLUMNS, out.parties),
        "items.csv": csv_bytes(ITEM_COLUMNS, out.items),
        "purchase_orders.json": json_bytes(
            {"synthetic": True, "purchase_orders": out.purchase_orders}
        ),
        "goods_received.json": json_bytes(
            {"synthetic": True, "goods_received": out.goods_received}
        ),
        "bills.json": json_bytes({"synthetic": True, "bills": out.bills}),
        "customer_invoices.json": json_bytes({"synthetic": True, "invoices": out.invoices}),
        "bank_statement.csv": csv_bytes(BANK_COLUMNS, out.bank_rows),
        "pos_sales.csv": csv_bytes(POS_COLUMNS, out.pos_rows),
        "pos_z_reports.csv": csv_bytes(Z_COLUMNS, out.z_rows),
        "events.jsonl": jsonl_bytes(out.events),
        "answer_key.json": json_bytes(out.answer_key),
    }
    for doc_id, content in sorted(out.documents.items()):
        files[f"documents/{doc_id}.txt"] = content
    return files


def write_tenant(
    out: Output, root: Path, *, seed: int, persona: str, months: int, mandates_source: str
) -> Path:
    """Write one tenant's files into ``root/<tenant_id>/``, replacing a previous generation."""
    target = root / out.tenant["id"]
    if target.exists():
        if not (target / "manifest.json").exists():
            raise RuntimeError(
                f"{target} exists but was not written by the generator; refusing to replace it"
            )
        shutil.rmtree(target)
    files = render_files(out, mandates_source)
    manifest = {
        "synthetic": True,
        "notice": "SYNTHETIC DATA: invented business, people, suppliers and accounts. Not real.",
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "persona": persona,
        "months": months,
        "tenant_id": out.tenant["id"],
        "as_of": out.tenant["as_of"],
        "period": out.tenant["period"],
        "files": {
            name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())
        },
    }
    files["manifest.json"] = json_bytes(manifest)
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return target
