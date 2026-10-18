import Link from "next/link";
import { notFound } from "next/navigation";
import { DegradedBanner, MoneyText, StateChip } from "@fiona/ui";
import { getWorkspaceSession } from "@/lib/session";
import { readEnginePath } from "@/lib/server-read";

export const dynamic = "force-dynamic";

type Json = Record<string, unknown>;
type StepState = "done" | "waiting" | "blocked" | "not_reached";

const STATE_TEXT: Record<StepState, string> = { done: "Done", waiting: "Waiting", blocked: "Stopped here", not_reached: "Not reached" };
const AGENTS: Record<string, string> = { treasurer: "Treasurer", controller: "Controller", cfo_strategist: "CFO Strategist", growth_analyst: "Growth Analyst" };

function list(value: unknown): Json[] {
  return Array.isArray(value) ? (value.filter((v) => v && typeof v === "object") as Json[]) : [];
}

function when(iso: unknown): string {
  return typeof iso === "string"
    ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Karachi" }).format(new Date(iso))
    : "—";
}

function Journal({ lines, currency }: { lines: Json[]; currency: string }) {
  const debit = lines.reduce((s, l) => s + Number(l.debit_minor ?? 0), 0);
  const credit = lines.reduce((s, l) => s + Number(l.credit_minor ?? 0), 0);
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead><tr><th>Account</th><th>Debit</th><th>Credit</th></tr></thead>
        <tbody>
          {lines.map((l) => (
            <tr key={String(l.line_no)}>
              <td>{String(l.account_code)} · {String(l.account_name ?? "")}</td>
              <td>{Number(l.debit_minor) ? <MoneyText amountMinor={Number(l.debit_minor)} currency={currency} animateCount={false} /> : ""}</td>
              <td>{Number(l.credit_minor) ? <MoneyText amountMinor={Number(l.credit_minor)} currency={currency} animateCount={false} /> : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={`trace-balance ${debit === credit ? "quote-ok" : "quote-bad"}`}>{debit === credit ? "✓ Balanced: debits equal credits" : "⚠ Not balanced"}</p>
    </div>
  );
}

function Step({ n, title, state, children }: { n: number; title: string; state: StepState; children: React.ReactNode }) {
  return (
    <li className={`trace-step trace-${state}`}>
      <span className="trace-dot" aria-hidden="true">{state === "done" ? "✓" : state === "blocked" ? "✕" : n}</span>
      <div>
        <div className="trace-head"><h3>{title}</h3><span className="trace-state">{STATE_TEXT[state]}</span></div>
        {children}
      </div>
    </li>
  );
}

/** One proposal from the bill to the audit chain, every step with its evidence. */
export default async function ProposalTrace({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^prop_[A-Za-z0-9_]+$/.test(id)) notFound();
  const session = await getWorkspaceSession();
  const result = await readEnginePath(`/v1/proposals/${id}/trace`);
  if (result.kind === "ok" && result.status === 404) notFound();
  if (result.kind !== "ok" || result.status !== 200) {
    return <div className="section-page"><h1>Proposal trail</h1><DegradedBanner>{result.kind === "unavailable" ? result.message : "The trail could not be loaded."}</DegradedBanner></div>;
  }
  const t = result.data as Json;
  const p = t.proposal as Json;
  const payload = (p.payload ?? {}) as Json;
  const amount = p.amount as { minor: number; currency: string } | null;
  const currency = amount?.currency ?? "PKR";
  const bill = t.bill as Json | null;
  const document = t.document as Json | null;
  const verdicts = list(t.verdicts);
  const latest = verdicts[verdicts.length - 1];
  const decisions = list(t.decisions);
  const lastDecision = decisions[decisions.length - 1];
  const payment = t.payment as Json | null;
  const audit = list(t.audit);
  const chain = t.audit_chain as { verified: boolean; length: number; first_bad_seq: number | null };
  const blocked = latest?.outcome === "block";
  const rejected = lastDecision?.decision === "reject";
  const decidedOnLatest = lastDecision && lastDecision.verdict_id === latest?.id;

  const decisionState: StepState = blocked ? "not_reached" : decidedOnLatest ? (rejected ? "blocked" : "done") : "waiting";
  const paymentState: StepState = payment ? "done" : blocked || rejected ? "not_reached" : decidedOnLatest ? "waiting" : "not_reached";

  return (
    <div className="section-page trace-page">
      <div className="page-kicker"><span className="eyebrow">PROPOSAL TRAIL</span><StateChip>{id}</StateChip></div>
      <header className="page-heading">
        <div>
          <h1>{String(p.summary)}</h1>
          <p>{AGENTS[String(p.agent)] ?? String(p.agent)} · {amount ? <MoneyText amountMinor={amount.minor} currency={currency} animateCount={false} /> : "no amount"} · pays on {String(payload.pay_on ?? "—")}</p>
        </div>
        <Link className="button button-secondary heading-action" href="/approvals">Back to approvals</Link>
      </header>

      <ol className="trace-list">
        <Step n={1} title="Bill received and posted" state={bill ? "done" : "not_reached"}>
          {bill ? (
            <>
              <p>{String(bill.number ?? bill.bill_id)} from {String(bill.supplier_id ?? bill.party)} · issued {String(bill.issue_date)} · due {String(bill.due_date)} · posted {String(bill.posted_on)}</p>
              {document && list((document.embedded_instructions as unknown[])?.map((x) => ({ x })) ?? []).length > 0 && (
                <div className="bill-alert"><strong>Instructions found in the document (reported, not followed):</strong><ul>{(document.embedded_instructions as string[]).map((x) => <li key={x}>&ldquo;{x}&rdquo;</li>)}</ul></div>
              )}
              {document && Array.isArray(document.warnings) && document.warnings.length > 0 && <ul className="bill-warnings">{(document.warnings as string[]).map((w) => <li key={w}>{w}</li>)}</ul>}
              {document && <p className="footnote">Document {String(document.id)} · SHA-256 {String(document.sha256).slice(0, 16)}… · received {when(document.received_at)}</p>}
              {list(t.bill_journal).length > 0 && <Journal lines={list(t.bill_journal)} currency={currency} />}
            </>
          ) : <p>This proposal does not refer to a bill.</p>}
        </Step>

        <Step n={2} title={`${AGENTS[String(p.agent)] ?? String(p.agent)} proposed it`} state="done">
          <p>{String(p.reasoning)}</p>
          <p className="footnote">Created {when(p.created_at)} by {String(((p.created_by as Json) ?? {}).kind)} {String(((p.created_by as Json) ?? {}).id)} · amount, payee and evidence filled from the ledger, not typed by the agent.</p>
        </Step>

        <Step n={3} title="Guardian checks" state={!latest ? "waiting" : blocked ? "blocked" : "done"}>
          {verdicts.map((v, i) => {
            const checks = list(v.checks);
            const failed = checks.filter((c) => c.outcome !== "approve");
            const review = checks.find((c) => c.rule === "G-12");
            const audit12 = (review?.audit ?? {}) as Json;
            return (
              <div key={String(v.id)} className="trace-verdict">
                <strong>{i === 0 ? "Rules" : "Independent review added"} · outcome {String(v.outcome).replaceAll("_", " ")}</strong>
                <span className="footnote"> {String(v.id)} · {when(v.decided_at)}{v.previous_verdict_id ? ` · replaces ${String(v.previous_verdict_id)}` : ""}</span>
                <ul>
                  <li>{checks.length - failed.length} of {checks.length} checks passed</li>
                  {failed.map((c) => <li key={`${String(c.rule)}${String(c.detail)}`}><strong>{String(c.rule)}</strong> {String(c.outcome)}: {String(c.detail)}</li>)}
                  {review && review.outcome === "approve" && <li><strong>G-12</strong> concern {String(audit12.concern ?? "?")}: no reason to stop it</li>}
                </ul>
              </div>
            );
          })}
          {!verdicts.some((v) => list(v.checks).some((c) => c.rule === "G-12")) && <p className="footnote">The independent model review has not reported yet.</p>}
        </Step>

        <Step n={4} title="Your decision" state={decisionState}>
          {blocked && <p>The Guardian blocked this proposal; no approval can release a block.</p>}
          {!blocked && decisions.length === 0 && <p>Waiting for the owner or finance team. <Link className="text-link" href="/approvals">Decide in Approvals →</Link></p>}
          {decisions.map((d) => (
            <p key={String(d.id)}>
              <strong>{d.decision === "approve" ? "Approved" : "Rejected"}</strong> by {d.decided_by === session?.userId ? "you" : String(d.decided_by)} on {when(d.decided_at)}
              {d.note ? ` · “${String(d.note)}”` : ""}
              {d.verdict_id !== latest?.id ? " · on an earlier verdict, so it no longer counts" : ""}
            </p>
          ))}
        </Step>

        <Step n={5} title="Sandbox wallet payment" state={paymentState}>
          {payment ? (
            <p>
              <strong>Paid (simulated)</strong> <MoneyText amountMinor={Number(payment.amount_minor)} currency={currency} animateCount={false} /> on {String(payment.paid_on)} · {String(payment.from_iban)} → {String(payment.to_iban)} · ref {String(payment.wallet_ref)}
            </p>
          ) : <p>{paymentState === "waiting" ? `Approved. The wallet pays it on ${String(payload.pay_on ?? "its date")} (Approvals → Pay what is due today).` : "No money has moved."}</p>}
        </Step>

        <Step n={6} title="Ledger entry" state={payment ? "done" : "not_reached"}>
          {payment && list(payment.journal).length > 0 ? <Journal lines={list(payment.journal)} currency={currency} /> : <p>Nothing posted for the payment.</p>}
        </Step>

        <Step n={7} title="Audit trail" state={audit.length ? (chain.verified ? "done" : "blocked") : "not_reached"}>
          <p className={chain.verified ? "quote-ok" : "quote-bad"}>
            {chain.verified ? `✓ The workspace's audit chain verifies (${chain.length} records, each hash linked to the one before).` : `⚠ The audit chain fails at record ${chain.first_bad_seq}.`}
          </p>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>#</th><th>What happened</th><th>When</th><th>Hash</th></tr></thead>
              <tbody>
                {audit.map((a) => {
                  const r = (a.record ?? {}) as Json;
                  return (
                    <tr key={String(a.seq)}>
                      <td>{String(a.seq)}</td>
                      <td>{String(r.action ?? "").replaceAll("_", " ")}{r.outcome ? ` · ${String(r.outcome)}` : ""}{r.decided_by ? ` · ${r.decided_by === session?.userId ? "you" : String(r.decided_by)}` : ""}{r.reason ? ` · ${String(r.reason)}` : ""}</td>
                      <td>{when(a.recorded_at)}</td>
                      <td><code>{String(a.hash).slice(7, 19)}…</code></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Step>
      </ol>
    </div>
  );
}
