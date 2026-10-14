"""Finance schedules for the persona: loan, leases, fixed assets and payroll. Integer arithmetic only.

These are facts a business holds as documents (a loan agreement and its repayment schedule, lease
agreements, an asset register, payroll summaries). The frameworks engine (Abdullah, B5) decides
how each framework treats them; the generator never applies a framework treatment.
"""

from __future__ import annotations

from datetime import date

from data.generator import core


def _months_between(start: date, end: date) -> int:
    return core.month_index(end) - core.month_index(start)


# ---------------------------------------------------------------- loan
def emi_minor(principal: int, rate_bp: int, months: int) -> int:
    """Level monthly instalment, rounded half-up to whole rupees, computed with exact fractions."""
    from fractions import Fraction

    r = Fraction(rate_bp, 10_000 * 12)
    growth = (1 + r) ** months
    emi = Fraction(principal) * r * growth / (growth - 1)
    return core.div_half_up(emi.numerator, emi.denominator * 100) * 100


def loan_schedule(cfg: dict, cal: core.Calendar) -> dict:
    principal = cfg["principal_minor"]
    rate_bp = cfg["benchmark_bp"] + cfg["spread_bp"]
    months = cfg["instalments"]
    emi = emi_minor(principal, rate_bp, months)
    first = date.fromisoformat(cfg["first_instalment"])
    balance, rows = principal, []
    for n in range(1, months + 1):
        nominal = core.add_months(first, n - 1)
        interest = core.div_half_up(balance * rate_bp, 10_000 * 12)
        payment = emi if n < months else balance + interest
        principal_part = payment - interest
        balance -= principal_part
        rows.append(
            {
                "n": n,
                "due_date": nominal.isoformat(),
                "paid_on": cal.on_or_before(nominal).isoformat(),
                "opening_principal_minor": balance + principal_part,
                "interest_minor": interest,
                "principal_minor": principal_part,
                "instalment_minor": payment,
                "closing_principal_minor": balance,
            }
        )
    return {
        "id": cfg["id"],
        "lender": cfg["lender"],
        "facility": cfg["facility"],
        "principal_minor": principal,
        "disbursed_on": cfg["disbursed_on"],
        "rate_type": cfg["rate_type"],
        "benchmark": cfg["benchmark"],
        "benchmark_bp": cfg["benchmark_bp"],
        "spread_bp": cfg["spread_bp"],
        "rate_bp": rate_bp,
        "reset_months": cfg["reset_months"],
        "instalments": months,
        "instalment_minor": emi,
        "security": cfg["security"],
        "covenants": cfg["covenants"],
        "schedule": rows,
        "note": "ASSUMPTION: the benchmark is held constant, so the schedule is level. Real KIBOR resets every "
        f"{cfg['reset_months']} months.",
    }


# ---------------------------------------------------------------- leases
def lease_payments(cfg: dict, start: date, end: date, cal: core.Calendar) -> list[dict]:
    """Monthly rent due inside [start, end]: fixed escalation (BR02) or rent by calendar year (BR01)."""
    commencement = date.fromisoformat(cfg["commencement"])
    rows = []
    month = date(start.year, start.month, 1)
    while month <= end:
        nominal = date(month.year, month.month, cfg["payment_day"])
        if start <= nominal <= end and nominal >= commencement:
            if "rent_by_year_minor" in cfg:
                amount = cfg["rent_by_year_minor"][str(month.year)]
            else:
                years = _months_between(commencement, month) // 12
                amount = cfg["monthly_rent_minor"]
                for _ in range(years):
                    amount = (
                        core.div_half_up(amount * (100 + cfg["escalation_pct_per_year"]), 100 * 100)
                        * 100
                    )
            rows.append(
                {
                    "month": month.strftime("%Y-%m"),
                    "due_date": nominal.isoformat(),
                    "paid_on": cal.on_or_before(nominal).isoformat(),
                    "amount_minor": amount,
                }
            )
        month = core.add_months(month, 1)
    return rows


def lease_record(cfg: dict, payments: list[dict]) -> dict:
    keep = (
        "id",
        "branch",
        "lessor",
        "asset",
        "commencement",
        "term_months",
        "payment_day",
        "payment_timing",
        "monthly_rent_minor",
        "escalation_pct_per_year",
        "escalation_month",
        "renewal_option",
        "incremental_borrowing_rate_bp",
        "security_deposit_minor",
        "rent_by_year_minor",
        "billed",
    )
    record = {k: cfg[k] for k in keep if k in cfg}
    record["payments"] = payments
    return record


# ---------------------------------------------------------------- fixed assets
def depreciation_to(asset: dict, on: date) -> int:
    """Straight-line accumulated depreciation at `on` (whole months after the month of acquisition)."""
    acquired = date.fromisoformat(asset["acquired_on"])
    if on < acquired:
        return 0
    months = min(asset["useful_life_months"], max(0, _months_between(acquired, on)))
    return asset["cost_minor"] * months // asset["useful_life_months"]


def asset_register(assets: list[dict], period_start: date, as_of: date) -> list[dict]:
    register = []
    for asset in assets:
        entry = dict(asset)
        entry["method"] = "straight_line"
        entry["residual_minor"] = 0
        entry["monthly_depreciation_minor"] = asset["cost_minor"] // asset["useful_life_months"]
        entry["accumulated_depreciation_at_start_minor"] = depreciation_to(asset, period_start)
        entry["accumulated_depreciation_at_as_of_minor"] = depreciation_to(asset, as_of)
        entry["in_period"] = date.fromisoformat(asset["acquired_on"]) >= period_start
        register.append(entry)
    return register


# ---------------------------------------------------------------- payroll
def payroll_gross(cfg: dict, month: date) -> int:
    """Monthly gross for the fiscal year that contains `month` (FY ends in June)."""
    fy_end = month.year + 1 if month.month >= 7 else month.year
    table = cfg["monthly_gross_minor_fy"]
    return table[str(fy_end)] if str(fy_end) in table else table[max(table, key=int)]
