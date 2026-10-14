"""Hypothesis property tests for Guardian checks and combiner (D5).

Validates invariant properties:
1. `combine` never returns an outcome less strict than any input.
2. Adding a passing check never changes the outcome.
3. An exception in any rule yields escalate or stricter, never approve.
4. Built verdicts always re-verify their cryptographic hash.
"""

from __future__ import annotations

from typing import Literal
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from engine.guardian_checks.combine import build_verdict, combine
from engine.guardian_checks.context import CheckContext
from engine.guardian_checks.rules import STRICTNESS_ORDER
from engine.guardian_checks.run import run_deterministic_checks
from fiona_contracts.hashing import verdict_hash
from fiona_contracts.models import Check, PayOnCondition

OUTCOMES: list[Literal["approve", "approve_with_conditions", "escalate", "block"]] = [
    "block",
    "escalate",
    "approve_with_conditions",
    "approve",
]
RANK_MAP = {outcome: idx for idx, outcome in enumerate(STRICTNESS_ORDER)}

check_strategy = st.builds(
    Check,
    name=st.sampled_from(["policy", "evidence", "arithmetic"]),
    rule=st.sampled_from(
        [
            "G-01",
            "G-02",
            "G-03",
            "G-04",
            "G-05",
            "G-06",
            "G-07",
            "G-08",
            "G-09",
            "G-10",
            "G-11",
            "G-13",
        ]
    ),
    result=st.sampled_from(["pass", "fail"]),
    outcome=st.sampled_from(OUTCOMES),
    detail=st.text(min_size=1, max_size=100).filter(lambda s: bool(s.strip())),
    condition=st.one_of(
        st.none(),
        st.builds(
            PayOnCondition,
            kind=st.just("pay_on"),
            date=st.sampled_from(["2026-11-01", "2026-11-15", "2026-12-01"]),
        ),
    ),
    audit=st.none(),
)


@given(checks=st.lists(check_strategy, min_size=1, max_size=20))
def test_combine_never_less_strict_than_any_input(checks: list[Check]) -> None:
    """Property 1: combine never returns an outcome less strict than any input check."""
    outcome, _ = combine(checks)
    combined_rank = RANK_MAP[outcome]
    input_ranks = [RANK_MAP[c.outcome] for c in checks]
    strictest_input_rank = min(input_ranks)

    # combined_rank must be <= strictest_input_rank (lower index = stricter)
    assert combined_rank <= strictest_input_rank, (
        f"Combined outcome {outcome} (rank {combined_rank}) is less strict than "
        f"strictest input (rank {strictest_input_rank})"
    )


@given(base_checks=st.lists(check_strategy, min_size=1, max_size=15))
def test_adding_passing_check_never_changes_outcome(base_checks: list[Check]) -> None:
    """Property 2: Adding a passing check never changes the outcome."""
    base_outcome, _ = combine(base_checks)

    passing_check = Check(
        name="policy",
        rule="G-01",
        result="pass",
        outcome="approve",
        detail="Payment is within per-payment cap.",
    )

    new_outcome, _ = combine([*base_checks, passing_check])
    assert new_outcome == base_outcome, (
        f"Adding passing check changed outcome from {base_outcome} to {new_outcome}"
    )


@given(
    failing_rule_idx=st.integers(min_value=0, max_value=11),
    err_msg=st.text(min_size=1, max_size=50).filter(lambda s: bool(s.strip())),
)
def test_exception_in_rule_yields_escalate_or_stricter(failing_rule_idx: int, err_msg: str) -> None:
    """Property 3: An unhandled exception in any rule runner yields escalate or block, never approve."""
    ctx = CheckContext(
        buffer_minor=200_000_000,
        country="PK",
        proposal={"agent": "treasurer", "type": "payment", "amount_minor": 1000},
        now="2026-10-22T09:00:00Z",
    )

    from engine.guardian_checks import run as run_module

    target_rule = run_module.RULE_RUNNERS[failing_rule_idx][0]

    def _exploding_runner(_ctx: CheckContext) -> Check:
        raise RuntimeError(f"Simulated fault: {err_msg}")

    new_runners = list(run_module.RULE_RUNNERS)
    new_runners[failing_rule_idx] = (
        new_runners[failing_rule_idx][0],
        new_runners[failing_rule_idx][1],
        _exploding_runner,
    )

    with patch.object(run_module, "RULE_RUNNERS", new_runners):
        checks = run_deterministic_checks(ctx)
        outcome, _ = combine(checks)

        # Must never approve
        assert outcome in ("escalate", "block"), (
            f"Fault in rule {target_rule} produced unsafe outcome {outcome}"
        )


@given(checks=st.lists(check_strategy, min_size=1, max_size=10))
def test_verdict_hash_recomputes_correctly(checks: list[Check]) -> None:
    """Property 4: Built Verdict cryptographic hash recomputes identically."""
    verdict = build_verdict(
        proposal_id="prop_property_test_01",
        checks=checks,
        now="2026-10-22T09:00:00Z",
    )

    v_dict = verdict.model_dump(mode="json", exclude_none=True)
    recomputed = verdict_hash(v_dict)
    assert verdict.verdict_hash == recomputed
