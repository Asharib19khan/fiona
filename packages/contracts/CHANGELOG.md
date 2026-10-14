# Contracts changelog

Additive changes only after the G1 freeze (Wed 14 Oct 2026). Breaking changes need Asharib and Daniyal, an entry in `docs/decision-log.md`, and the orchestrator's approval.

## 1.0.0-rc.1 (2026-10-14): A2 core, proposed for the G1 freeze
- Common: `Money`, `Timestamp`, `Date`, prefixed IDs, `RuleId` (G-01…G-15), `AgentName`, `Actor`, `Evidence`, `Action`, `Period`, `Meta`, `ErrorEnvelope`.
- `Figure`, `FigureInput`, `Threshold` (Yahya's field list; every dimensionless number in basis points).
- `Finding` (Blueprint shape plus `type`, `detail`, `period`, `created_at`, `dedupe_key`, `figures`); `money_at_stake` is nullable.
- `ProposalDraft` / `Proposal`: six types (payment with `channel` wallet|bank_file, bill_approval, journal_adjustment, send_document, purchase_order, reconciliation_match), `status`, `created_by` (G-04), `verdict_id`, `supersedes`; `DecisionRequest`, `Decision` (`decided_by`, G-04).
- `Verdict` with `id` (CG-1), per-check `outcome` (fiona-b7 ruling), machine-checkable `Condition`s, `policy_version`, `previous_verdict_id`, and `verdict_hash` as defined (CG-16).
- `Mandate` (Abdullah's `mandate_shape`) and `TenantPolicies.cash_buffer_minor` (cash buffer ruling).
- `LedgerEvent` union of the nine event types, matching `data/fixtures/FORMATS.md` §3.13.
- Generated: TypeScript types, Pydantic v2 package `fiona_contracts`, and a typed engine client from the engine's OpenAPI.

## 1.0.0-rc.2 (2026-10-14): Daniyal's G1 sign-off condition
- `ProposalDraft.agent` / `Proposal.agent` use the full `AgentName` enum (was treasurer | controller | growth_analyst), so an out-of-mandate attempt (S-13: the CFO Strategist submits a payment) reaches the Guardian and is **blocked by G-13 with a verdict and an audit record**, instead of a 422 at intake that leaves no trace. Fail-closed is unchanged: G-13 blocks any action type missing from the agent's mandate.
