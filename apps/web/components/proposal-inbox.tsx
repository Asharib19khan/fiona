"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Card, EmptyState, MoneyText } from "@fiona/ui";

type Tab = "needs_you" | "blocked" | "approved" | "rejected";

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

const AGENTS: Record<string, string> = {
  treasurer: "Treasurer",
  controller: "Controller",
  cfo_strategist: "CFO Strategist",
  growth_analyst: "Growth Analyst",
};

const REVIEWED = new Set(["payment", "bill_approval", "journal_adjustment", "send_document", "purchase_order"]);

const TABS: Array<{ key: Tab; label: string; icon: string; statuses: string[] }> = [
  { key: "needs_you", label: "Needs your decision", icon: "▣", statuses: ["needs_owner", "submitted"] },
  { key: "blocked", label: "Blocked by the Guardian", icon: "✕", statuses: ["blocked"] },
  { key: "approved", label: "Approved & paid", icon: "✓", statuses: ["approved", "cleared", "executed"] },
  { key: "rejected", label: "Rejected", icon: "↺", statuses: ["rejected"] },
];

function when(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Karachi" }).format(new Date(iso));
}

function GuardianSection({ proposal }: { proposal: Proposal }) {
  const checks = proposal.verdict?.checks ?? [];
  const failed = checks.filter((c) => c.outcome !== "approve");
  const review = checks.find((c) => c.rule === "G-12");
  const passed = checks.length - failed.length;
  return (
    <div className="spec-item spec-guardian-item">
      <span className="spec-label">
        Guardian verdict: {proposal.verdict ? proposal.verdict.outcome.replaceAll("_", " ") : "not yet checked"}
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
          {review.audit?.reasons && review.audit.reasons.length > 0 && (
            <ul>{review.audit.reasons.slice(0, 4).map((r) => <li key={r}>{r}</li>)}</ul>
          )}
          {review.detail.startsWith("CHECK_ERROR") && <p>{review.detail}</p>}
        </div>
      ) : REVIEWED.has(proposal.type) && proposal.status !== "executed" ? (
        <p className="guardian-review guardian-review-pending">Independent review in progress…</p>
      ) : null}
    </div>
  );
}

/** Every proposal the agents made, live from the engine. Approving or rejecting is recorded
 * as you (from your signed-in session) and nothing pays until you approve. */
export function ProposalInbox() {
  const [tab, setTab] = useState<Tab>("needs_you");
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/fiona/proposals", { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Proposals could not be loaded.");
      setProposals(data.proposals as Proposal[]);
      setProblem(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "Proposals could not be loaded.");
    }
  }, []);

  useEffect(() => {
    const first = window.setTimeout(load, 0);
    const timer = window.setInterval(load, 15_000); // Guardian reviews land a little after the proposal
    return () => { window.clearTimeout(first); window.clearInterval(timer); };
  }, [load]);

  async function act(proposal: Proposal, action: "approve" | "reject" | "review") {
    setBusy(proposal.id);
    setFeedback(null);
    try {
      const url = action === "review" ? `/api/fiona/proposals/${proposal.id}/request-review` : `/api/fiona/proposals/${proposal.id}/decision`;
      const body = action === "review" ? {} : { decision: action, ...(notes[proposal.id]?.trim() ? { note: notes[proposal.id]!.trim() } : {}) };
      const res = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "That did not go through.");
      setFeedback(
        action === "review"
          ? "The Guardian is reviewing it again."
          : action === "approve"
            ? `Approved. It pays from the sandbox wallet on ${proposal.payload.pay_on ?? "its date"}.`
            : "Rejected. The agent will not pay it.",
      );
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
      const res = await fetch("/api/fiona/agents/pay-approved", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Payments could not be sent.");
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

  const byTab = (key: Tab) => (proposals ?? []).filter((p) => TABS.find((t) => t.key === key)!.statuses.includes(p.status));
  const shown = byTab(tab);

  return (
    <div className="approvals-workbench">
      <div className="approvals-nav-bar" role="tablist">
        {TABS.map((t) => {
          const count = byTab(t.key).length;
          return (
            <button
              key={t.key}
              className={`approvals-tab-btn ${tab === t.key ? "tab-active" : ""}`}
              onClick={() => setTab(t.key)}
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

      <div className="approvals-stream">
        {problem && (
          <Card className="empty-panel-card">
            <EmptyState title="Proposals could not be loaded">{problem}</EmptyState>
          </Card>
        )}
        {!problem && proposals === null && (
          <Card className="empty-panel-card"><EmptyState title="Loading proposals">Reading the ledger…</EmptyState></Card>
        )}
        {!problem && proposals !== null && shown.length === 0 && (
          <Card className="empty-panel-card">
            <EmptyState title={tab === "needs_you" ? "Nothing waits for you" : "Nothing here yet"}>
              {tab === "needs_you"
                ? "When the Treasurer plans payments they appear here, checked by the Guardian. Run the team from the agents panel."
                : "Proposals move here as you decide on them."}
            </EmptyState>
          </Card>
        )}

        {shown.map((p) => (
          <Card key={p.id} className="approval-luxury-card">
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
                  {p.status === "rejected" && "Rejected by you"}
                </span>
              </div>
              <div className="approval-footer-actions">
                {p.status === "needs_owner" && (
                  <>
                    <input
                      className="approval-note"
                      aria-label="Note for the audit trail"
                      placeholder="Note (optional)"
                      maxLength={1000}
                      value={notes[p.id] ?? ""}
                      onChange={(e) => setNotes((n) => ({ ...n, [p.id]: e.target.value }))}
                    />
                    <button className="button button-quiet" type="button" disabled={busy !== null} onClick={() => act(p, "review")}>
                      Review again
                    </button>
                    <button className="button button-danger action-reject" type="button" disabled={busy !== null} onClick={() => act(p, "reject")}>
                      Reject
                    </button>
                    <button className="button button-primary action-approve" type="button" disabled={busy !== null} onClick={() => act(p, "approve")}>
                      {busy === p.id ? "Recording…" : "Approve"}
                    </button>
                  </>
                )}
                {(p.status === "approved" || p.status === "executed" || p.status === "blocked" || p.status === "rejected") && (
                  <Link className="button button-secondary" href={`/audit?proposal_id=${p.id}`}>Audit trail</Link>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

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
