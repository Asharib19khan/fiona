"""Plain-text rendering of supplier bills. ``document_sha256`` hashes exactly these bytes.

The text is deterministic and uses LF line endings on every platform. PDF and photo renders of
about 20 bills arrive in D2.
"""

from __future__ import annotations

from data.generator.core import fmt_money

WIDTH = 72


def render_bill(bill: dict, supplier: dict, buyer_name: str) -> bytes:
    rule = "-" * WIDTH
    out = [
        "SYNTHETIC DOCUMENT - Fiona demo data",
        "=" * WIDTH,
        supplier["name"],
        f"{supplier['city']}, Pakistan    NTN: {bill['supplier']['tax_id']}",
        rule,
        "SALES TAX INVOICE",
        f"Invoice no: {bill['number']}",
        f"Date: {bill['issue_date']}    Due: {bill['due_date']}",
        f"Bill to: {buyer_name}",
        f"PO ref: {bill['po_number'] or '-'}",
        rule,
        f"{'Qty':>5}  {'Item / description':<38}{'Unit price':>12}{'Amount':>15}",
    ]
    for line in bill["lines"]:
        label = f"{line['sku'] or ''} {line['description']}".strip()[:38]
        out.append(
            f"{line['qty']:>5}  {label:<38}{fmt_money(line['unit_price_minor']):>12}{fmt_money(line['line_total_minor']):>15}"
        )
    out.append(rule)
    out.append(f"{'Subtotal ' + bill['currency']:>55}{fmt_money(bill['subtotal_minor']):>17}")
    for tax in bill["tax"]:
        rate = f"{tax['rate_bp'] // 100}.{tax['rate_bp'] % 100:02d}%"
        out.append(f"{tax['code'] + ' ' + rate:>55}{fmt_money(tax['amount_minor']):>17}")
    out.append(f"{'TOTAL ' + bill['currency']:>55}{fmt_money(bill['total_minor']):>17}")
    out.append(rule)
    out.append(f"Pay to IBAN: {bill['supplier']['bank_iban']}")
    if bill["notes"]:
        out.append("")
        out.append(bill["notes"])
    return ("\n".join(out) + "\n").encode("utf-8")
