import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, EmptyState, MoneyText, OutcomeBadge, StateChip, VerdictPanel } from "@fiona/ui";
import { getMockProposal } from "@/lib/mock-api";

export default async function ProposalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[A-Za-z0-9_-]{3,80}$/.test(id)) notFound();
  const record = getMockProposal(id);
  if (!record) return <div className="section-page"><div className="page-kicker"><Link className="text-link" href="/approvals">← Back to approvals</Link><StateChip>Mock data</StateChip></div><EmptyState title="No matching mock proposal">This ID is not in the synthetic mock API.</EmptyState></div>;
  const { proposal, verdict } = record;
  return <div className="section-page"><div className="page-kicker"><Link className="text-link" href="/approvals">← Back to approvals</Link><StateChip>Mock API</StateChip></div><header className="page-heading"><div><span className="eyebrow">PROPOSAL SUMMARY</span><h1>{proposal.summary}</h1><p>Prepared by {proposal.agent.replaceAll("_", " ")} · no approval or payment is available from this synthetic view.</p></div></header><Card className="route-placeholder"><div className="placeholder-topline"><span className="eyebrow">PROPOSED PAYMENT</span>{proposal.amount && <MoneyText amountMinor={proposal.amount.minor} currency={proposal.amount.currency} />}</div><p className="proposal-reasoning">{proposal.reasoning}</p>{verdict ? <VerdictPanel outcome={verdict.outcome === "approve_with_conditions" ? "conditions" : verdict.outcome}><ul className="verdict-check-list">{verdict.checks.map((check) => <li key={`${check.rule}-${check.name}`}><OutcomeBadge outcome={check.outcome === "approve_with_conditions" ? "conditions" : check.outcome} /><strong>{check.rule}</strong><span>{check.detail}</span></li>)}</ul></VerdictPanel> : <EmptyState title="No Guardian verdict">The mock proposal has not been reviewed.</EmptyState>}</Card></div>;
}
