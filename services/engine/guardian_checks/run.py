"""Runner for deterministic Guardian checks (D5).

Executes rules G-01 to G-11 and G-13 (Tier 1), plus G-14 and G-15 if enabled.
All applicable rules run regardless of earlier failures; any unhandled exception
fails closed with outcome='escalate' and detail='CHECK_ERROR: <reason>'.
"""

from __future__ import annotations

from collections.abc import Callable

from engine.guardian_checks.checks import (
    g01_per_payment_cap,
    g02_payee_allow_list,
    g03_bank_account_change,
    g04_maker_checker,
    g05_duplicate_bill,
    g06_three_way_match,
    g07_arithmetic,
    g08_cash_buffer,
    g09_evidence_check,
    g10_daily_cap,
    g11_supplier_tax_id,
    g13_mandate_permission,
    g14_stale_inputs,
    g15_insider_payee,
)
from engine.guardian_checks.context import CheckContext
from fiona_contracts.models import Check

RULE_RUNNERS: list[tuple[str, str, Callable[[CheckContext], Check | None]]] = [
    ("G-01", "policy", g01_per_payment_cap),
    ("G-02", "policy", g02_payee_allow_list),
    ("G-03", "policy", g03_bank_account_change),
    ("G-04", "policy", g04_maker_checker),
    ("G-05", "policy", g05_duplicate_bill),
    ("G-06", "policy", g06_three_way_match),
    ("G-07", "arithmetic", g07_arithmetic),
    ("G-08", "policy", g08_cash_buffer),
    ("G-09", "evidence", g09_evidence_check),
    ("G-10", "policy", g10_daily_cap),
    ("G-11", "policy", g11_supplier_tax_id),
    ("G-13", "policy", g13_mandate_permission),
]

PROPOSED_RUNNERS: list[tuple[str, str, Callable[[CheckContext], Check | None]]] = [
    ("G-14", "evidence", g14_stale_inputs),
    ("G-15", "policy", g15_insider_payee),
]


def run_deterministic_checks(
    ctx: CheckContext,
    enable_proposed: bool = False,
) -> list[Check]:
    """Run all applicable deterministic Guardian checks against the context.

    Returns a list containing one Check per applicable rule that ran.
    """
    ctx.enable_proposed = enable_proposed
    checks: list[Check] = []

    active_runners = list(RULE_RUNNERS)
    if enable_proposed:
        active_runners.extend(PROPOSED_RUNNERS)

    for rule_id, family, runner in active_runners:
        try:
            res = runner(ctx)
            if res is not None:
                checks.append(res)
        except Exception as e:
            # Fail closed: escalate on any unhandled error
            checks.append(
                Check(
                    name=family,  # type: ignore[arg-type]
                    rule=rule_id,
                    result="fail",
                    outcome="escalate",
                    detail=f"CHECK_ERROR: {e}",
                )
            )

    return checks
