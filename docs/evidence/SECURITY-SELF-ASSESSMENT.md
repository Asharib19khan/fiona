# Security self-assessment

Fiona is a governed AI finance prototype that demonstrates ledger-backed analysis and simulated
financial actions over synthetic SME data. This page states what the controls are, where each is
tested, and what is **not** covered. Last checked: 19 Oct 2026.

## Controls and where they are proven

| Control | How it works | Proven by |
|---|---|---|
| Money moves only through the wallet | Agents have no tool that pays, posts journals or approves. The wallet is the only code that writes a payment event. | `services/agents` toolboxes; `engine/wallet/tests/test_wallet.py` |
| No payment without a cleared, complete, current verdict | The wallet reloads the proposal, verdict and decisions from the database and refuses unless the verdict is the latest, unmodified (hash recomputed), at most 7 days old, carries every Tier-1 rule **and** the G-12 model review, is no softer than its own checks, and (below `act_within_mandate`) has an owner approval by someone other than the proposer. 22 refusal cases. | `engine/wallet/tests/test_wallet.py::test_wallet_refuses` |
| A block is final | No owner decision can release a `block`; the wallet refuses it independently. | `tests/test_acceptance.py` (scenario 2), `ledger/tests/test_flow.py` |
| Fail closed when the Guardian is down | Without the G-12 review the wallet refuses (`REVIEW_MISSING`), even after an owner approval. A reviewer error, timeout or malformed answer becomes `escalate`, never `approve`. The model can only raise an outcome. | `tests/test_acceptance.py` (scenario 5), `ledger/tests/test_review.py` |
| Pay once | The payment event's source key is the proposal ID (unique per tenant), so a retry or a race returns `already_executed`. | `test_cleared_payment_executes_once_and_is_audited`, acceptance scenario 1 |
| Documents are data | Bill text is never placed in an agent's instructions. A deterministic pre-scan flags text addressed to an AI, urgency, secrecy and bank changes; the Opus reviewer gets the flags as data. The extractor lists embedded instructions; the Treasurer refuses flagged bills. | `tests/test_acceptance.py` (scenario 3 + phrasing cases), [`runs/prop_01M5HDDCM0DBBKVDFGWXT4K1D9.json`](runs/prop_01M5HDDCM0DBBKVDFGWXT4K1D9.json) (real Opus run) |
| Tenant isolation | Every table has forced row-level security keyed on `app.tenant_id`; the engine runs tenant work as a role without `BYPASSRLS`. In live mode the tenant comes only from a signed 60-second token; a tenant header or query parameter is ignored. | `tests/test_acceptance.py` (scenario 4), `ledger/tests/test_schema_rls.py`, `tests/test_tenancy.py` |
| Only people decide | Decisions need a person token (owner or finance); agents and the Guardian get 403. Maker-checker: the proposer cannot approve (G-04). | `ledger/tests/test_review.py`, `ledger/tests/test_proposals.py` |
| Tamper evidence | The audit log is append-only (database triggers) and hash-chained per tenant; the chain is verified on every trail view and export. | `engine/wallet/tests/test_audit.py`, `scripts/verify_audit_chain.py` |
| Hosted database | 17 tables, RLS forced on all, no grants to Supabase `anon`/`authenticated` (checked after migration on 19 Oct). | Migration `20261013120200_ledger_security.sql` |
| Sign-in | Supabase Auth; workspace and role read from `app_metadata` (not user-editable). One super admin, fixed server-side, creates accounts. | `apps/web/test/admin.test.ts`, `apps/web/test/live-bff-auth.test.ts` |
| Secrets | No secret in the repo, prompts or `NEXT_PUBLIC_*`. A gitleaks hook runs on every commit. | Full-history scan below |

## Guardian rules

| Rule | Kind | Checks | Tests |
|---|---|---|---|
| G-01 | deterministic | Per-payment cap | `guardian_checks/tests/test_properties.py`, `ledger/tests/test_proposals.py` |
| G-02 | deterministic | Payee on the allow-list | `test_properties.py` |
| G-03 | deterministic | Bank change without call-back confirmation | `test_properties.py`, `test_review_fixes.py`, acceptance scenario 2 |
| G-04 | deterministic | Maker-checker | `test_properties.py`, `ledger/tests/test_proposals.py` |
| G-05 | deterministic | Duplicate bill | `test_properties.py`, `ledger/tests/test_bill_checks.py` |
| G-06 | deterministic | Three-way match | `test_properties.py` |
| G-07 | deterministic | Arithmetic and journal balance | `test_properties.py` |
| G-08 | deterministic | Cash buffer (live forecast) | `test_properties.py`, `test_review_fixes.py` |
| G-09 | deterministic | Evidence exists for every figure | `test_properties.py` |
| G-10 | deterministic | Daily cap | `test_properties.py` |
| G-11 | deterministic | Supplier tax ID | `test_properties.py` |
| G-12 | **model** (Claude Opus) | Injection, pressure, mismatches | `ledger/tests/test_review.py`, `services/guardian/tests/test_review.py`, acceptance scenario 3 |
| G-13 | deterministic | Action within the agent's mandate | `test_properties.py` |
| G-14 | deterministic, **off** | Stale inputs (proposed, Tier 2) | `guardian_checks/tests/test_g14_g15.py` |
| G-15 | deterministic, **off** | Insider payee (proposed, Tier 2) | `test_g14_g15.py` |

Every rule that cannot run reports `fail` with `CHECK_ERROR:` and contributes `escalate`. The 21
planted scenarios in `rulebook/scenarios.yaml` are checked against their expected outcomes in
`guardian_checks/tests/test_scenarios.py`.

## Secrets scan

`gitleaks git --redact .` (gitleaks 8.30.1), 19 Oct 2026: **120 commits scanned, ~331 MB, no leaks
found.** The same tool runs as a pre-commit hook.

## Known limitations

- **Prototype, synthetic data.** One invented Karachi apparel business (seed 42). No real bank,
  tax authority or accounting system is connected. Payments are simulated.
- **The model-only scenario is not in the deterministic suite.** S-12 (prompt injection, G-12) is
  skipped in `test_scenarios.py` because only a model can judge it. It is covered by the Guardian
  service tests, by the acceptance test (with a supplied reviewer answer), and by the recorded real
  Opus run in `runs/`. Model output varies between runs.
- **G-14 and G-15 are off.** Written and tested, not enabled in verdicts.
- **Hosted agents need an Anthropic API key and spend money.** Each run is capped by
  `LLM_RUN_BUDGET_USD`; there is no daily cap in code yet. No replay recordings exist yet, so if the
  model is unavailable the hosted demo cannot propose or review (it fails closed, but it stops).
- **Verdict age is fixed at 7 days** in the wallet, not set per business in the rulebook.
- **Decisions can come from the owner or the finance role.** There is no per-amount approver limit.
- **Accounting simplifications.** EBITDA on the financing screen is a proxy from operating cash flow
  (disclosed on screen); inventory reads generator files rather than the database.
- **Scanned images are not read.** Bill upload takes PDF text and plain text.
- **The Supabase database password and secret key appeared in a local session log** on 19 Oct.
  They were never committed; they are to be rotated after deployment.
