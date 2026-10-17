import {
  briefingSeedFixture,
  plantedBillProposalFixture,
  plantedBillVerdictFixture,
  treasurerMandateFixture,
} from "@fiona/contracts/fixtures";
import type { BriefingCard, BriefingResponse, Mandate, Proposal, Verdict } from "@fiona/contracts";

export const briefingScenarios = ["default", "planted-bill", "clean", "escalate-over-cap", "degraded", "empty", "error", "replayed"] as const;
export type BriefingScenario = (typeof briefingScenarios)[number];

export interface MockProposalRecord {
  proposal: Proposal;
  verdict: Verdict | null;
}

const clone = <T>(value: T): T => structuredClone(value);

function guardianCard(scenario: "planted-bill" | "escalate-over-cap"): BriefingCard {
  const proposal = clone(plantedBillProposalFixture);
  return {
    id: `card_${scenario}`,
    rank: 1,
    kind: "guardian",
    finding_id: null,
    proposal_id: proposal.id,
    severity: "high",
    needs_owner: true,
    title: scenario === "planted-bill" ? "Guardian blocked a bill to a changed bank account" : "A payment above the mandate needs you",
    detail: scenario === "planted-bill" ? "The synthetic bill duplicates a paid invoice and has a recently changed bank account." : "The synthetic payment exceeds the Treasurer’s per-payment mandate.",
    source_label: "Guardian · planted security scenario",
    money_at_stake: proposal.amount,
    evidence: proposal.evidence,
    actions: [{ label: "Review proposal", route: `/proposals/${proposal.id}`, kind: "primary" }],
  };
}

/** Deterministic local read model. It mirrors the data served by `pnpm mock:api`. */
export function getMockBriefing(scenario: BriefingScenario = "default"): BriefingResponse | null {
  if (scenario === "error") return null;
  const response = clone(briefingSeedFixture);
  if (scenario === "clean" || scenario === "empty") response.cards = [];
  if (scenario === "degraded") response.degraded = [{ source: "inventory", detail: "The labelled inventory fixture is unavailable in this preview." }];
  if (scenario === "replayed") response.meta = { ...response.meta, replayed: true, model: "replay", recorded_at: "2026-10-22T04:00:00Z" };
  if (scenario === "planted-bill" || scenario === "escalate-over-cap") {
    response.cards.unshift(guardianCard(scenario));
    response.cards.forEach((card, index) => { card.rank = index + 1; });
    response.greeting = { text: "Good morning. One proposal needs your review.", needs_owner_count: 1 };
  }
  return response;
}

export function getMockProposals(): MockProposalRecord[] {
  return [{ proposal: clone(plantedBillProposalFixture), verdict: clone(plantedBillVerdictFixture) }];
}

export function getMockProposal(id: string): MockProposalRecord | null {
  return getMockProposals().find((record) => record.proposal.id === id) ?? null;
}

export function getMockMandates(): Mandate[] {
  return [clone(treasurerMandateFixture)];
}

export const screenPreviews = {
  forecast: {
    eyebrow: "13-WEEK VIEW",
    title: "Week 7 falls below the cash buffer",
    detail: "The synthetic forecast reaches PKR 246,119 in its lowest week against a PKR 2,000,000 policy buffer.",
    amountMinor: 175_388_100,
    amountLabel: "Estimated shortfall exposure",
    note: "Forecast output is a fixture-backed demo and does not schedule payments.",
  },
  financing: {
    eyebrow: "OPTION MATCH",
    title: "Supplier credit is the lowest-cost eligible option",
    detail: "The fixture-backed matcher compares cited costs, eligibility and debt-service cover before ranking options.",
    amountMinor: 200_000_000,
    amountLabel: "Illustrative financing request",
    note: "Prices and product availability remain illustrative until terms are verified.",
  },
  inventory: {
    eyebrow: "INVENTORY ANALYSIS",
    title: "Slow stock is tying up working capital",
    detail: "The demo highlights summer lawn suits with more than a year of cover and a separate reorder suggestion for wool shawls.",
    amountMinor: 53_300_000,
    amountLabel: "Illustrative stock at risk",
    note: "This synthetic preview's draft reorder suggestions do not create a purchase order.",
  },
  audit: {
    eyebrow: "SIMULATED AUDIT TRAIL",
    title: "Every proposal and payment attempt has a trace",
    detail: "The demo audit chain records a proposal, Guardian outcome and simulated wallet result in order.",
    amountMinor: 18_450_000,
    amountLabel: "Blocked demo payment",
    note: "This synthetic preview cannot make a real payment.",
  },
  import: {
    eyebrow: "LEDGER INTAKE",
    title: "Source files are checked before they affect the ledger",
    detail: "The importer validates bank, POS and bill records and reports row-level errors without changing the synthetic source files.",
    amountMinor: 0,
    amountLabel: "Ready for a mock file",
    note: "This synthetic preview keeps file upload disabled.",
  },
  "launch-lab": {
    eyebrow: "LAUNCH LAB",
    title: "Winter shawl scenario is ready to explore",
    detail: "The synthetic launch simulation combines unit economics, demand variation and cash timing into an illustrative result.",
    amountMinor: 50_119_900,
    amountLabel: "Illustrative peak cash need",
    note: "This illustrative preview does not submit a launch decision.",
  },
  council: {
    eyebrow: "DECISION COUNCIL",
    title: "Financing viewpoints are kept visible",
    detail: "The demo preserves the recommendation and dissent trail for a financing decision before the owner chooses an action.",
    amountMinor: 200_000_000,
    amountLabel: "Decision under review",
    note: "Council deliberation is replay-only in this preview.",
  },
} as const;
