# Guardian Rules v1 and Default Mandates (B2)

Owner: Abdullah lane (fiona-fa). Version 1.0.0, effective 14 October 2026 (G1).
Machine-readable: [guardian.yaml](../guardian.yaml), [mandates.yaml](../mandates.yaml), thresholds in [thresholds.yaml](../thresholds.yaml).
Implemented by Daniyal (deterministic checks D5, wallet D6) and Asharib (adversarial review and combiner A6, mandate UI A5).

**Source.** This finalises the twelve draft rules in the Build Blueprint, section "Guardian rules v1". Nothing was silently replaced: every change is listed in "Changes from the draft" with its reason, and three new rules were added: G-13 is final (Tier 1, approved by fiona-b7 on 13 Oct); G-14 and G-15 are *proposed* for Tier 2.

## The four outcomes

| Outcome | Meaning | Who can release it |
| --- | --- | --- |
| `approve` | Every rule passed. The action proceeds as far as the agent's autonomy level allows: executed at *act within mandate*, one-tap owner approval at *prepare*, nothing at *advise*. | — |
| `approve_with_conditions` | Proceeds only if machine-checkable conditions hold at execution (for example "pay on 24 Oct"). The wallet re-checks them and refuses otherwise. A condition never widens a mandate. | The wallet, automatically |
| `escalate` | The Guardian will not clear it alone. The owner, or an authorised user who is not the proposer, approves explicitly (passkey or biometric). | Owner |
| `block` | Must not proceed in this form. No in-app approval releases it; the facts must change (a confirmed bank change, a corrected bill) and the Guardian runs again. | Nobody, by approval |

The blueprint's contract strings are lowercase; "ESCALATE_TO_OWNER" in the finance brief is `escalate`.

**Combining.** Every applicable rule runs on every proposal (so the verdict lists every reason), and the final outcome is the strictest. Three properties are deliberate:

1. **A model cannot override a rule.** The adversarial reviewer (G-12) can only raise the outcome. No agent reasoning, model output or document text can lower an outcome a deterministic rule set.
2. **Fail closed.** A check that cannot run (missing data, timeout, exception) reports `fail` with `CHECK_ERROR: …` and escalates. A payment is never cleared because a check was skipped.
3. **Documents are data.** Text in bills and emails reaches the reviewer only as quoted data; "pay this now" is evidence to examine, never a command.

The Guardian may block but never executes anything, never approves as a user, and never sees the proposing agent's reasoning or prompts.

## Control matrix

| ID | Rule | Check | Outcome when it fires | Threshold (class) | Planted scenario |
| --- | --- | --- | --- | --- | --- |
| G-01 | Payment above the agent's per-payment cap | Policy | Escalate | Mandate cap (owner policy) | S-01 |
| G-02 | Payee not on the allow-list | Policy | Escalate | — | S-02 |
| G-03 | Payee's bank account changed within 7 days, never confirmed out of band, or a bill printing a different account | Policy | **Block** until the owner confirms by phone on the number on file | 7 days (hard; tenant may lengthen, minimum 3) | S-03, DEMO-1 |
| G-04 | Same actor proposes and approves | Policy | **Block** | — | S-04 |
| G-05 | Duplicate bill (same file; same normalised number and amount within 1%; or number similarity ≥ 0.90 and amount within 1%) | Policy | **Block**; escalate for distinct-GRN or different-amount cases | 1%, 0.90, 180 days (hard, provisional) | S-05, S-05b, DEMO-1 |
| G-06 | Three-way match fails (no PO, no GRN, or a line off by more than 2%) | Policy | Escalate | 2% (hard, provisional) | S-06 |
| G-07 | Lines and tax don't add up; journal debits ≠ credits; payment ≠ outstanding balance | Arithmetic | **Block** | 1 minor unit (hard) | S-07 |
| G-08 | Payment creates or deepens a week below the buffer | Policy | Approve with conditions (latest safe date ≤ due date); escalate if none | Buffer (owner policy) | S-08a/b/c |
| G-09 | Required evidence missing, unresolvable or contradicting the payload; unmatched figures in reasoning | Evidence | **Block**; escalate for reasoning mismatches | — | S-09 |
| G-10 | Payments today would exceed the daily cap | Policy | Escalate | Mandate daily cap (owner policy) | S-10 |
| G-11 | Supplier tax ID missing, malformed or different from file | Policy | Escalate | Country pack pattern (unverified) | S-11 |
| G-12 | Adversarial reviewer's concern is high, or the reviewer fails | Adversarial | Escalate | "high" | S-12, DEMO-1 |
| G-13 (final, Tier 1) | Action type outside the mandate or a material decision; category or window outside | Policy | **Block** / escalate | — | S-13 |
| G-14 *(proposed, Tier 2)* | Forecast or balance stale; low-confidence extraction; sources conflict | Evidence | Escalate | 24 h forecast, 48 h balance | — |
| G-15 *(proposed, Tier 2)* | Payee account belongs to an employee, user or related party | Policy | Escalate | — | — |

The S-numbers are defined in [scenarios.yaml](../scenarios.yaml) (B3, authoritative) and used in Daniyal's answer key.

## Three rules worth explaining

**G-05 duplicates without false alarms.** Invoice numbers are normalised in a fixed order: uppercase, strip leading zeros in each digit run, then drop separators. That order matters: it keeps `KAC-2026-0010` and `KAC-2026-0011` apart (similarity 0.889) while `INV 2231` and `INV-2231` become identical. Amount alone never fires the rule, so a monthly rent bill for the same amount passes. Near-identical numbers backed by two distinct goods-received notes escalate instead of blocking, because they may be two genuine deliveries.

**G-08 liquidity, tested incrementally.** The baseline forecast already pays every open bill on its due date. The rule asks whether *this* payment creates or deepens a below-buffer week compared with that plan:

| Case (B3 scenario) | Result |
| --- | --- |
| A routine bill paid on its due date (S-08a) | Pass. If a dip already exists, the detail says it is pre-existing and not caused by this payment. |
| The same bill paid early, landing in the week-7 dip (S-08b) | Approve with conditions: pay on the latest safe date, which is the due date. |
| An unplanned payment that breaches the buffer whatever date it is paid (S-08c) | Escalate to the owner. |

Without the incremental test, the planted week-7 dip would escalate every routine payment. The rule never schedules a payment after its due date, and never delays tax or payroll: those escalate so the owner can arrange funding.

**G-03 bank changes.** The 7-day cooling-off alone would let an unconfirmed change through on day 8, so v1 also blocks any change never confirmed by phone, and any bill that prints an account different from the one on file. The release path is an owner call-back to a number already on file, recorded as an event, followed by a re-run.

## Default mandates

Every agent starts at **advise**. Only the owner moves an agent up or down, each change creates a new mandate version in the audit chain, and **no agent ever gains authority automatically**, however many of its recommendations are accepted. A downgrade is instant, and pending proposals re-run the Guardian against the new mandate.

| Agent | Highest level allowed (ceiling) | Default | May prepare | May execute | Never |
| --- | --- | --- | --- | --- | --- |
| CFO Strategist | Advise | Advise | — (memos only) | — | Payments, entries, contacting lenders or investors |
| Treasurer | Act within mandate (payments) | Advise | Payments | Payments to allow-listed payees within caps, categories and windows, after Guardian clearance | New or changed payees without the owner, payroll, taxes, dividends, loan drawdowns |
| Controller | Prepare | Advise | Bill approvals, journal entries, outgoing documents, reconciliation matches | — | Payments, approving its own drafts, changing bank details |
| Growth Analyst | Prepare (purchase orders) | Advise | Draft purchase orders | — | Payments, launch commitments, supplier contracts |
| Guardian | — | — | — | — | Executing, approving as a user, editing proposals, seeing the maker's reasoning |
| Guide | — | — | — | — | Financial advice, proposals, finance tools, money |

**Material decisions** (borrowing, equity, dividends, capex commitments, product launches, technology contracts, lease signings) are never executable by any agent at any level. Agents advise; the owner decides (G-13).

**Escalation is mandatory** for every Guardian `escalate`, every journal entry, every purchase order and launch memo, every new payee, and every bank-detail change.

### Karachi persona (synthetic demo settings)

| Setting | Value | Why |
| --- | --- | --- |
| Cash buffer (tenant policy) | PKR 2,000,000 | Daniyal's draft, kept. Recheck against one month of committed outflows when generator v1 lands. |
| Treasurer | Act within mandate for payments | Shows the top of the autonomy ladder |
| Per-payment cap | PKR 150,000 | 7.5% of the buffer. The default formula (5%) gives PKR 100,000; 150,000 lets routine supplier bills clear while the blueprint's PKR 184,500 payment escalates to the phone (demo moment 6). |
| Daily cap | PKR 450,000 | 3 × the per-payment cap |
| Categories | Inventory suppliers, utilities, rent, logistics | — |
| Payment window | Mon–Sat, 09:00–17:00 Asia/Karachi, no public holidays | — |
| Controller | Prepare | — |

### Mandate shape (sent to fiona-19 for A2)

`id, tenant_id, agent, version, status, currency, autonomy {action_type → level}, allowed_action_types, per_payment_cap_minor, daily_cap_minor, allowed_categories?, payee_scope?, payment_windows?, effective_from, effective_to?, approved_by, created_at`. The cash buffer is a tenant policy (`tenant.policies.cash_buffer_minor`), not a mandate field.

## Changes from the draft

| Rule | Change | Why |
| --- | --- | --- |
| G-03 | Also blocks unconfirmed changes of any age and a bill printing a different account | Project documentation requires out-of-band confirmation for new accounts |
| G-05 | Exact decision table with normalisation order; escalate for distinct-GRN and different-amount cases | Avoid false blocks on recurring and sequential bills |
| G-07 | Extended to journals and to payment amount against the outstanding balance | Brief's "arithmetic and accounting" control area |
| G-08 | Incremental test against the baseline; never pays after the due date; statutory payments escalate | Approved by fiona-b7, 13 Oct |
| G-09 | Evidence required per proposal type; contradictions block; free-text mismatches escalate | Makes "claim without evidence" testable without a model |
| G-12 | Reviewer errors escalate; deterministic pre-scan for injection and urgency cues | Fail closed; prompt-injection test |
| G-13–G-15 | New; G-13 final, G-14 and G-15 proposed (Tier 2) | Mandate enforcement, stale data and conflicts of interest had no rule |

## Known limits

- The 7-day cooling-off, the 1% and 0.90 duplicate thresholds and the 2% match tolerance are judgement until B3 measures false alarms on the generator's clean bills.
- Pakistan's tax-ID pattern is unverified, which is why G-11 escalates rather than blocks.
- G-12 depends on a model; its errors are contained by fail-closed escalation and by its inability to lower an outcome, not eliminated.
