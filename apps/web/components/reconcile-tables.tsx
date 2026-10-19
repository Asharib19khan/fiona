"use client";

import { useMemo } from "react";
import { EmptyState, MoneyText } from "@fiona/ui";
import { PagedList, PagedTable } from "@/components/paged";
import { Meter, Pill, nice, toneFor } from "@/components/screen-kit";

/** Plain data from the server; rows are built here so thousands of matches stay a small payload. */
export interface MatchRow { line: string; pass: string; confidence: number; status: string; events: string[] }
export interface FindingRow { id: string; title: string; detail: string; minor: number | null }

function LinkedEvents({ ids }: { ids: string[] }) {
  if (!ids.length) return <>—</>;
  const [first, second, ...rest] = ids;
  return (
    <div className="sk-events">
      <code className="sk-mono">{first}</code>
      {second && <code className="sk-mono">{second}</code>}
      {rest.length > 0 && <details className="sk-events-more"><summary>+{rest.length} more</summary><div>{rest.map((id) => <code className="sk-mono" key={id}>{id}</code>)}</div></details>}
    </div>
  );
}

export function MatchTable({ matches }: { matches: MatchRow[] }) {
  const rows = useMemo(() => matches.map((match) => [
    <code key="line" className="sk-mono">{match.line}</code>,
    <span key="pass" className="sk-nowrap">{nice(match.pass)}</span>,
    <span key="conf" className="sk-conf"><Meter value={match.confidence} tone={match.confidence >= 1 ? "green" : match.confidence >= 0.9 ? "blue" : "amber"} /><span>{Math.round(match.confidence * 100)}%</span></span>,
    <Pill key="status" tone={toneFor(match.status)}>{nice(match.status)}</Pill>,
    <LinkedEvents key="events" ids={match.events} />,
  ]), [matches]);
  if (!rows.length) return <EmptyState title="No records to show">No match response is available. Run the local engine with the seeded database to load it.</EmptyState>;
  return <PagedTable headers={["Bank line", "Pass", "Confidence", "Review status", "Linked events"]} rows={rows} noun="matches" pageSize={20} />;
}

export function FindingList({ findings }: { findings: FindingRow[] }) {
  const items = useMemo(() => findings.map((finding) => (
    <article className="option-row sk-finding" key={finding.id}>
      <div><h3>{finding.title}</h3><p>{finding.detail}</p></div>
      {finding.minor !== null && <strong><MoneyText amountMinor={finding.minor} animateCount={false} /></strong>}
    </article>
  )), [findings]);
  return <PagedList items={items} pageSize={10} noun="findings" />;
}
