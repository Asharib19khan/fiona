import briefingSeed42 from "../examples/Briefing.seed-42.json" with { type: "json" };
import treasurerMandate from "../examples/Mandate.treasurer.json" with { type: "json" };
import plantedBill from "../examples/scenarios/planted-bill-block.json" with { type: "json" };
import type { BriefingResponse, Mandate, Proposal, Verdict } from "../generated/ts/types";

/**
 * Labelled synthetic fixtures shared by the mock server and Window. They never describe a
 * live tenant and are deliberately exported separately from the contract validation API.
 */
export const briefingSeedFixture = briefingSeed42 as unknown as BriefingResponse;
export const treasurerMandateFixture = treasurerMandate as unknown as Mandate;
export const plantedBillProposalFixture = plantedBill.proposal as unknown as Proposal;
export const plantedBillVerdictFixture = plantedBill.verdict as unknown as Verdict;
