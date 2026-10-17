"""verify_audit_chain.py — Independent audit chain verifier for FinTechathon 2026."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def canonical_json(value: object) -> str:
    """Canonical RFC 8785 JSON representation with sorted keys and no whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_audit_hash(prev_hash: str, record: dict) -> str:
    """Compute sha256(prev_hash + canonical_json(record)) as sha256:<hex>."""
    canonical = canonical_json(record)
    content = prev_hash + canonical
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_chain(log_path: str | Path) -> bool:
    genesis_prev = "sha256:" + "0" * 64
    prev_hash = genesis_prev
    valid_count = 0

    with open(log_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            entry = json.loads(line_str)
            seq = entry["seq"]
            recorded_prev = entry["prev_hash"]
            recorded_hash = entry["hash"]
            record = entry["record"]

            # 1. Verify link to previous entry
            if recorded_prev != prev_hash:
                print(f"[ERROR] Broken link at sequence {seq} (line {line_num})!")
                print(f"  Expected prev_hash: {prev_hash}\n  Recorded:         {recorded_prev}")
                return False

            # 2. Recompute current entry hash
            computed_hash = compute_audit_hash(prev_hash, record)
            if computed_hash != recorded_hash:
                print(f"[ERROR] Cryptographic mismatch at sequence {seq} (line {line_num})!")
                print(f"  Computed: {computed_hash}\n  Recorded: {recorded_hash}")
                return False

            prev_hash = computed_hash
            valid_count += 1

    print(
        f"[SUCCESS] Audit chain verified: {valid_count} entries cryptographically intact and untampered."
    )
    return True


if __name__ == "__main__":
    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "docs/submission/06-execution-evidence/audit_chain.jsonl"
    )
    success = verify_chain(target)
    sys.exit(0 if success else 1)
