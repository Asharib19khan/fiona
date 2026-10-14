"""Hash-chained audit log implementation (D6).

Provides:
- `append`: Appends an entry to the tenant's hash chain using SHA-256 over
  (prev_hash + canonical_json(record)). Monotonic seq with advisory xact lock.
- `verify`: Re-traverses and validates the full hash chain for a tenant, returning
  (ok, length, first_bad_seq).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

from fiona_contracts.hashing import canonical_json

GENESIS_PREV_HASH: str = "sha256:" + "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    tenant_id: str
    seq: int
    prev_hash: str
    record: dict[str, Any]
    hash: str
    proposal_id: str | None
    recorded_at: datetime


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    length: int
    first_bad_seq: int | None = None


def compute_audit_hash(prev_hash: str, record: dict[str, Any]) -> str:
    """Compute sha256(prev_hash + canonical_json(record)) written as sha256:<hex>."""
    canonical = canonical_json(record)
    content = prev_hash + canonical
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def append(
    conn: psycopg.Connection,
    tenant_id: str,
    record: dict[str, Any],
    proposal_id: str | None = None,
    now: datetime | None = None,
) -> AuditEntry:
    """Append a record to the tenant's audit log hash chain.

    Locks the tenant chain to prevent concurrent forks, increments seq,
    computes sha256(prev_hash + canonical_json(record)), and inserts the row.
    """
    recorded_at = now or datetime.now(UTC)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=UTC)

    # Take advisory lock scoped to current transaction to serialize appends per tenant
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (tenant_id,))

    # Find the most recent entry for this tenant
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT seq, hash
              FROM public.audit_log
             WHERE tenant_id = %s
             ORDER BY seq DESC
             LIMIT 1
            """,
            (tenant_id,),
        )

        last_row = cur.fetchone()

        if last_row is not None:
            last_seq, last_hash = last_row
            seq = last_seq + 1
            prev_hash = last_hash
        else:
            seq = 1
            prev_hash = GENESIS_PREV_HASH

        entry_hash = compute_audit_hash(prev_hash, record)

        cur.execute(
            """
            INSERT INTO public.audit_log (
                tenant_id, seq, prev_hash, record, hash, proposal_id, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                tenant_id,
                seq,
                prev_hash,
                json.dumps(record),
                entry_hash,
                proposal_id,
                recorded_at,
            ),
        )

    return AuditEntry(
        tenant_id=tenant_id,
        seq=seq,
        prev_hash=prev_hash,
        record=record,
        hash=entry_hash,
        proposal_id=proposal_id,
        recorded_at=recorded_at,
    )


def verify(conn: psycopg.Connection, tenant_id: str) -> VerifyResult:
    """Verify cryptographic hash chain integrity for the given tenant.

    Returns VerifyResult(ok=True/False, length=count, first_bad_seq=seq | None).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT seq, prev_hash, record, hash
              FROM public.audit_log
             WHERE tenant_id = %s
             ORDER BY seq ASC
            """,
            (tenant_id,),
        )
        rows = cur.fetchall()

    if not rows:
        return VerifyResult(ok=True, length=0, first_bad_seq=None)

    expected_seq = 1
    last_hash = GENESIS_PREV_HASH

    for row in rows:
        seq, prev_hash, record_val, stored_hash = row

        # Handle record column as json or string
        record = json.loads(record_val) if isinstance(record_val, str) else dict(record_val)

        # 1. Monotonic sequence check
        if seq != expected_seq:
            return VerifyResult(ok=False, length=len(rows), first_bad_seq=seq)

        # 2. Previous hash linkage check
        if prev_hash != last_hash:
            return VerifyResult(ok=False, length=len(rows), first_bad_seq=seq)

        # 3. Hash recomputation check
        expected_hash = compute_audit_hash(prev_hash, record)
        if stored_hash != expected_hash:
            return VerifyResult(ok=False, length=len(rows), first_bad_seq=seq)

        last_hash = stored_hash
        expected_seq += 1

    return VerifyResult(ok=True, length=len(rows), first_bad_seq=None)
