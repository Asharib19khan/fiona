"""The business's own figures that financing options are tested against.

Revenue and existing loan service come straight from the ledger. EBITDA is a STUB until the
statements engine (Abdullah lane, B5/Y2) exposes a forecast EBITDA: here it is the operating
cash flow before debt service, read off the bank statement and annualised, and every figure
built on it carries origin "stub". The DSCR itself is always computed by
engine.analysis.coverage, the one implementation every lane uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.forecast.cash.engine import forecast_cash
from engine.forecast.ledger_source import LedgerSnapshot

LOAN = re.compile(r"^LOAN INSTALMENT (\d+)/(\d+)")


@dataclass(frozen=True)
class BusinessFigures:
    currency: str
    country: str | None
    history_days: int
    revenue_annual_minor: int | None
    ebitda_next_12m_minor: int | None  # stub (see module docstring)
    existing_service_12m_minor: int
    existing_service_basis: str
    cash_lowest_closing_minor: int | None
    cash_lowest_week: int | None
    cash_buffer_minor: int | None
    has_b2b_receivables: bool
    forecast_run_id: str | None


def business_figures(snap: LedgerSnapshot) -> BusinessFigures:
    lines = snap.bank_lines
    days = (lines[-1].posted_on - lines[0].posted_on).days + 1 if lines else 0
    scale = 365 / days if days else 0.0

    revenue = round(sum(v for _, v in snap.sales) * scale) if snap.sales and days else None

    latest_loan = None
    for b in lines:
        m = LOAN.match(b.narration)
        if m and b.amount_minor < 0:
            latest_loan = (-b.amount_minor, int(m.group(1)), int(m.group(2)))
    if latest_loan:
        amount, n, total = latest_loan
        months = min(12, total - n)
        service = amount * months
        basis = (
            f"{months} remaining monthly instalments of the existing loan (last paid {n}/{total})"
        )
    else:
        service, basis = 0, "no loan instalments in the bank statement"

    operating = sum(b.amount_minor for b in lines if not LOAN.match(b.narration))
    ebitda = round(operating * scale) if days else None

    forecast = forecast_cash(snap) if lines else None
    lowest = min(forecast.weeks, key=lambda w: w.closing.minor) if forecast else None

    return BusinessFigures(
        currency=snap.currency,
        country=snap.country,
        history_days=days,
        revenue_annual_minor=revenue,
        ebitda_next_12m_minor=ebitda,
        existing_service_12m_minor=service,
        existing_service_basis=basis,
        cash_lowest_closing_minor=lowest.closing.minor if lowest else None,
        cash_lowest_week=lowest.week if lowest else None,
        cash_buffer_minor=snap.cash_buffer_minor,
        has_b2b_receivables=bool(snap.invoices),
        forecast_run_id=forecast.run_id if forecast else None,
    )
