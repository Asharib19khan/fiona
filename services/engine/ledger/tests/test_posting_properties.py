"""Safety property (run on every build): debits equal credits for any event the ledger can hold."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from engine.ledger.posting import NARRATION_RULES, PostingContext, balanced, post_event

SKUS = ["KRT-M-BLU", "STS-L-PNK", "UNS-OS-GRN"]
CTX = PostingContext(
    item_costs=dict.fromkeys(SKUS, 180_000),
    landlords={"pty_001"},
    loan_schedule={1: (33_506_500, 18_125_000)},
)
money = st.integers(min_value=0, max_value=10**11)
qty = st.integers(min_value=1, max_value=50)


@st.composite
def sale(draw) -> tuple[str, dict]:
    txn = draw(st.sampled_from(["sale", "refund", "void"]))
    sign = -1 if txn == "refund" else 1
    lines = []
    for _ in range(draw(st.integers(1, 4))):
        total = draw(money)
        lines.append(
            {
                "item": draw(st.sampled_from(SKUS)),
                "qty": sign * draw(qty),
                "price_minor": total,
                "discount_minor": 0,
                "total_minor": sign * total,
                "tax_minor": sign * total * 1800 // 11800,
                "cost_minor": draw(money),
            }
        )
    method = draw(st.sampled_from(["cash", "card", "bank_qr", "raast", "jazzcash", "easypaisa"]))
    return "sale", {
        "txn": txn,
        "lines": lines,
        "total_minor": sum(ln["total_minor"] for ln in lines),
        "tax_minor": sum(ln["tax_minor"] for ln in lines),
        "payment": {"method": method},
    }


@st.composite
def purchase_bill(draw) -> tuple[str, dict]:
    lines = [
        {"sku": draw(st.sampled_from([*SKUS, None])), "line_total_minor": draw(money)}
        for _ in range(draw(st.integers(1, 4)))
    ]
    subtotal, tax = sum(ln["line_total_minor"] for ln in lines), draw(money)
    return "purchase_bill", {
        "party": draw(st.sampled_from(["sup_001", "pty_001"])),
        "lines": lines,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": subtotal + tax,
    }


@st.composite
def customer_invoice(draw) -> tuple[str, dict]:
    lines = [
        {"sku": draw(st.sampled_from(SKUS)), "qty": draw(qty)}
        for _ in range(draw(st.integers(1, 3)))
    ]
    subtotal, tax = draw(money), draw(money)
    return "customer_invoice", {
        "lines": lines,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": subtotal + tax,
    }


@st.composite
def journal(draw) -> tuple[str, dict]:
    amounts = draw(st.lists(money, min_size=1, max_size=5))
    lines = [{"account": "1000", "debit_minor": a, "credit_minor": 0} for a in amounts]
    lines.append({"account": "3000", "debit_minor": 0, "credit_minor": sum(amounts)})
    return "journal_adjustment", {"lines": lines, "reason": "test"}


@st.composite
def bank_line(draw) -> tuple[str, dict]:
    prefixes = [
        "POS CARD SETTL",
        "JAZZCASH MERCH SETTL",
        "CASH DEPOSIT",
        "IBFT FROM X",
        "IBFT TO X FA_006",
        "IBFT TO X",
        "SALARY BULK TRF",
        "RENT OCT",
        "GAS BILL",
        "LOAN INSTALMENT 01/36",
        "LOAN DISBURSEMENT",
        "FBR SALES TAX",
        "OWNER DRAWINGS",
        "MDR CHARGES",
        "SOMETHING UNKNOWN",
    ]
    narration = draw(st.sampled_from(prefixes)) + draw(st.text(alphabet="ABC 123", max_size=8))
    amount = draw(st.integers(min_value=-(10**11), max_value=10**11))
    return "bank_line", {"narration": narration, "amount_minor": amount}


@st.composite
def payment(draw) -> tuple[str, dict]:
    return "supplier_payment", {"amount_minor": draw(money)}


any_event = st.one_of(
    sale(), purchase_bill(), customer_invoice(), journal(), bank_line(), payment()
)


@settings(max_examples=500, deadline=None)
@given(st.lists(any_event, min_size=1, max_size=30))
def test_debits_equal_credits_for_any_sequence_of_events(events: list[tuple[str, dict]]) -> None:
    total_debits = total_credits = 0
    for kind, payload in events:
        lines = post_event(kind, payload, CTX)
        assert balanced(lines), (kind, payload, lines)
        for line in lines:
            assert line["debit_minor"] >= 0 and line["credit_minor"] >= 0
            assert not (line["debit_minor"] and line["credit_minor"])
            total_debits += line["debit_minor"]
            total_credits += line["credit_minor"]
    assert total_debits == total_credits


def test_every_narration_rule_targets_a_known_account_or_a_book_event() -> None:
    known = {
        "1010",
        "1020",
        "1030",
        "1100",
        "1350",
        "1500",
        "2100",
        "2200",
        "3100",
        "6000",
        "6100",
        "6200",
        "6250",
        "6270",
        "6300",
    }
    assert all(account is None or account in known for _, account in NARRATION_RULES)
