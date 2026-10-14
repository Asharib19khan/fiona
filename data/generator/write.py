"""Writers for the fixture files in FORMATS.md: UTF-8, LF, deterministic bytes."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

from data.generator.build import GENERATOR_VERSION

COLUMNS = {
    "parties.csv": [
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
    ],
    "items.csv": [
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
    ],
    "bank_statement.csv": [
        "account_iban",
        "line_no",
        "posted_on",
        "value_date",
        "narration",
        "reference",
        "amount_minor",
        "balance_minor",
        "currency",
    ],
    "pos_sales.csv": [
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
    ],
    "pos_z_reports.csv": [
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
    ],
    "accounts.csv": ["code", "name", "class", "neutral_class"],
    "demand_weekly.csv": ["week", "week_start", "sku", "actual_units", "expected_units"],
}
NOTICE = "SYNTHETIC DATA: invented business, people, suppliers and accounts. Not real."


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def csv_bytes(columns: list[str], rows: list) -> bytes:
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


def render_files(output: dict) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name, content in output["files"].items():
        if name.endswith(".csv"):
            files[name] = csv_bytes(COLUMNS[name], content)
        elif name.endswith(".jsonl"):
            files[name] = jsonl_bytes(content)
        else:
            files[name] = json_bytes(content)
    files.update(sorted(output["documents"].items()))
    return files


def render_holdout(output: dict) -> dict[str, bytes]:
    holdout = output["holdout"]
    return {
        "cash_weekly.json": json_bytes(
            {
                "synthetic": True,
                "notice": "HELD OUT: do not train or tune on this file.",
                "weeks": holdout["weeks"],
            }
        ),
        "demand_weekly.csv": csv_bytes(COLUMNS["demand_weekly.csv"], holdout["demand"]),
    }


def _write(target: Path, files: dict[str, bytes], manifest: dict) -> Path:
    if target.exists():
        if not (target / "manifest.json").exists():
            raise RuntimeError(
                f"{target} exists but was not written by the generator; refusing to replace it"
            )
        shutil.rmtree(target)
    manifest["files"] = {
        name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())
    }
    files = {**files, "manifest.json": json_bytes(manifest)}
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return target


def write_tenant(
    output: dict, root: Path, *, seed: int, persona: str, months: int
) -> tuple[Path, Path]:
    """Write the published fixtures to root/<tenant_id>/ and the held-out truth to root/holdout/<tenant_id>/."""
    tenant = output["files"]["tenant.json"]
    base = {
        "synthetic": True,
        "notice": NOTICE,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "persona": persona,
        "months": months,
        "tenant_id": tenant["id"],
        "as_of": tenant["as_of"],
        "period": tenant["period"],
    }
    published = _write(root / tenant["id"], render_files(output), dict(base))
    held_out = _write(
        root / "holdout" / tenant["id"],
        render_holdout(output),
        {**base, "held_out": "13 weeks after as_of; for backtests only"},
    )
    return published, held_out
