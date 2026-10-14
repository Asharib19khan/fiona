"""Plain-text rendering of supplier bills. ``document_sha256`` hashes exactly these bytes.

The text is deterministic and uses LF line endings on every platform. Planted and demo bills are
also rendered as one-page PDFs (render_bill_pdf); their PDF bytes are the hashed document.
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


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")


def render_bill_pdf(bill: dict, supplier: dict, buyer_name: str) -> bytes:
    """A one-page PDF of the same bill text (Courier). Deterministic: no dates, IDs or producer info."""
    lines = render_bill(bill, supplier, buyer_name).decode("utf-8").splitlines()
    stream = "\n".join(
        ["BT", "/F1 8.5 Tf", "10.5 TL", "36 812 Td"]
        + [f"({_pdf_escape(line)}) '" for line in lines]
        + ["ET"]
    ).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n% SYNTHETIC DOCUMENT - Fiona demo data\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)
