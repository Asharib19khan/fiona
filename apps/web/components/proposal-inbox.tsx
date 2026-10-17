"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, EmptyState, MoneyText, OutcomeBadge, StateChip } from "@fiona/ui";
import type { Proposal, ProposalDraft, Verdict } from "@fiona/contracts";
import type { MockProposalRecord } from "@/lib/mock-api";

type ProposalRow = { proposal: Proposal; verdict: Verdict | null };
const sampleDraft: ProposalDraft = {
  agent: "treasurer",
  type: "payment",
  summary: "Synthetic demo draft for supplier invoice INV-2231",
  amount: { minor: 5_000_000, currency: "PKR" },
  payload: {
    payee_id: "sup_017",
    bill_id: "bill_2231",
    pay_on: "2026-10-24",
    channel: "wallet",
    category: "inventory_supplier",
  },
  evidence: [{ kind: "bill", ref: "bill_2231" }],
  reasoning: "Synthetic draft used to demonstrate local proposal intake. It has not been reviewed by Guardian.",
  mandate_ref: "mnd_treasurer_v1",
  created_by: { kind: "user", id: "usr_demo_owner" },
};

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function proposalRows(value: unknown): ProposalRow[] {
  if (!isObject(value) || !Array.isArray(value.proposals)) return [];
  return value.proposals.flatMap((item) => {
    if (!isObject(item)) return [];
    if (isObject(item.proposal)) {
      return [{ proposal: item.proposal as unknown as Proposal, verdict: isObject(item.verdict) ? item.verdict as unknown as Verdict : null }];
    }
    const { verdict, ...proposal } = item;
    return [{ proposal: proposal as unknown as Proposal, verdict: isObject(verdict) ? verdict as unknown as Verdict : null }];
  });
}

export function ProposalInbox({ initial, mockEnabled }: { initial: MockProposalRecord[]; mockEnabled: boolean }) {
  const [rows, setRows] = useState<ProposalRow[]>(initial);
  const [message, setMessage] = useState("Local mock mode only. Draft submission does not run Guardian or approve a payment.");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const response = await fetch("/api/fiona/proposals", { cache: "no-store" });
    const body: unknown = await response.json();
    if (!response.ok) {
      const detail = isObject(body) && isObject(body.error) && typeof body.error.message === "string" ? body.error.message : "The proposal list could not be loaded.";
      throw new Error(detail);
    }
    const loaded = proposalRows(body);
    if (loaded.length) setRows(loaded);
  }

  useEffect(() => {
    let active = true;
    fetch("/api/fiona/proposals", { cache: "no-store" })
      .then(async (response) => {
        const body: unknown = await response.json();
        if (!response.ok) throw new Error("Local mock proposal service is unavailable; showing the bundled fixture.");
        return proposalRows(body);
      })
      .then((loaded) => { if (active && loaded.length) setRows(loaded); })
      .catch((error: unknown) => { if (active) setMessage(error instanceof Error ? error.message : "Local mock proposal service is unavailable."); });
    return () => { active = false; };
  }, []);

  async function submitDraft() {
    setBusy(true);
    setMessage("Submitting the synthetic draft to the in-memory local mock service…");
    try {
      const response = await fetch("/api/fiona/proposals", {
        method: "POST",
        headers: { "content-type": "application/json", "idempotency-key": crypto.randomUUID() },
        body: JSON.stringify(sampleDraft),
      });
      const result: unknown = await response.json();
      if (!response.ok) {
        const detail = isObject(result) && isObject(result.error) && typeof result.error.message === "string" ? result.error.message : "The draft was not accepted.";
        throw new Error(detail);
      }
      await refresh();
      setMessage("Draft stored in local mock memory. No Guardian review, owner decision, ledger posting or payment occurred.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Draft submission failed.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <Card className="tier-panel">
      <div className="panel-heading"><div><span className="eyebrow">PROPOSAL INBOX</span><h2>Review synthetic requests</h2></div><StateChip>Mock mode</StateChip></div>
      {rows.length ? <div className="option-list">{rows.map(({ proposal, verdict }) => <article className="option-row" key={proposal.id}>
        <div><span className="eyebrow">{proposal.agent.replaceAll("_", " ")} · {proposal.type.replaceAll("_", " ")}</span><h3>{proposal.summary}</h3><p>{proposal.reasoning}</p></div>
        <div className="option-facts"><span>{proposal.amount ? <MoneyText amountMinor={proposal.amount.minor} currency={proposal.amount.currency} /> : "No amount"}</span><span>{proposal.status.replaceAll("_", " ")}</span>{verdict && <OutcomeBadge outcome={verdict.outcome === "approve_with_conditions" ? "conditions" : verdict.outcome} />}{verdict && <Link className="text-link" href={`/proposals/${proposal.id}`}>Open read-only verdict</Link>}</div>
      </article>)}</div> : <EmptyState title="No proposals available">The local service and bundled fixture returned an empty inbox.</EmptyState>}
    </Card>
    <Card className="tier-panel">
      <div className="panel-heading"><div><span className="eyebrow">LOCAL INTAKE DEMO</span><h2>Submit a sample draft</h2></div><span className="placeholder-tag">In memory · resets on restart</span></div>
      <p className="proposal-reasoning">This fixed synthetic request only demonstrates proposal intake. It is not a real bill instruction and the mock service does not call Guardian, the ledger, or the wallet.</p>
      {mockEnabled ? <button className="button button-primary" type="button" onClick={submitDraft} disabled={busy}>{busy ? "Submitting…" : "Submit synthetic draft"}</button> : <p className="footnote">Draft submission is disabled outside local mock mode.</p>}
      <p className="footnote" role="status" aria-live="polite">{message}</p>
    </Card>
  </>;
}
