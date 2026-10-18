"""Agent mandates: what each agent may do, at which autonomy level (the permission tiers).

The latest version per agent is in force. Only the owner changes a level, and a change is a new
version, never an edit (mandates are append-only), with a hash-chained `mandate_change` audit
record. A level can never exceed the system ceiling in rulebook/mandates.yaml (for example the
CFO Strategist can never act on a payment), and no agent raises its own level.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import psycopg
import yaml

from engine.app.errors import ApiError
from engine.ledger import db
from engine.wallet.audit import append

LEVELS = ("advise", "prepare", "act_within_mandate")
RULEBOOK = Path(__file__).resolve().parents[3] / "rulebook" / "mandates.yaml"


@cache
def ceilings() -> dict[str, dict[str, str]]:
    data = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    return {
        agent: dict(spec.get("ceiling") or {})
        for agent, spec in (data.get("agents") or {}).items()
        if isinstance(spec, dict)
    }


def _latest(conn: psycopg.Connection) -> list[tuple]:
    return conn.execute(
        "select distinct on (agent) id, agent, version, currency, per_payment_cap_minor,"
        " daily_cap_minor, allowed_action_types, policy, source, effective_from, created_at"
        " from mandates order by agent, version desc"
    ).fetchall()


def _shape(row: tuple) -> dict[str, Any]:
    mid, agent, version, currency, cap, daily, allowed, policy, source, effective, created = row
    policy = policy or {}
    return {
        "id": mid,
        "agent": agent,
        "version": version,
        "currency": currency,
        "per_payment_cap": {"minor": cap, "currency": currency},
        "daily_cap": {"minor": daily, "currency": currency},
        "allowed_action_types": list(allowed or []),
        "autonomy": {a: (policy.get("autonomy") or {}).get(a, "prepare") for a in (allowed or [])},
        "ceiling": ceilings().get(agent, {}),
        "allowed_categories": policy.get("allowed_categories"),
        "payee_scope": policy.get("payee_scope"),
        "payment_windows": policy.get("payment_windows"),
        "source": source,
        "effective_from": str(effective),
        "created_at": created.isoformat(),
    }


def list_mandates(conn: psycopg.Connection, tenant_id: str) -> dict[str, Any]:
    with db.tenant_session(conn, tenant_id):
        rows = _latest(conn)
    return {"api_version": "v1", "levels": list(LEVELS), "mandates": [_shape(r) for r in rows]}


def set_autonomy(
    conn: psycopg.Connection,
    tenant_id: str,
    agent: str,
    action_type: str,
    level: str,
    *,
    changed_by: str,
    now: datetime,
) -> dict[str, Any]:
    if level not in LEVELS:
        raise ApiError(422, "invalid_level", f"level must be one of {', '.join(LEVELS)}.")
    ceiling = ceilings().get(agent, {}).get(action_type)
    if ceiling is None:
        raise ApiError(403, "not_permitted", f"{agent} may never take {action_type} actions.")
    if LEVELS.index(level) > LEVELS.index(ceiling):
        raise ApiError(
            403, "above_ceiling", f"{agent} cannot go above {ceiling} for {action_type}."
        )
    with db.tenant_session(conn, tenant_id):
        row = next((r for r in _latest(conn) if r[1] == agent), None)
        if row is None:
            raise ApiError(404, "not_found", f"{agent} has no mandate.")
        mid, _, version, currency, cap, daily, allowed, policy, _, _, _ = row
        if action_type not in (allowed or []):
            raise ApiError(403, "not_permitted", f"{agent}'s mandate does not cover {action_type}.")
        policy = dict(policy or {})
        autonomy = dict(policy.get("autonomy") or {})
        previous = autonomy.get(action_type, "prepare")
        if previous == level:
            return {"api_version": "v1", "mandate": _shape(row), "changed": False}
        autonomy[action_type] = level
        policy["autonomy"] = autonomy
        new_id = f"mnd_{agent}_v{version + 1}"
        conn.execute(
            "insert into mandates (tenant_id, id, agent, version, currency, per_payment_cap_minor,"
            " daily_cap_minor, allowed_action_types, policy, source, effective_from, created_at)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'owner', %s, %s)",
            (
                tenant_id,
                new_id,
                agent,
                version + 1,
                currency,
                cap,
                daily,
                allowed,
                json.dumps(policy),
                now.date(),
                now,
            ),
        )
        append(
            conn,
            tenant_id,
            {
                "action": "mandate_change",
                "agent": agent,
                "action_type": action_type,
                "from": previous,
                "to": level,
                "previous_mandate_id": mid,
                "mandate_id": new_id,
                "changed_by": changed_by,
            },
            now=now,
        )
        current = next(r for r in _latest(conn) if r[1] == agent)
    return {"api_version": "v1", "mandate": _shape(current), "changed": True}
