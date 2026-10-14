"""Sandbox agent wallet and hash-chained audit log (D6).

Provides:
- audit.py: Append and verify cryptographic hash chains in the audit_log table.
- wallet.py: Autonomous payment execution engine with defence-in-depth safety checks.
- oplog.py: JSONL operational logs and evidence bundle exporter (Deliverable 06).
"""

from __future__ import annotations

from engine.wallet.audit import AuditEntry, VerifyResult, append, verify
from engine.wallet.oplog import export_operation_log
from engine.wallet.wallet import PaymentResult, execute_payment

__all__ = [
    "AuditEntry",
    "PaymentResult",
    "VerifyResult",
    "append",
    "execute_payment",
    "export_operation_log",
    "verify",
]
