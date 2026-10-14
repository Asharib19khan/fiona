"""Tests for autonomous sandbox wallet and payment execution (D6)."""

from __future__ import annotations

import psycopg
import pytest

from engine.guardian_checks.checks import g01_per_payment_cap, g03_bank_account_change
from engine.guardian_checks.combine import build_verdict
from engine.guardian_checks.context import (
    BankDetailChangeContext,
    CheckContext,
    PartyContext,
)
from engine.ledger.db import tenant_session
from engine.wallet.audit import verify
from engine.wallet.tests.conftest import seed_wallet_tenant
from engine.wallet.wallet import execute_payment


def test_payment_refusals(conn: psycopg.Connection) -> None:
    """Proves the wallet refuses payments in every unsafe condition and records an audit log."""
    tenant = "ten_refusals_test"
    seed_wallet_tenant(conn, tenant, opening_balance_minor=350000000)

    now = "2026-10-22T09:00:00Z"

    # Case 1: No verdict
    prop_no_verdict = {
        "id": "prop_nov",
        "agent": "treasurer",
        "type": "payment",
        "amount_minor": 5000000,
        "payload": {"payee_id": "sup_001"},
    }
    with tenant_session(conn, tenant):
        res1 = execute_payment(conn, prop_no_verdict, verdict=None, now=now)
        assert res1.status == "refused"
        assert "NO_VERDICT" in str(res1.reason)

    # Case 2: Block verdict
    ctx_block = CheckContext(
        proposal={
            "id": "prop_blk",
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 5000000,
        },
        payee=PartyContext(
            party_id="sup_017",
            bank_account_changed_at="2026-10-20T06:30:00Z",
            latest_bank_detail_change=BankDetailChangeContext(
                confirmed_via="email", days_before_as_of=2
            ),
        ),
        now=now,
    )
    chk_block = g03_bank_account_change(ctx_block)
    assert chk_block is not None
    verdict_block = build_verdict("prop_blk", [chk_block], now=now)

    with tenant_session(conn, tenant):
        res2 = execute_payment(
            conn,
            {"id": "prop_blk", "agent": "treasurer", "amount_minor": 5000000},
            verdict_block,
            now=now,
        )
        assert res2.status == "refused"
        assert "VERDICT_BLOCKED" in str(res2.reason)

    # Case 3: Tampered verdict hash
    v_tampered_dict = verdict_block.model_dump(mode="json", exclude_none=True)
    v_tampered_dict["verdict_hash"] = "sha256:" + "0" * 64
    with tenant_session(conn, tenant):
        res3 = execute_payment(
            conn,
            {"id": "prop_blk", "agent": "treasurer", "amount_minor": 5000000},
            v_tampered_dict,
            now=now,
        )
        assert res3.status == "refused"
        assert "TAMPERED_VERDICT" in str(res3.reason)

    # Case 4: Escalation approved by the proposer (segregation of duties violation)
    ctx_esc = CheckContext(
        proposal={
            "id": "prop_esc",
            "agent": "treasurer",
            "type": "payment",
            "amount_minor": 18450000,
        },
        mandate={"per_payment_cap_minor": 15000000, "daily_cap_minor": 45000000},
        now=now,
    )
    chk_esc = g01_per_payment_cap(ctx_esc)
    assert chk_esc is not None
    verdict_esc = build_verdict("prop_esc", [chk_esc], now=now)

    with tenant_session(conn, tenant):
        # Approver is the treasurer (proposer)
        res4 = execute_payment(
            conn,
            {
                "id": "prop_esc",
                "agent": "treasurer",
                "amount_minor": 18450000,
                "payload": {"payee_id": "sup_001"},
            },
            verdict_esc,
            approvals=[{"user_id": "treasurer", "decision": "approved"}],
            now=now,
        )
        assert res4.status == "refused"
        assert "INVALID_APPROVAL" in str(res4.reason)

    # Case 5: Expired / future condition (pay_on is in future)
    from fiona_contracts.models import Check, PayOnCondition

    cond_check = Check(
        name="policy",
        rule="G-08",
        result="fail",
        outcome="approve_with_conditions",
        detail="Pay on safe date",
        condition=PayOnCondition(kind="pay_on", date="2026-12-08"),
    )
    verdict_cond = build_verdict("prop_cond", [cond_check], now=now)
    with tenant_session(conn, tenant):
        res5 = execute_payment(
            conn,
            {
                "id": "prop_cond",
                "agent": "treasurer",
                "amount_minor": 5000000,
                "payload": {"payee_id": "sup_001"},
            },
            verdict_cond,
            now=now,  # current date is 2026-10-22 < 2026-12-08
        )
        assert res5.status == "refused"
        assert "CONDITION_NOT_MET" in str(res5.reason)

    # Case 6: Defence in depth: amount exceeds per-payment cap
    pass_check = Check(
        name="policy", rule="G-01", result="pass", outcome="approve", detail="Passing check"
    )
    verdict_approved = build_verdict("prop_overcap", [pass_check], now=now)
    with tenant_session(conn, tenant):
        res6 = execute_payment(
            conn,
            {
                "id": "prop_overcap",
                "agent": "treasurer",
                "amount_minor": 20000000,
                "payload": {"payee_id": "sup_001"},
            },
            verdict_approved,
            now=now,
        )
        assert res6.status == "refused"
        assert "DEFENCE_IN_DEPTH_CAP" in str(res6.reason)

    # Verify all refusal audit records exist and chain verifies
    with tenant_session(conn, tenant):
        v_res = verify(conn, tenant)
        assert v_res.ok is True
        assert v_res.length == 6


def test_s01_flow(conn: psycopg.Connection) -> None:
    """The S-01 flow: escalate -> owner approval -> exactly one supplier_payment event -> audit chain verifies."""
    tenant = "ten_s01_flow"
    seed_wallet_tenant(conn, tenant, opening_balance_minor=350000000)

    now = "2026-10-22T09:00:00Z"
    proposal = {
        "id": "prop_s01payment",
        "agent": "treasurer",
        "type": "payment",
        "amount_minor": 28036800,
        "currency": "PKR",
        "payload": {
            "payee_id": "sup_001",
            "to_iban": "PK70SYNA0000000100000001",
            "bill_id": "bill_2240",
            "category": "inventory_supplier",
        },
        "reasoning": "Payment for clean bill above cap.",
    }

    # Seed proposal row so approval foreign key and status update can succeed
    with conn.cursor() as cur:
        import json

        cur.execute(
            """
            INSERT INTO public.proposals (
                tenant_id, id, agent, type, created_at, summary, amount_minor, currency, payload, reasoning
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (
                tenant,
                proposal["id"],
                proposal["agent"],
                proposal["type"],
                now,
                "S-01 Payment proposal",
                proposal["amount_minor"],
                proposal["currency"],
                json.dumps(proposal["payload"]),
                proposal["reasoning"],
            ),
        )

    # 1. Deterministic check yields escalate
    ctx = CheckContext(
        proposal=proposal,
        mandate={"per_payment_cap_minor": 15000000, "daily_cap_minor": 45000000},
        now=now,
    )
    chk = g01_per_payment_cap(ctx)
    assert chk is not None and chk.outcome == "escalate"

    verdict = build_verdict("prop_s01payment", [chk], now=now)
    assert verdict.outcome == "escalate"

    # 2. Owner approves
    approvals = [
        {
            "id": "app_s01_01",
            "user_id": "usr_owner",
            "decision": "approved",
            "notes": "Approved by owner",
        }
    ]

    # 3. Wallet executes payment inside tenant_session
    with tenant_session(conn, tenant):
        res = execute_payment(conn, proposal, verdict, approvals=approvals, now=now)
        assert res.status == "executed"
        assert res.payment_id is not None
        assert res.wallet_ref is not None
        assert res.amount_minor == 28036800

        # Exactly one supplier_payment event
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*), payload->>'wallet_ref', payload->>'amount_minor'
                  FROM public.events
                 WHERE tenant_id = %s AND type = 'supplier_payment' AND source->>'key' = %s
                 GROUP BY payload->>'wallet_ref', payload->>'amount_minor'
                """,
                (tenant, res.wallet_ref),
            )
            rows = cur.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 1
            assert rows[0][1] == res.wallet_ref
            assert int(rows[0][2]) == 28036800

            # Balance deducted correctly (350,000,000 - 28,036,800 = 321,963,200)
            cur.execute(
                "SELECT balance_minor FROM public.wallet_accounts WHERE tenant_id = %s", (tenant,)
            )
            bal = cur.fetchone()[0]
            assert bal == 350000000 - 28036800

        # Audit chain verifies
        v_chain = verify(conn, tenant)
        assert v_chain.ok is True
        assert v_chain.length >= 1


def test_demo_1_never_pays(conn: psycopg.Connection) -> None:
    """DEMO-1 never pays: blocked verdict always refuses execution, even if approval attempted."""
    tenant = "ten_demo1_test"
    seed_wallet_tenant(conn, tenant, opening_balance_minor=350000000)

    now = "2026-10-22T09:00:00Z"
    proposal = {
        "id": "prop_demo1attempt",
        "agent": "treasurer",
        "type": "payment",
        "amount_minor": 18450000,
        "payload": {
            "payee_id": "sup_017",
            "to_iban": "PK70SYNB0000000200000002",
            "bill_id": "bill_2231",
        },
    }

    ctx = CheckContext(
        proposal=proposal,
        payee=PartyContext(
            party_id="sup_017",
            bank_account_changed_at="2026-10-20T06:30:00Z",
            latest_bank_detail_change=BankDetailChangeContext(
                confirmed_via="email", days_before_as_of=2
            ),
        ),
        now=now,
    )
    chk_g03 = g03_bank_account_change(ctx)
    assert chk_g03 is not None and chk_g03.outcome == "block"

    verdict_demo1 = build_verdict("prop_demo1attempt", [chk_g03], now=now)
    assert verdict_demo1.outcome == "block"

    with tenant_session(conn, tenant):
        # Owner attempts approval
        res = execute_payment(
            conn,
            proposal,
            verdict_demo1,
            approvals=[{"user_id": "usr_owner", "decision": "approved"}],
            now=now,
        )
        assert res.status == "refused"
        assert "VERDICT_BLOCKED" in str(res.reason)

        # Confirm 0 supplier_payment events were written
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.events WHERE tenant_id = %s AND type = 'supplier_payment'",
                (tenant,),
            )
            assert cur.fetchone()[0] == 0


def test_tenant_rls_isolation(conn: psycopg.Connection) -> None:
    """Tenant A cannot read or write Tenant B's wallet or audit log rows."""
    tenant_a = "ten_a_iso"
    tenant_b = "ten_b_iso"

    seed_wallet_tenant(conn, tenant_a)
    seed_wallet_tenant(conn, tenant_b)

    with tenant_session(conn, tenant_a):
        from engine.wallet.audit import append

        append(conn, tenant_a, {"action": "tenant_a_secret", "secret_value": 42})

    # Under Tenant B's session, Tenant A's records are completely invisible
    with tenant_session(conn, tenant_b):
        with conn.cursor() as cur:
            # Cannot see Tenant A's audit rows
            cur.execute("SELECT count(*) FROM public.audit_log WHERE tenant_id = %s", (tenant_a,))
            assert cur.fetchone()[0] == 0

            # Cannot see Tenant A's wallet account
            cur.execute(
                "SELECT count(*) FROM public.wallet_accounts WHERE tenant_id = %s", (tenant_a,)
            )
            assert cur.fetchone()[0] == 0

            # Attempting to insert into Tenant A's audit log violates RLS WITH CHECK policy
            with pytest.raises(psycopg.Error):
                cur.execute(
                    """
                    INSERT INTO public.audit_log (tenant_id, seq, prev_hash, record, hash, recorded_at)
                    VALUES (%s, 999, 'sha256:000', '{}'::jsonb, 'sha256:111', now())
                    """,
                    (tenant_a,),
                )
