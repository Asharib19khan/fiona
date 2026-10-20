import type { Metadata } from "next";
import Link from "next/link";
import { LegalDoc, type LegalSection } from "../legal-doc";

export const metadata: Metadata = { title: "AI & Financial Notice · Fiona" };

const sections: LegalSection[] = [
  {
    id: "you-are-talking-to-ai",
    heading: "You are working with AI",
    body: <p>The Treasurer, Controller, CFO Strategist, Growth Analyst and the Guardian&rsquo;s reviewer are AI agents built on Anthropic&rsquo;s Claude models. They are not people. Their names describe their job in Fiona, not a qualification.</p>,
  },
  {
    id: "how-it-works",
    heading: "How decisions are split",
    body: (
      <ul>
        <li><strong>The agents propose.</strong> They read documents, choose what to suggest and explain why.</li>
        <li><strong>The engine computes.</strong> Amounts, balances, forecasts and ratios come from Fiona&rsquo;s ledger engine in code, not from the AI. Money is held as whole minor units, never estimated.</li>
        <li><strong>The Guardian checks.</strong> Every payment proposal passes deterministic rule checks and an independent AI review. A block cannot be overridden.</li>
        <li><strong>You decide.</strong> Nothing is paid without a person&rsquo;s approval on the latest Guardian verdict.</li>
      </ul>
    ),
  },
  {
    id: "limits",
    heading: "Limits you should know",
    body: (
      <ul>
        <li>AI can be wrong, incomplete or overconfident, and can misread documents. Check important figures against the source, which Fiona links for each extracted field.</li>
        <li>Forecasts are projections from past records and stated assumptions. They are not promises about the future.</li>
        <li>Agents may disagree. Dissent is shown on purpose; it is not an error.</li>
        <li>Fiona&rsquo;s demonstration business is synthetic. Its results say nothing about any real business.</li>
      </ul>
    ),
  },
  {
    id: "not-advice",
    heading: "Not financial, tax or legal advice",
    body: <p>Fiona is decision support. It is not investment, financing, accounting, tax or legal advice, and we are not licensed to give such advice. Financing comparisons are illustrations, not offers from any lender. Before acting on anything material, consult a qualified professional. You are responsible for your decisions and approvals. See the <Link href="/legal/terms">Terms of Service</Link>.</p>,
  },
  {
    id: "sandbox",
    heading: "The sandbox wallet",
    body: <p>The wallet in this prototype is a sandbox. It is not connected to any bank, card network or payment system, and approving a payment moves no real money.</p>,
  },
  {
    id: "safety",
    heading: "Safety measures",
    body: (
      <ul>
        <li>Documents are treated as data, never instructions. Text that tries to instruct the AI is reported and ignored.</li>
        <li>Each agent works within mandates the owner can tighten, with a spending cap on every AI run.</li>
        <li>Every step is recorded in a tamper-evident audit trail you can inspect.</li>
      </ul>
    ),
  },
  {
    id: "report",
    heading: "Report a problem",
    body: <p>If an agent produces something harmful, misleading or plainly wrong, tell us using the contact below. Reports help us improve the checks.</p>,
  },
];

export default function AiNoticePage() {
  return (
    <LegalDoc
      title="AI & Financial Notice"
      summary={
        <ul>
          <li>The agents are AI, not people, and they can make mistakes.</li>
          <li>The engine does the maths; the Guardian checks; you approve every payment.</li>
          <li>Nothing here is financial, tax or legal advice, and the wallet moves no real money.</li>
        </ul>
      }
      sections={sections}
    />
  );
}
