"""Verdict combiner and builder (D5).

Combines individual Check results according to guardian.yaml:
- Strictest outcome wins: block > escalate > approve_with_conditions > approve
- Conditions are combined; conflicting pay_on dates elevate the outcome to escalate
- No input can lower an outcome
- Builds immutable, hash-verified Verdict contracts (vrd_<ulid>)
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from engine.guardian_checks.rules import POLICY_VERSION, STRICTNESS_ORDER
from fiona_contracts.hashing import verdict_hash
from fiona_contracts.models import (
    BeforeTimeCondition,
    Check,
    MaxAmountCondition,
    PayOnCondition,
    Verdict,
)

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_ulid(timestamp_ms: int, randomness: bytes) -> str:
    value = (timestamp_ms << 80) | int.from_bytes(randomness, "big")
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def generate_verdict_id(now_dt: datetime) -> str:
    """Generate a Crockford Base32 ULID identifier prefixed with 'vrd_'."""
    ms = int(now_dt.timestamp() * 1000)
    rand_bytes = secrets.token_bytes(10)
    return f"vrd_{_encode_ulid(ms, rand_bytes)}"


def combine(
    checks: list[Check],
) -> tuple[str, list[PayOnCondition | MaxAmountCondition | BeforeTimeCondition]]:
    """Combine check results: strictest outcome wins, merge non-conflicting conditions.

    If two pay_on dates conflict, outcome elevates to escalate.
    """
    if not checks:
        return "approve", []

    # Map outcomes to strictness rank (0 is block, 3 is approve)
    rank_map = {outcome: idx for idx, outcome in enumerate(STRICTNESS_ORDER)}

    strictest_rank = max(rank_map.values())
    strictest_outcome = "approve"

    for check in checks:
        rank = rank_map.get(check.outcome, 0)
        if rank < strictest_rank:
            strictest_rank = rank
            strictest_outcome = check.outcome

    # Collect conditions from checks that have them
    all_conditions: list[PayOnCondition | MaxAmountCondition | BeforeTimeCondition] = []
    pay_on_dates: set[str] = set()

    for check in checks:
        if check.condition is not None:
            cond = check.condition
            if isinstance(cond, PayOnCondition):
                pay_on_dates.add(cond.date)
            all_conditions.append(cond)

    # If conflicting pay_on dates exist, elevate to escalate if not already stricter (block)
    if len(pay_on_dates) > 1:
        if rank_map[strictest_outcome] > rank_map["escalate"]:
            strictest_outcome = "escalate"
        return strictest_outcome, []

    # Conditions only apply if final outcome is approve_with_conditions
    if strictest_outcome == "approve_with_conditions":
        # Deduplicate conditions
        unique_conditions: list[PayOnCondition | MaxAmountCondition | BeforeTimeCondition] = []
        seen = set()
        for c in all_conditions:
            key = c.model_dump_json()
            if key not in seen:
                seen.add(key)
                unique_conditions.append(c)
        return strictest_outcome, unique_conditions

    return strictest_outcome, []


def build_verdict(
    proposal_id: str,
    checks: list[Check],
    now: datetime | str,
    policy_version: str | None = None,
    previous_verdict_id: str | None = None,
) -> Verdict:
    """Combine checks and assemble an immutable Verdict model with cryptographic hash."""
    if isinstance(now, datetime):
        now_dt = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
    else:
        s = str(now)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        now_dt = datetime.fromisoformat(s).astimezone(UTC)

    decided_at_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    outcome, conditions = combine(checks)
    verdict_id = generate_verdict_id(now_dt)
    version = policy_version or POLICY_VERSION

    # Build raw dict representation to compute canonical verdict_hash
    body: dict[str, Any] = {
        "id": verdict_id,
        "proposal_id": proposal_id,
        "outcome": outcome,
        "checks": [c.model_dump(mode="json", exclude_none=True) for c in checks],
        "conditions": [c.model_dump(mode="json", exclude_none=True) for c in conditions],
        "decided_at": decided_at_str,
        "policy_version": version,
    }
    if previous_verdict_id is not None:
        body["previous_verdict_id"] = previous_verdict_id

    # Compute verdict hash
    v_hash = verdict_hash(body)
    body["verdict_hash"] = v_hash

    return Verdict.model_validate(body)
