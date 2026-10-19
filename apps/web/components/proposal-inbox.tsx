"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { CheckCircleIcon, InboxIcon, UndoIcon, XCircleIcon } from "@/components/briefing-icons";
import { Card, EmptyState, MoneyText } from "@fiona/ui";

type Tab = "needs_you" | "blocked" | "approved" | "sent_back" | "rejected";
type Action = "approve" | "reject" | "reconsider";

interface Check {
  name: string;
  rule: string;
  result: "pass" | "fail";
  outcome: string;
  detail: string;
  audit?: { concern?: string; reasons?: string[]; injection_detected?: boolean; model?: string } | null;
}

interface Proposal {
  id: string;
  agent: string;
  type: string;
  created_at: string;
  summary: string;
  reasoning: string;
  amount: { minor: number; currency: string } | null;
  payload: { payee_id?: string; bill_id?: string; pay_on?: string };
  status: string;
  verdict: { id: string; outcome: string; checks: Check[] } | null;
}

interface Reconsideration {
  id: string;
  proposal_id: string;
  note: string;
  requested_at: string;
  status: "checking" | "done" | "failed";
  source?: "treasurer" | "supplier" | "both" | "neither";
  summary?: string;
  findings?: string[];
  treasurer_fix?: string | null;
  email?: { to: string; subject: string; body: string; sent_at: string; simulated: boolean };
  rerun_id?: string;
  rerun_status?: string | null;
  rerun_summary?: string | null;
  error?: string;
}

const AGENTS: Record<string, string> = {
  treasurer: "Treasurer",
  controller: "Controller",
  cfo_strategist: "CFO Strategist",
  growth_analyst: "Growth Analyst",
};

const REVIEWED = new Set(["payment", "bill_approval", "journal_adjustment", "send_document", "purchase_order"]);

const TABS: Array<{ key: Tab; label: string; icon: ReactNode }> = [
  { key: "needs_you", label: "Needs your decision", icon: <InboxIcon width="16" height="16" /> },
  { key: "blocked", label: "Blocked by the Guardian", icon: <XCircleIcon width="16" height="16" /> },
  { key: "approved", label: "Approved & paid", icon: <CheckCircleIcon width="16" height="16" /> },
  { key: "sent_back", label: "Sent back", icon: <UndoIcon width="16" height="16" /> },
  { key: "rejected", label: "Rejected", icon: <XCircleIcon width="16" height="16" /> },
];

const STATUSES: Record<Exclude<Tab, "sent_back" | "rejected">, string[]> = {
  needs_you: ["needs_owner", "submitted"],
  blocked: ["blocked"],
  approved: ["approved", "cleared", "executed"],
};

const SOURCES: Record<NonNullable<Reconsideration["source"]>, string> = {
  supplier: "The problem is on the supplier's bill",
  treasurer: "The problem was in the Treasurer's plan",
  both: "Problems on both the bill and the Treasurer's plan",
  neither: "No error found, so the Treasurer re-plans around your note",
};

const RERUN: Record<string, string> = {
  queued: "waiting to start",
  running: "re-planning now",
  done: "re-planned",
  failed: "could not finish",
};

function when(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Karachi" }).format(new Date(iso));
}

const VERDICTS: Record<string, string> = { approve: "approved", approve_with_conditions: "approved with conditions", escalate: "escalated to you", block: "blocked" };
function verdictLabel(outcome: string): string {
  return VERDICTS[outcome] ?? outcome.replaceAll("_", " ");
}

/** Splits a reviewer's paragraph into sentences. Decimals ("8.17M") never split: a split needs a
 * space after the full stop and a capital or digit next. */
function sentences(text: string): string[] {
  return text.split(/(?<=[.!?])\s+(?=[A-Z0-9"'“(])/).map((s) => s.trim()).filter(Boolean);
}

function ReviewPoints({ reasons }: { reasons: string[] }) {
  return (
    <ul className="review-points">
      {reasons.map((reason) => {
        const [lead, ...rest] = sentences(reason);
        return (
          <li key={reason}>
            <span className="review-lead">{lead}</span>
            {rest.length > 0 && <ul className="review-sub">{rest.map((s, i) => <li key={`${i}-${s}`}>{s}</li>)}</ul>}
          </li>
        );
      })}
    </ul>
  );
}

function GuardianSection({ proposal }: { proposal: Proposal }) {
  const checks = proposal.verdict?.checks ?? [];
  const failed = checks.filter((c) => c.outcome !== "approve");
  const review = checks.find((c) => c.rule === "G-12");
  const passed = checks.length - failed.length;
  return (
    <div className="spec-item spec-guardian-item">
      <span className="spec-label">
        Guardian verdict: {proposal.verdict ? verdictLabel(proposal.verdict.outcome) : "not yet checked"}
      </span>
      <div className="guardian-chips">
        {passed > 0 && <span className="guardian-chip chip-ok">{passed} rule{passed === 1 ? "" : "s"} passed</span>}
        {failed.filter((c) => c.rule !== "G-12").map((c) => (
          <span key={`${c.rule}-${c.detail}`} className="guardian-chip chip-failed" title={c.detail}>
            {c.rule}: {c.detail.length > 110 ? `${c.detail.slice(0, 110)}…` : c.detail}
          </span>
        ))}
      </div>
      {review ? (
        <div className={`guardian-review ${review.outcome === "approve" ? "" : "guardian-review-raised"}`}>
          <strong>
            Independent review (G-12): {review.detail.startsWith("CHECK_ERROR") ? "could not run, so this escalates" : `concern ${review.audit?.concern ?? "?"}`}
            {review.audit?.injection_detected ? " · instructions hidden in the document" : ""}
          </strong>
          {review.audit?.reasons && review.audit.reasons.length > 0 && <ReviewPoints reasons={review.audit.reasons.slice(0, 4)} />}
          {review.detail.startsWith("CHECK_ERROR") && <ReviewPoints reasons={[review.detail]} />}
        </div>
      ) : REVIEWED.has(proposal.type) && proposal.status !== "executed" ? (
        <p className="guardian-review guardian-review-pending">Independent review in progress…</p>
      ) : null}
    </div>
  );
}

function ReconsiderationPanel({ record, busy, onRetry }: { record: Reconsideration; busy: boolean; onRetry: () => void }) {
  const state = record.status === "checking" ? "Cross-checking" : record.status === "failed" ? "Could not finish" : "Checked";
  return (
    <section className={`recon-panel recon-${record.status}`} aria-live="polite">
      <header className="recon-head">
        <span className="recon-eyebrow">Sent back to the Treasurer · {when(record.requested_at)}</span>
        <span className={`recon-state recon-state-${record.status}`}>{state}</span>
      </header>
      {record.note && (
        <blockquote className="recon-note">
          <span className="recon-note-label">Your note</span>
          {record.note}
        </blockquote>
      )}
      {record.status === "checking" && (
        <p className="recon-progress">
          <span className="recon-pulse" aria-hidden="true" />
          The Treasurer is checking the bill, its own plan and the Guardian&rsquo;s findings to see where the problem came from.
        </p>
      )}
      {record.status === "failed" && (
        <div className="recon-failed">
          <p>{record.error ?? "The cross-check did not finish."}</p>
          <button className="button button-secondary" type="button" disabled={busy} onClick={onRetry}>Try again</button>
        </div>
      )}
      {record.status === "done" && record.source && (
        <>
          <p className={`recon-source recon-source-${record.source}`}>{SOURCES[record.source]}</p>
          {record.summary && <p className="recon-summary">{record.summary}</p>}
          {record.findings && record.findings.length > 0 && (
            <ul className="recon-findings">{record.findings.map((f) => <li key={f}>{f}</li>)}</ul>
          )}
          {record.email && (
            <div className="recon-email">
              <div className="recon-email-head">
                <span>Email to <strong>{record.email.to}</strong></span>
                {record.email.simulated && <span className="intake-badge">Simulated email</span>}
              </div>
              <p className="recon-email-subject"><span>Subject</span>{record.email.subject}</p>
              <pre className="recon-email-body">{record.email.body}</pre>
              <span className="recon-email-meta">Sent {when(record.email.sent_at)}. The corrected bill comes back through bill intake and is checked again.</span>
            </div>
          )}
          {record.rerun_id && (
            <div className="recon-rerun">
              <span className="recon-rerun-label">
                Treasurer {RERUN[record.rerun_status ?? "queued"] ?? record.rerun_status}
                {record.treasurer_fix ? `: ${record.treasurer_fix}` : ""}
              </span>
              {record.rerun_summary && <p>{record.rerun_summary}</p>}
            </div>
          )}
        </>
      )}
    </section>
  );
}

async function postJson(url: string, body: unknown): Promise<Record<string, unknown>> {
  const res = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message ?? "That did not go through.");
  return data;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Every proposal the agents made, live from the engine. Approving or rejecting is recorded
 * as you (from your signed-in session) and nothing pays until you approve. Sending one back
 * rejects it and asks the Treasurer to find where the problem came from. */
export function ProposalInbox() {
  const [tab, setTab] = useState<Tab>("needs_you");
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [recons, setRecons] = useState<Record<string, Reconsideration>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [bulkNote, setBulkNote] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [res, rec] = await Promise.all([
        fetch("/api/fiona/proposals", { cache: "no-store" }),
        fetch("/api/fiona/agents/reconsiderations", { cache: "no-store" }).catch(() => null),
      ]);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Proposals could not be loaded.");
      const list = data.proposals as Proposal[];
      setProposals(list);
      setProblem(null);
      if (rec?.ok) {
        const items = ((await rec.json()).reconsiderations ?? []) as Reconsideration[];
        const latest: Record<string, Reconsideration> = {};
        for (const r of items) if (!latest[r.proposal_id]) latest[r.proposal_id] = r; // newest first
        setRecons(latest);
      }
      const open = new Set(list.filter((p) => p.status === "needs_owner").map((p) => p.id));
      setSelected((s) => new Set([...s].filter((id) => open.has(id))));
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "Proposals could not be loaded.");
    }
  }, []);

  const pending = useMemo(
    () => Object.values(recons).some((r) => r.status === "checking" || r.rerun_status === "queued" || r.rerun_status === "running"),
    [recons],
  );

  useEffect(() => {
    const first = window.setTimeout(load, 0);
    // Guardian reviews land a little after the proposal; a cross-check takes about a minute.
    const timer = window.setInterval(load, pending ? 4_000 : 15_000);
    return () => { window.clearTimeout(first); window.clearInterval(timer); };
  }, [load, pending]);

  const decide = (id: string, decision: "approve" | "reject", note: string) =>
    postJson(`/api/fiona/proposals/${id}/decision`, { decision, ...(note ? { note: note.slice(0, 1000) } : {}) });

  /** Runs one action over one or many proposals and reports what happened. */
  async function run(action: Action, ids: string[], note: string) {
    if (ids.length === 0) return;
    setBusy(ids.length === 1 ? ids[0]! : "bulk");
    setFeedback(null);
    const done: string[] = [];
    const failures: string[] = [];
    const verb = { approve: "Approving", reject: "Rejecting", reconsider: "Sending back" }[action];
    for (const [i, id] of ids.entries()) {
      if (ids.length > 1) setFeedback(`${verb} ${i + 1} of ${ids.length}…`);
      try {
        if (action === "reconsider") await decide(id, "reject", note ? `Sent back for reconsideration: ${note}` : "Sent back for reconsideration");
        else await decide(id, action, note);
        done.push(id);
      } catch (err) {
        failures.push(err instanceof Error ? err.message : "did not go through");
      }
    }
    let message = "";
    if (action === "approve") message = ids.length === 1 && done.length === 1
      ? `Approved. It pays from the sandbox wallet on ${proposals?.find((p) => p.id === ids[0])?.payload.pay_on ?? "its date"}.`
      : `${plural(done.length, "payment")} approved. Each pays from the sandbox wallet on its date.`;
    if (action === "reject") message = `${done.length === 1 ? "Rejected" : `${plural(done.length, "proposal")} rejected`}. The agent will not pay ${done.length === 1 ? "it" : "them"}.`;
    if (action === "reconsider" && done.length > 0) {
      try {
        const data = await postJson("/api/fiona/agents/reconsider", { proposal_ids: done, note });
        const skipped = (data.skipped ?? []) as Array<{ reason: string }>;
        message = `${done.length === 1 ? "Sent back" : `${plural(done.length, "proposal")} sent back`} to the Treasurer. It is cross-checking ${done.length === 1 ? "the bill" : "each bill"} now; follow it under Sent back.`;
        if (skipped.length) failures.push(...skipped.map((s) => s.reason));
        setTab("sent_back");
      } catch (err) {
        message = `Rejected, but the Treasurer could not start the cross-check: ${err instanceof Error ? err.message : "unknown error"}. Send it back again from the Rejected tab.`;
      }
    }
    if (done.length === 0) message = "";
    setFeedback([message, failures.length ? `${plural(failures.length, "item")} not done: ${[...new Set(failures)].join("; ")}` : ""].filter(Boolean).join(" "));
    setSelected(new Set());
    if (ids.length === 1) setNotes((n) => ({ ...n, [ids[0]!]: "" }));
    else setBulkNote("");
    await load();
    setBusy(null);
  }

  /** Sends an already rejected proposal (or a failed cross-check) back to the Treasurer. */
  async function sendBackAgain(id: string, note: string) {
    setBusy(id);
    setFeedback(null);
    try {
      await postJson("/api/fiona/agents/reconsider", { proposal_ids: [id], note });
      setFeedback("Sent back to the Treasurer. It is cross-checking the bill now.");
      setTab("sent_back");
      await load();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "That did not go through.");
    } finally {
      setBusy(null);
    }
  }

  async function reviewAgain(proposal: Proposal) {
    setBusy(proposal.id);
    setFeedback(null);
    try {
      await postJson(`/api/fiona/proposals/${proposal.id}/request-review`, {});
      setFeedback("The Guardian is reviewing it again.");
      await load();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "That did not go through.");
    } finally {
      setBusy(null);
    }
  }

  async function payDueToday() {
    setBusy("pay");
    setFeedback(null);
    try {
      const data = await postJson("/api/fiona/agents/pay-approved", {});
      const results = (data.results ?? []) as Array<{ status: string; reason?: string }>;
      const paid = results.filter((r) => r.status === "executed").length;
      const refused = results.filter((r) => r.status !== "executed" && r.status !== "already_executed");
      setFeedback(
        results.length === 0
          ? "Nothing approved is due today."
          : `${paid} paid from the sandbox wallet.${refused.length ? ` ${refused.length} not paid: ${refused.map((r) => r.reason ?? "refused").join("; ")}` : ""}`,
      );
      await load();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "Payments could not be sent.");
    } finally {
      setBusy(null);
    }
  }

  const byTab = (key: Tab) => (proposals ?? []).filter((p) => {
    if (key === "sent_back") return p.status === "rejected" && Boolean(recons[p.id]);
    if (key === "rejected") return p.status === "rejected" && !recons[p.id];
    return STATUSES[key].includes(p.status);
  });
  const shown = byTab(tab);
  const selectable = tab === "needs_you" ? shown.filter((p) => p.status === "needs_owner") : [];
  const allSelected = selectable.length > 0 && selectable.every((p) => selected.has(p.id));
  const someSelected = selected.size > 0 && !allSelected;
  const chosen = selectable.filter((p) => selected.has(p.id)).map((p) => p.id);

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function switchTab(next: Tab) {
    setTab(next);
    setSelected(new Set());
  }

  return (
    <div className="approvals-workbench">
      <div className="approvals-nav-bar" role="tablist">
        {TABS.map((t) => {
          const count = byTab(t.key).length;
          return (
            <button
              key={t.key}
              className={`approvals-tab-btn ${tab === t.key ? "tab-active" : ""}`}
              onClick={() => switchTab(t.key)}
              role="tab"
              aria-selected={tab === t.key}
            >
              <span className="tab-icon">{t.icon}</span>
              <span className="tab-label">{t.label}</span>
              <span className={`tab-counter ${t.key === "needs_you" && count > 0 ? "counter-attention" : t.key === "blocked" && count > 0 ? "counter-danger" : t.key === "approved" ? "counter-success" : ""}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {feedback && (
        <div className="approvals-toast" role="status">
          <span className="toast-bullet">●</span>
          <span>{feedback}</span>
        </div>
      )}

      {selectable.length > 1 && (
        <label className="bulk-select-all">
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => { if (el) el.indeterminate = someSelected; }}
            onChange={() => setSelected(allSelected ? new Set() : new Set(selectable.map((p) => p.id)))}
            disabled={busy !== null}
          />
          <span>{allSelected ? "All selected" : `Select all ${selectable.length}`}</span>
        </label>
      )}

      <div className="approvals-stream">
        {problem && (
          <Card className="empty-panel-card">
            <EmptyState title="Proposals could not be loaded">{problem}</EmptyState>
          </Card>
        )}
        {!problem && proposals === null && (
          <div className="sk-skeleton-list" role="status" aria-label="Loading proposals">{[0, 1, 2].map((i) => <div key={i} className="sk-skeleton-card" style={{ animationDelay: `${i * 120}ms` }}><span /><span /><span /></div>)}<span className="sr-only">Reading the ledger…</span></div>
        )}
        {!problem && proposals !== null && shown.length === 0 && (
          <Card className="empty-panel-card">
            <EmptyState title={tab === "needs_you" ? "Nothing waits for you" : tab === "sent_back" ? "Nothing sent back" : "Nothing here yet"}>
              {tab === "needs_you"
                ? "When the Treasurer plans payments they appear here, checked by the Guardian. Run the team from the agents panel."
                : tab === "sent_back"
                  ? "Use Reconsider on a payment to send it back with a note. The Treasurer checks whether the mistake was its own or on the supplier's bill, and acts on it."
                  : "Proposals move here as you decide on them."}
            </EmptyState>
          </Card>
        )}

        {shown.map((p, index) => {
          const canSelect = tab === "needs_you" && p.status === "needs_owner";
          const recon = recons[p.id];
          const card = (
            <Card key={p.id} className={`approval-luxury-card sk-rise ${selected.has(p.id) ? "approval-selected" : ""}`} style={{ "--d": `${Math.min(index, 6) * 50}ms` } as CSSProperties}>
              <div className="approval-card-header">
                <div className="approval-card-badges">
                  <span className={`agent-pill agent-${p.agent}`}>{AGENTS[p.agent] ?? p.agent}</span>
                  <span className="type-pill">{p.type.replaceAll("_", " ")}</span>
                  <span className="date-pill">{when(p.created_at)}</span>
                </div>
                <div className="approval-amount-block">
                  <span className="amount-label">Amount</span>
                  <strong className="approval-money">
                    {p.amount ? <MoneyText amountMinor={p.amount.minor} currency={p.amount.currency} animateCount={false} /> : "—"}
                  </strong>
                </div>
              </div>

              <div className="approval-card-body">
                <h3 className="approval-title">{p.summary}</h3>
                <p className="approval-rationale"><strong>{AGENTS[p.agent] ?? p.agent}&rsquo;s reasoning:</strong> {p.reasoning}</p>
                <div className="approval-specs-grid">
                  {p.payload.payee_id && (
                    <div className="spec-item">
                      <span className="spec-label">Payee</span>
                      <strong className="spec-value">{p.payload.payee_id}</strong>
                    </div>
                  )}
                  {p.payload.bill_id && (
                    <div className="spec-item">
                      <span className="spec-label">Bill · pays on</span>
                      <code className="spec-code">{p.payload.bill_id} · {p.payload.pay_on ?? "—"}</code>
                    </div>
                  )}
                  <GuardianSection proposal={p} />
                </div>
                {recon && <ReconsiderationPanel record={recon} busy={busy !== null} onRetry={() => sendBackAgain(p.id, recon.note)} />}
              </div>

              <div className="approval-card-footer">
                <div className="approval-footer-left">
                  <span className="status-indicator">
                    {p.status === "needs_owner" && "Waiting for your decision"}
                    {p.status === "submitted" && "The Guardian is checking it"}
                    {p.status === "blocked" && "Blocked: no approval can release it"}
                    {p.status === "approved" && "Approved by you · pays on its date"}
                    {p.status === "cleared" && "Cleared to pay within the mandate"}
                    {p.status === "executed" && "Paid from the sandbox wallet"}
                    {p.status === "rejected" && (recon ? "Rejected and sent back to the Treasurer" : "Rejected by you")}
                  </span>
                </div>
                <div className="approval-footer-actions">
                  {p.status === "needs_owner" && (
                    <>
                      <input
                        className="approval-note"
                        aria-label="Note for the audit trail and the Treasurer"
                        placeholder="Note (optional)"
                        maxLength={900}
                        value={notes[p.id] ?? ""}
                        onChange={(e) => setNotes((n) => ({ ...n, [p.id]: e.target.value }))}
                      />
                      <button className="button button-quiet" type="button" disabled={busy !== null} onClick={() => reviewAgain(p)}>
                        Review again
                      </button>
                      <button
                        className="button button-secondary action-reconsider"
                        type="button"
                        disabled={busy !== null}
                        title="Reject it and send it back to the Treasurer with your note. The Treasurer checks whether the mistake was its own or on the supplier's bill."
                        onClick={() => run("reconsider", [p.id], (notes[p.id] ?? "").trim())}
                      >
                        Reconsider
                      </button>
                      <button className="button button-danger action-reject" type="button" disabled={busy !== null} onClick={() => run("reject", [p.id], (notes[p.id] ?? "").trim())}>
                        Reject
                      </button>
                      <button className="button button-primary action-approve" type="button" disabled={busy !== null} onClick={() => run("approve", [p.id], (notes[p.id] ?? "").trim())}>
                        {busy === p.id ? "Recording…" : "Approve"}
                      </button>
                    </>
                  )}
                  {p.status === "rejected" && !recon && (
                    <button className="button button-secondary action-reconsider" type="button" disabled={busy !== null} onClick={() => sendBackAgain(p.id, "")}>
                      Send back to the Treasurer
                    </button>
                  )}
                  <Link className="button button-secondary" href={`/proposals/${p.id}`}>Full trail</Link>
                </div>
              </div>
            </Card>
          );
          return canSelect ? (
            <div key={p.id} className="approval-row">
              <label className="approval-select">
                <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} disabled={busy !== null} aria-label={`Select: ${p.summary}`} />
              </label>
              {card}
            </div>
          ) : card;
        })}
      </div>

      {chosen.length > 0 && (
        <div className="bulk-bar" role="region" aria-label="Decide on the selected payments">
          <span className="bulk-count">{chosen.length} selected</span>
          <input
            className="approval-note bulk-note"
            aria-label="Note for every selected payment"
            placeholder="Note for all selected (optional)"
            maxLength={900}
            value={bulkNote}
            onChange={(e) => setBulkNote(e.target.value)}
          />
          <div className="bulk-actions">
            <button className="button button-quiet" type="button" disabled={busy !== null} onClick={() => setSelected(new Set())}>Clear</button>
            <button className="button button-secondary action-reconsider" type="button" disabled={busy !== null} onClick={() => run("reconsider", chosen, bulkNote.trim())}>
              Reconsider {chosen.length}
            </button>
            <button className="button button-danger action-reject" type="button" disabled={busy !== null} onClick={() => run("reject", chosen, bulkNote.trim())}>
              Reject {chosen.length}
            </button>
            <button className="button button-primary action-approve" type="button" disabled={busy !== null} onClick={() => run("approve", chosen, bulkNote.trim())}>
              {busy === "bulk" ? "Working…" : `Approve ${chosen.length}`}
            </button>
          </div>
        </div>
      )}

      {tab === "approved" && (
        <Card className="proposal-intake-card">
          <div className="intake-header">
            <div>
              <span className="eyebrow">SANDBOX WALLET</span>
              <h2>Send approved payments due today</h2>
            </div>
            <span className="intake-badge">Simulated money</span>
          </div>
          <p className="intake-desc">
            The wallet pays only what you approved, on its date, and checks the Guardian&rsquo;s verdict, your decision and every limit again before it moves anything.
          </p>
          <div className="intake-actions">
            <button className="button button-primary" type="button" disabled={busy !== null} onClick={payDueToday}>
              {busy === "pay" ? "Sending…" : "Pay what is due today"}
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
