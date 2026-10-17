"use client";

import { useState } from "react";
import { Card, MoneyText, OutcomeBadge, StateChip, VerdictPanel } from "@fiona/ui";

interface TestScenario {
  id: string;
  name: string;
  proposer: string;
  payee: string;
  iban: string;
  amountMinor: number;
  description: string;
  expectedOutcome: "approve" | "block" | "escalate";
  checks: Array<{
    rule: string;
    name: string;
    outcome: "approve" | "conditions" | "escalate" | "block";
    detail: string;
  }>;
}

const SCENARIOS: TestScenario[] = [
  {
    id: "clean-bill",
    name: "Clean Vendor Payment",
    proposer: "accountant_bill",
    payee: "Gul Ahmed Fabric Mills",
    iban: "PK36SCBL0000001123456701",
    amountMinor: 120_000_00, // PKR 120,000
    description: "Scheduled payment for raw cotton yarn. Verified invoice, vendor on approved list, well under mandate caps.",
    expectedOutcome: "approve",
    checks: [
      { rule: "G-01", name: "Mandate limit check", outcome: "approve", detail: "PKR 120,000 is under the PKR 150,000 single transaction cap." },
      { rule: "G-02", name: "Liquidity buffer check", outcome: "approve", detail: "13-week forecast remains above PKR 2,000,000 policy buffer." },
      { rule: "G-03", name: "Bank details age check", outcome: "approve", detail: "Payee account verified > 90 days ago. No recent changes." },
      { rule: "G-05", name: "Duplicate invoice check", outcome: "approve", detail: "Invoice GA-2026-8812 is unique across all posted events." },
      { rule: "G-08", name: "Arithmetic verification", outcome: "approve", detail: "Line items sum matches invoice total exactly." },
    ],
  },
  {
    id: "planted-bill",
    name: "Planted Attack: Altered Account & Duplicate",
    proposer: "accountant_bill",
    payee: "Al-Rehman Textiles",
    iban: "PK99HABB00009988776655", // altered
    amountMinor: 184_500_00, // PKR 184,500
    description: "Simulated security scenario: Duplicate invoice reference with an IBAN changed 18 hours ago.",
    expectedOutcome: "block",
    checks: [
      { rule: "G-01", name: "Mandate limit check", outcome: "escalate", detail: "Exceeds PKR 150,000 single payment limit." },
      { rule: "G-03", name: "Bank details age check", outcome: "block", detail: "PAYEE IBAN CHANGED 18 HOURS AGO (< 72h security quarantine)." },
      { rule: "G-05", name: "Duplicate invoice check", outcome: "block", detail: "DUPLICATE: Bill INV-2026-0419 was already paid on 2026-10-04." },
      { rule: "G-08", name: "Arithmetic verification", outcome: "approve", detail: "Internal tax and line item calculation is valid." },
    ],
  },
  {
    id: "over-cap",
    name: "Over-Cap Seasonal Order",
    proposer: "growth_inventory",
    payee: "Karachi Yarn Wholesalers",
    iban: "PK45MEZN0000002233445566",
    amountMinor: 650_000_00, // PKR 650,000
    description: "Bulk purchase order for winter shawls. Valid vendor, but amount exceeds autonomous agent mandate.",
    expectedOutcome: "escalate",
    checks: [
      { rule: "G-01", name: "Mandate limit check", outcome: "escalate", detail: "PKR 650,000 exceeds PKR 150,000 autonomous mandate. Requires Owner approval." },
      { rule: "G-02", name: "Liquidity buffer check", outcome: "escalate", detail: "Reduces forecast week 7 cash to PKR 1.4m (below PKR 2.0m buffer)." },
      { rule: "G-03", name: "Bank details age check", outcome: "approve", detail: "Account in good standing since 2024." },
      { rule: "G-05", name: "Duplicate invoice check", outcome: "approve", detail: "Unique purchase order." },
    ],
  },
];

export function WalletStation() {
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("clean-bill");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [stepIndex, setStepIndex] = useState<number>(0);
  const [lastReceipt, setLastReceipt] = useState<{
    scenarioId: string;
    outcome: "approve" | "block" | "escalate";
    hash: string;
    seq: number;
    timestamp: string;
  } | null>(null);

  const activeScenario: TestScenario = SCENARIOS.find((s) => s.id === selectedScenarioId) ?? (SCENARIOS[0] as TestScenario);

  async function runSimulation() {
    setIsRunning(true);
    setStepIndex(1); // Step 1: Proposal Intake
    await new Promise((r) => setTimeout(r, 450));
    setStepIndex(2); // Step 2: Guardian Evaluation
    await new Promise((r) => setTimeout(r, 600));
    setStepIndex(3); // Step 3: Mandate Check
    await new Promise((r) => setTimeout(r, 450));
    setStepIndex(4); // Step 4: Dispatch Decision
    await new Promise((r) => setTimeout(r, 400));
    setStepIndex(5); // Step 5: Audit Hash Generation

    const fakeHash = Array.from({ length: 64 }, () =>
      Math.floor(Math.random() * 16).toString(16)
    ).join("");

    setLastReceipt({
      scenarioId: activeScenario.id,
      outcome: activeScenario.expectedOutcome,
      hash: fakeHash,
      seq: Math.floor(1000 + Math.random() * 9000),
      timestamp: new Date().toISOString(),
    });

    setIsRunning(false);
  }

  return (
    <div className="wallet-station-interactive">
      {/* Scenario Selector */}
      <Card className="tier-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">SANDBOX TESTBENCH</span>
            <h2>Guardian Gatekeeper &amp; Simulated Wallet Dispatch</h2>
          </div>
          <span className="placeholder-tag">ZERO REAL MONEY MOVES</span>
        </div>

        <div className="scenario-selector-bar">
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`scenario-choice-btn ${s.id === selectedScenarioId ? "active" : ""}`}
              onClick={() => {
                setSelectedScenarioId(s.id);
                setStepIndex(0);
                setLastReceipt(null);
              }}
            >
              <span className="scenario-btn-title">{s.name}</span>
              <span className="scenario-btn-amount">
                <MoneyText amountMinor={s.amountMinor} />
              </span>
              <OutcomeBadge outcome={s.expectedOutcome === "approve" ? "approve" : s.expectedOutcome === "block" ? "block" : "escalate"} />
            </button>
          ))}
        </div>

        <div className="scenario-details-box">
          <div className="scenario-facts-row">
            <div>
              <span className="eyebrow">PROPOSED PAYEE</span>
              <strong>{activeScenario.payee}</strong>
              <small className="footnote">IBAN: {activeScenario.iban}</small>
            </div>
            <div>
              <span className="eyebrow">DISPATCH AMOUNT</span>
              <strong><MoneyText amountMinor={activeScenario.amountMinor} /></strong>
            </div>
            <div>
              <span className="eyebrow">PROPOSING AGENT</span>
              <strong>{activeScenario.proposer}</strong>
            </div>
          </div>
          <p className="scenario-desc">{activeScenario.description}</p>

          <div className="run-action-bar">
            <button
              type="button"
              className="button button-primary"
              disabled={isRunning}
              onClick={runSimulation}
            >
              {isRunning ? "Simulating Pipeline…" : "Dispatch to Guardian & Wallet"}
            </button>
            <span className="footnote">
              Evaluates 15 Guardian rules before submitting to the cryptographic ledger.
            </span>
          </div>
        </div>
      </Card>

      {/* Pipeline Stepper */}
      <Card className="tier-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">CRYPTOGRAPHIC PIPELINE</span>
            <h2>5-Stage Execution Flow</h2>
          </div>
          <StateChip>
            {stepIndex === 0
              ? "Ready"
              : isRunning
              ? `Running Stage ${stepIndex} / 5`
              : "Completed"}
          </StateChip>
        </div>

        <ol className="wallet-pipeline-steps">
          <li className={`pipeline-step ${stepIndex >= 1 ? "step-active" : ""}`}>
            <span className="step-num">1</span>
            <div>
              <strong>Typed Proposal Intake</strong>
              <span>Validates schema, origin hashes and currency precision</span>
            </div>
          </li>
          <li className={`pipeline-step ${stepIndex >= 2 ? "step-active" : ""}`}>
            <span className="step-num">2</span>
            <div>
              <strong>Guardian Rule Verification</strong>
              <span>Runs 15 security, duplicate, and liquidity checks</span>
            </div>
          </li>
          <li className={`pipeline-step ${stepIndex >= 3 ? "step-active" : ""}`}>
            <span className="step-num">3</span>
            <div>
              <strong>Owner Mandate Gate</strong>
              <span>Enforces single-payment (PKR 150k) and daily (PKR 450k) caps</span>
            </div>
          </li>
          <li className={`pipeline-step ${stepIndex >= 4 ? "step-active" : ""}`}>
            <span className="step-num">4</span>
            <div>
              <strong>Wallet Simulated Dispatch</strong>
              <span>Only clears if Guardian gave unconditional APPROVE</span>
            </div>
          </li>
          <li className={`pipeline-step ${stepIndex >= 5 ? "step-active" : ""}`}>
            <span className="step-num">5</span>
            <div>
              <strong>Append-Only Audit Receipt</strong>
              <span>Emits SHA-256 hash linked to previous ledger block</span>
            </div>
          </li>
        </ol>
      </Card>

      {/* Result Panel */}
      {lastReceipt && (
        <Card className="tier-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">EXECUTION RECEIPT</span>
              <h2>Guardian Verdict &amp; Audit Trail Result</h2>
            </div>
            <OutcomeBadge
              outcome={
                lastReceipt.outcome === "approve"
                  ? "approve"
                  : lastReceipt.outcome === "block"
                  ? "block"
                  : "escalate"
              }
            />
          </div>

          <div style={{ padding: "15px" }}>
            <VerdictPanel
              outcome={
                lastReceipt.outcome === "approve"
                  ? "approve"
                  : lastReceipt.outcome === "block"
                  ? "block"
                  : "escalate"
              }
              title={`Guardian Evaluation: ${activeScenario.name}`}
            >
              <ul className="verdict-check-list" style={{ marginTop: "12px" }}>
                {activeScenario.checks.map((chk) => (
                  <li key={chk.rule}>
                    <OutcomeBadge outcome={chk.outcome} />
                    <strong>{chk.rule} · {chk.name}</strong>
                    <span>{chk.detail}</span>
                  </li>
                ))}
              </ul>
            </VerdictPanel>

            <div className="audit-receipt-card">
              <span className="eyebrow">HASH-CHAIN AUDIT EVIDENCE</span>
              <div className="receipt-facts">
                <div>
                  <span>Ledger Sequence</span>
                  <strong>#{lastReceipt.seq}</strong>
                </div>
                <div>
                  <span>Wallet Action</span>
                  <strong>
                    {lastReceipt.outcome === "approve"
                      ? "DISPATCHED (SIMULATED)"
                      : lastReceipt.outcome === "block"
                      ? "STRICTLY BLOCKED"
                      : "ESCALATED TO OWNER"}
                  </strong>
                </div>
                <div>
                  <span>Timestamp</span>
                  <strong>{lastReceipt.timestamp}</strong>
                </div>
              </div>
              <div className="receipt-hash">
                <span>Entry Hash (SHA-256):</span>
                <code>{lastReceipt.hash}</code>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
