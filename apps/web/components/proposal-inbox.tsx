"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, EmptyState, MoneyText, OutcomeBadge, StateChip } from "@fiona/ui";
import type { MockProposalRecord } from "@/lib/mock-api";

type ApprovalTab = "unread" | "reconsideration" | "rejected" | "approved";

interface ProposalItem {
  id: string;
  agent: string;
  type: string;
  summary: string;
  reasoning: string;
  payee: string;
  iban?: string;
  amountMinor: number;
  currency: string;
  status: ApprovalTab;
  guardianRulesChecked: string[];
  guardianVerdict: "approve" | "block" | "review";
  date: string;
  urgency: "high" | "normal" | "low";
}

const INITIAL_PROPOSALS: ProposalItem[] = [
  {
    id: "prop_9912_raw_cotton",
    agent: "Treasurer",
    type: "Vendor Payment",
    summary: "Discharge raw cotton yarn invoice INV-2231 to Gul Ahmed Mills",
    reasoning: "2/10 net 30 payment capture yielding 44.59% APR annualized return. Cash remains PKR 46M above buffer.",
    payee: "Gul Ahmed Textile Mills Ltd.",
    iban: "PK36SCBL0000001123456701",
    amountMinor: 12_000_000,
    currency: "PKR",
    status: "unread",
    guardianRulesChecked: ["G-01 (Zero Float Math)", "G-03 (Bank Detail Match)", "G-08 (Mandate Cap)"],
    guardianVerdict: "approve",
    date: "Today, 10:14 AM",
    urgency: "high",
  },
  {
    id: "prop_9914_bulk_dye",
    agent: "Controller",
    type: "Reorder Authorization",
    summary: "Procure Reactive Blue 19 reactive dyes for Fall Collection",
    reasoning: "Stock depletion forecast within 11 operating days. Reorder point triggered at EOQ optimum.",
    payee: "Dawood Chemicals Pvt Ltd.",
    iban: "PK82MCB00123984712093412",
    amountMinor: 4_850_000,
    currency: "PKR",
    status: "unread",
    guardianRulesChecked: ["G-01 (Arithmetic Verification)", "G-08 (Cap Clearance)"],
    guardianVerdict: "approve",
    date: "Today, 09:30 AM",
    urgency: "normal",
  },
  {
    id: "prop_9908_working_cap",
    agent: "CFO Strategist",
    type: "Financing Restructure",
    summary: "SBP SME Export Refinance Scheme vs. Supplier Credit Extension",
    reasoning: "Council debate open: CFO favors SBP 6% concessionary facility; Treasurer urges supplier credit to avoid debt service.",
    payee: "State Bank of Pakistan / Partner Bank",
    amountMinor: 20_000_000,
    currency: "PKR",
    status: "reconsideration",
    guardianRulesChecked: ["G-14 (Regulatory Sanctions)", "G-15 (Capital Preservation)"],
    guardianVerdict: "review",
    date: "Yesterday, 04:15 PM",
    urgency: "normal",
  },
  {
    id: "prop_planted_bill_tamper",
    agent: "Controller",
    type: "Vendor Payment",
    summary: "Planted Attack: Altered Account & Duplicate Bill INV-2231",
    reasoning: "Interception alert: Recipient account mismatch detected against historical verified vendor profile.",
    payee: "Unverified Intermediary Corp",
    iban: "PK99HABB0099881122334455",
    amountMinor: 18_450_000,
    currency: "PKR",
    status: "rejected",
    guardianRulesChecked: ["G-03 (Bank Details Verification: FAILED)", "G-12 (Adversarial Prompt Defense: FLAGGED)"],
    guardianVerdict: "block",
    date: "16 Oct 2026, 02:40 PM",
    urgency: "high",
  },
  {
    id: "prop_over_cap_order",
    agent: "Growth Analyst",
    type: "Equipment Capex",
    summary: "High-speed computerized embroidery machine purchase",
    reasoning: "Requested amount exceeds the autonomous growth mandate limit of PKR 50M without Board clearance.",
    payee: "Tajima Industrial Machinery Co.",
    amountMinor: 65_000_000,
    currency: "PKR",
    status: "rejected",
    guardianRulesChecked: ["G-08 (Autonomous Spending Cap: EXCEEDED)"],
    guardianVerdict: "block",
    date: "15 Oct 2026, 11:10 AM",
    urgency: "normal",
  },
  {
    id: "prop_9891_utility_k_electric",
    agent: "Treasurer",
    type: "Fixed Operating Expense",
    summary: "Monthly industrial grid electricity bill settlement",
    reasoning: "Matched against automated utility portal metering. Cleared under automated utility mandate.",
    payee: "K-Electric Karachi Industrial Grid",
    iban: "PK11HABB0001002003004005",
    amountMinor: 3_420_000,
    currency: "PKR",
    status: "approved",
    guardianRulesChecked: ["G-01 (Arithmetic)", "G-03 (Authorized Payee)", "G-08 (Within Cap)"],
    guardianVerdict: "approve",
    date: "14 Oct 2026, 09:00 AM",
    urgency: "low",
  },
  {
    id: "prop_9888_weekly_payroll",
    agent: "Controller",
    type: "Direct Salary Disbursement",
    summary: "Weekly manufacturing plant floor payroll tranche",
    reasoning: "Fully reconciled against biometric attendance logs and approved wage registry.",
    payee: "Karachi Apparel Payroll Disbursement Vault",
    amountMinor: 14_100_000,
    currency: "PKR",
    status: "approved",
    guardianRulesChecked: ["G-01 (Reconciliation 0-Diff)", "G-08 (Pre-approved Payroll Schedule)"],
    guardianVerdict: "approve",
    date: "12 Oct 2026, 08:30 AM",
    urgency: "high",
  },
];

export function ProposalInbox({ initial, mockEnabled }: { initial: MockProposalRecord[]; mockEnabled: boolean }) {
  const [activeTab, setActiveTab] = useState<ApprovalTab>("unread");
  const [proposals, setProposals] = useState<ProposalItem[]>(INITIAL_PROPOSALS);
  const [feedback, setFeedback] = useState<string | null>(null);

  const counts = {
    unread: proposals.filter((p) => p.status === "unread").length,
    reconsideration: proposals.filter((p) => p.status === "reconsideration").length,
    rejected: proposals.filter((p) => p.status === "rejected").length,
    approved: proposals.filter((p) => p.status === "approved").length,
  };

  const filteredProposals = proposals.filter((p) => p.status === activeTab);

  function transitionStatus(id: string, newStatus: ApprovalTab, notice: string) {
    setProposals((prev) => prev.map((p) => (p.id === id ? { ...p, status: newStatus } : p)));
    setFeedback(notice);
    setTimeout(() => setFeedback(null), 3500);
  }

  return (
    <div className="approvals-workbench">
      {/* 4 Primary Navigation Tabs */}
      <div className="approvals-nav-bar" role="tablist">
        <button
          className={`approvals-tab-btn ${activeTab === "unread" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("unread")}
          role="tab"
          aria-selected={activeTab === "unread"}
        >
          <span className="tab-icon">▣</span>
          <span className="tab-label">Unread & Pending</span>
          <span className={`tab-counter ${counts.unread > 0 ? "counter-attention" : ""}`}>{counts.unread}</span>
        </button>

        <button
          className={`approvals-tab-btn ${activeTab === "reconsideration" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("reconsideration")}
          role="tab"
          aria-selected={activeTab === "reconsideration"}
        >
          <span className="tab-icon">↺</span>
          <span className="tab-label">Reconsideration</span>
          <span className="tab-counter">{counts.reconsideration}</span>
        </button>

        <button
          className={`approvals-tab-btn ${activeTab === "rejected" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("rejected")}
          role="tab"
          aria-selected={activeTab === "rejected"}
        >
          <span className="tab-icon">✕</span>
          <span className="tab-label">Rejected & Blocked</span>
          <span className={`tab-counter ${counts.rejected > 0 ? "counter-danger" : ""}`}>{counts.rejected}</span>
        </button>

        <button
          className={`approvals-tab-btn ${activeTab === "approved" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("approved")}
          role="tab"
          aria-selected={activeTab === "approved"}
        >
          <span className="tab-icon">✓</span>
          <span className="tab-label">Approved & Cleared</span>
          <span className="tab-counter counter-success">{counts.approved}</span>
        </button>
      </div>

      {feedback && (
        <div className="approvals-toast" role="status">
          <span className="toast-bullet">●</span>
          <span>{feedback}</span>
        </div>
      )}

      {/* Main Approvals List */}
      <div className="approvals-stream">
        {filteredProposals.length > 0 ? (
          filteredProposals.map((item) => (
            <Card key={item.id} className="approval-luxury-card">
              <div className="approval-card-header">
                <div className="approval-card-badges">
                  <span className={`agent-pill agent-${item.agent.toLowerCase()}`}>{item.agent}</span>
                  <span className="type-pill">{item.type}</span>
                  <span className="date-pill">{item.date}</span>
                </div>
                <div className="approval-amount-block">
                  <span className="amount-label">Authorized Amount</span>
                  <strong className="approval-money">
                    <MoneyText amountMinor={item.amountMinor} currency={item.currency} />
                  </strong>
                </div>
              </div>

              <div className="approval-card-body">
                <h3 className="approval-title">{item.summary}</h3>
                <p className="approval-rationale">{item.reasoning}</p>

                <div className="approval-specs-grid">
                  <div className="spec-item">
                    <span className="spec-label">Verified Payee</span>
                    <strong className="spec-value">{item.payee}</strong>
                  </div>
                  {item.iban && (
                    <div className="spec-item">
                      <span className="spec-label">Destination IBAN</span>
                      <code className="spec-code">{item.iban}</code>
                    </div>
                  )}
                  <div className="spec-item spec-guardian-item">
                    <span className="spec-label">Guardian Invariant Gauntlet</span>
                    <div className="guardian-chips">
                      {item.guardianRulesChecked.map((rule) => (
                        <span
                          key={rule}
                          className={`guardian-chip ${rule.includes("FAILED") || rule.includes("FLAGGED") ? "chip-failed" : "chip-ok"}`}
                        >
                          {rule}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Bar based on Tab */}
              <div className="approval-card-footer">
                <div className="approval-footer-left">
                  <span className="status-indicator">
                    {item.status === "unread" && "⚡ Requires Human Executive Sign-off"}
                    {item.status === "reconsideration" && "⏳ Council Deliberation Active"}
                    {item.status === "rejected" && "🛑 Intercepted by Guardian Invariant Ring"}
                    {item.status === "approved" && "🔒 Cryptographically Sealed · Ready for Settlement"}
                  </span>
                </div>

                <div className="approval-footer-actions">
                  {item.status === "unread" && (
                    <>
                      <button
                        className="button button-secondary action-reconsider"
                        type="button"
                        onClick={() => transitionStatus(item.id, "reconsideration", `Proposal ${item.id} routed to Council for reconsideration.`)}
                      >
                        Request Reconsideration
                      </button>
                      <button
                        className="button button-danger action-reject"
                        type="button"
                        onClick={() => transitionStatus(item.id, "rejected", `Proposal ${item.id} rejected and logged in security register.`)}
                      >
                        Reject
                      </button>
                      <button
                        className="button button-primary action-approve"
                        type="button"
                        onClick={() => transitionStatus(item.id, "approved", `Proposal ${item.id} approved and signed via verified session.`)}
                      >
                        Approve & Sign →
                      </button>
                    </>
                  )}

                  {item.status === "reconsideration" && (
                    <>
                      <button
                        className="button button-danger"
                        type="button"
                        onClick={() => transitionStatus(item.id, "rejected", `Deliberation terminated: ${item.id} rejected.`)}
                      >
                        Terminate & Reject
                      </button>
                      <button
                        className="button button-primary"
                        type="button"
                        onClick={() => transitionStatus(item.id, "approved", `Revised terms accepted: ${item.id} approved.`)}
                      >
                        Accept Revised Terms →
                      </button>
                    </>
                  )}

                  {item.status === "rejected" && (
                    <>
                      <Link className="button button-secondary" href="/audit">
                        View Interception Telemetry
                      </Link>
                      <button
                        className="button button-quiet"
                        type="button"
                        onClick={() => transitionStatus(item.id, "unread", `Proposal ${item.id} returned to pending queue for re-evaluation.`)}
                      >
                        Re-evaluate Case
                      </button>
                    </>
                  )}

                  {item.status === "approved" && (
                    <>
                      <Link className="button button-secondary" href="/wallet">
                        Inspect Sandbox Vault Dispatch
                      </Link>
                      <Link className="button button-quiet" href="/audit">
                        RFC 8785 Hash Receipt ↗
                      </Link>
                    </>
                  )}
                </div>
              </div>
            </Card>
          ))
        ) : (
          <Card className="empty-panel-card">
            <EmptyState title={`No proposals in ${activeTab}`}>
              There are currently zero entries waiting under this state filter. All policy invariants are operating smoothly.
            </EmptyState>
          </Card>
        )}
      </div>

      {/* New Proposal Fast-Dispatcher Drawer */}
      <Card className="proposal-intake-card">
        <div className="intake-header">
          <div>
            <span className="eyebrow">AUTONOMOUS INTAKE ENGINE</span>
            <h2>Dispatch Financial Proposal to Guardian</h2>
          </div>
          <span className="intake-badge">Zero Float Math Enforced</span>
        </div>
        <p className="intake-desc">
          Propose an emergency or scheduled liquidity dispatch. Every proposed payload passes through the 15 Guardian invariant checks (arithmetic verification, bank detail change protection, mandate caps, and adversarial prompt defense) before committing to the ledger.
        </p>
        <div className="intake-actions">
          <button
            className="button button-primary"
            type="button"
            onClick={() => {
              const newProp: ProposalItem = {
                id: `prop_${Date.now().toString(36)}`,
                agent: "Treasurer",
                type: "Manual Fast-Dispatch",
                summary: "Emergency Working Capital Allocation to Dawood Yarn Distributors",
                reasoning: "Immediate raw material yarn batch booking to lock in early-bird discount (44.6% APR).",
                payee: "Dawood Yarn Distributors Ltd.",
                iban: "PK44MEZN0001928374655647",
                amountMinor: 8_500_000,
                currency: "PKR",
                status: "unread",
                guardianRulesChecked: ["G-01 (Arithmetic: Clean)", "G-03 (Bank Detail: Matched)", "G-08 (Mandate Cap: Within Limits)"],
                guardianVerdict: "approve",
                date: "Just now",
                urgency: "high",
              };
              setProposals((prev) => [newProp, ...prev]);
              setActiveTab("unread");
              setFeedback("New proposal dispatched and queued in Unread & Pending.");
              setTimeout(() => setFeedback(null), 3500);
            }}
          >
            + Dispatch New Financial Proposal
          </button>
        </div>
      </Card>
    </div>
  );
}
