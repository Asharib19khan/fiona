# Prompt 2 for Antigravity: build the Guardian checks, wallet and audit log (D5 and D6)

Paste everything below the line into Antigravity, in a new conversation.

---

You are the BUILD-AG lane for Fiona, an AI finance copilot for small businesses (FinTechathon 2026, deadline Tue 20 Oct). The repository is `Y:\Fiona`. Four Claude Code sessions own the other parts of the code. They are paused to save tokens, and a Claude reviewer will check your work afterwards. Your job is heavy, well-specified engineering: the **deterministic Guardian checks (D5)** and the **sandbox agent wallet with its hash-chained audit log (D6)**. They are the security core, worth 30% of the score, so correctness matters more than speed.

## Rule zero: do not invent anything
- Every rule ID, threshold, field name, table, column, enum value, file path and function you use must already exist in the files named below. Open the file and check before you use a name.
- If something you need is missing or ambiguous, **do not guess.** Write it under "Questions" in `docs/status/antigravity-build.md`, choose the most conservative behaviour (fail closed: escalate or refuse), mark it in the code with `# QUESTION(AG): <text>`, and carry on.
- Never claim a test passes unless you ran it and saw it pass. Paste the real pytest summary line into the status file.
- Never hardcode a threshold that exists in `rulebook/`. Load it.

## Read these first, in this order
1. `CLAUDE.md` and `AGENTS.md`: the repository rules. Obey them.
2. `docs/orchestrator/PLAN.md` §5 (engineering rules) and §6 (git).
3. `rulebook/guardian.yaml`, in full: the verdict semantics, combiner, fail-closed rule, and every rule G-01 to G-15 with its family, inputs, threshold IDs, outcome, condition and audit_fields. **G-13 is final. G-14 and G-15 are "proposed": implement them behind a flag that defaults to off.** G-12 is the model reviewer and is NOT yours.
4. `rulebook/thresholds.yaml` and `rulebook/mandates.yaml`: the threshold values by ID, and the mandate shape.
5. `rulebook/scenarios.yaml`, in full: `common` (the buffer, the Treasurer mandate, the 13-week `forecast_fixture`), then every scenario's `given`, `expected_checks` and `expected_outcome`. The scenarios DEMO-1, S-01 to S-13 (with S-05b and S-08a/b/c) and the controls C-01 to C-04 are **your acceptance tests.**
6. `packages/contracts/python/fiona_contracts/models.py`: the classes `Check`, `Verdict`, `Proposal`, `ProposalDraft`, `ProposalType`, `Mandate`, `PayOnCondition`, `MaxAmountCondition`, `BeforeTimeCondition`, and the ledger event models. Plus `fiona_contracts/hashing.py` (`canonical_json`, `verdict_hash`). Import these. **Never redefine them.**
7. `data/fixtures/FORMATS.md`: the money, ID and date conventions, the `bank_detail_change` event, and the bills, parties, purchase-order and goods-received shapes.
8. `supabase/migrations/20261013120100_ledger_tables.sql` and `..._ledger_security.sql`: the tables `proposals`, `verdicts`, `audit_log`, `events`, `mandates` and `parties`, plus row-level security and the append-only triggers.
9. `services/engine/ledger/db.py` (`connect`, `tenant_session`, `create_database`, `apply_migrations`) and `services/engine/ledger/tests/conftest.py`: how tests get a throwaway database. Copy that pattern.
10. An existing engine module that serves an API, as an example of the layout: `services/engine/forecast/api.py` and its tests.

## What you own (only write here)
- `services/engine/guardian_checks/` (new module: `__init__.py`, code, `tests/`)
- `services/engine/wallet/` (new module: `__init__.py`, code, `tests/`)
- **One** new additive migration file: `supabase/migrations/20261014120000_verdict_ids_and_wallet.sql` (see Task 2)
- `docs/status/antigravity-build.md` (your status file)

Do not touch anything else: not other modules, `app/`, `pyproject.toml`, `packages/contracts`, the rulebook, the web app, or docs. If you need a dependency, list it under "Questions" rather than adding it. (These are already available: pydantic, psycopg, pyyaml, rapidfuzz, pytest, hypothesis.)

## Task 1 (D5): deterministic Guardian checks, as a pure library with no database
Build `engine.guardian_checks`:
- `rules.py` loads `rulebook/guardian.yaml` and `thresholds.yaml` once, resolves each threshold by ID, and exposes the `policy_version`.
- `context.py` defines one typed input, `CheckContext` (Pydantic), that holds everything the rules need:
  - the proposal (contract `Proposal`/`ProposalDraft`)
  - the agent's mandate (contract `Mandate`)
  - tenant policies (the buffer)
  - the payee party (`on_allow_list`, `bank_account_changed_at`, the last `bank_detail_change` with `confirmed_via`, the tax ID with its country pattern)
  - the bill under review, and the supplier's earlier bills (number, amount, document_sha256, status, paid)
  - the matching PO and goods-received notes
  - the 13-week baseline forecast (week starts and closing balances in minor units)
  - payments already made today by this agent
  - the actor IDs (proposer, approver)
  - `now` (injected; never call the clock inside a rule)

  Build it from exactly the fields that `guardian.yaml` says each rule reads. Nothing extra.
- `checks.py` holds one function per rule (`g01_per_payment_cap`, and so on), each `(ctx) -> Check | None`. It returns `None` only when guardian.yaml says the rule does not apply to that action type. **Every applicable rule runs, even after another fails.** If a rule raises an exception or its input is missing, it returns `result="fail"`, `outcome="escalate"` and `detail="CHECK_ERROR: <reason>"` (fail closed). Each `Check` carries `name` (its family), `rule`, `result`, `outcome`, a plain-English `detail` containing the actual numbers, an optional machine-checkable `condition`, and `audit` filled with that rule's `audit_fields`.
- Specifics to get right, all taken from guardian.yaml and scenarios.yaml:
  - G-05 duplicate detection uses invoice-number normalisation (`INV-2231`, `INV 2231` and `INV2231` are equal) with RapidFuzz similarity in basis points, amount tolerance in basis points, and same-file SHA-256.
  - G-07 checks that the lines add up, the subtotal plus tax equals the total, and the tax rounds half-up per the country pack, all in integer minor units.
  - G-08 tests the payment's **incremental effect against the baseline forecast**. It yields approve, approve_with_conditions with `pay_on` set to the latest safe date, or escalate, as S-08a, S-08b and S-08c define.
  - G-10 is the daily cap. G-13 checks the action type against the mandate's `allowed_action_types`, and is a block.
- `combine.py` provides `combine(checks) -> (outcome, conditions)`: the strictest outcome wins, using guardian.yaml's `strictness_order`. Conditions are merged; conflicting `pay_on` dates become escalate. **No input can lower an outcome.** Also `build_verdict(proposal_id, checks, now, policy_version) -> Verdict`, which fills `verdict_hash` with `fiona_contracts.verdict_hash` and an `id` of the form `vrd_<ulid>`.
- `run.py` provides `run_deterministic_checks(ctx) -> list[Check]`, which runs every rule G-01 to G-11 and G-13, plus G-14 and G-15 only if enabled.
- Tests (`tests/test_scenarios.py`): load `rulebook/scenarios.yaml`, build a `CheckContext` from each scenario's `given` (plus `common`), and assert every row of its `expected_checks` (rule, result, outcome). Assert `expected_outcome` from `combine`, ignoring G-12, which belongs to the model. For DEMO-1, the combined deterministic outcome must still be **block**. The controls C-01 to C-04 must not come out as block or escalate.
- Add Hypothesis property tests:
  - `combine` never returns an outcome less strict than any input.
  - Adding a passing check never changes the outcome.
  - An exception in any rule yields escalate or stricter, never approve.
- If a scenario's `given` lacks a field a rule needs, add the minimum fixture *inside your test file*, with a comment naming the scenario. Never edit `scenarios.yaml`.

## Task 2 (D6): sandbox wallet and hash-chained audit log
Build `engine.wallet`:
- `audit.py`:
  - `append(conn, tenant_id, record: dict, proposal_id | None) -> AuditEntry`. The hash is `sha256(prev_hash + canonical_json(record))`, written as `sha256:<hex>`. The first entry for a tenant uses `prev_hash = "sha256:" + "0"*64`. `seq` increments per tenant inside one transaction, with `select ... for update` or an advisory lock so concurrent appends can't fork the chain.
  - `verify(conn, tenant_id) -> VerifyResult` (ok, length, first_bad_seq).
  - Use plain SHA-256 (it is NOT an HMAC; don't call it one).
- `wallet.py`, a simulated account (never a real bank). `execute_payment(conn, proposal, verdict, approvals, now) -> PaymentResult` **refuses** (returns `refused` with a reason, and writes an audit record of the refusal) unless every one of these holds:
  - The verdict exists for this proposal, and its hash recomputes correctly.
  - The outcome is approve; or approve_with_conditions with every condition true at `now`; or escalate with an owner approval from a user who is **not** the proposer (segregation of duties).
  - The outcome is never block.
  - Defence in depth: the wallet itself re-checks the per-payment cap, the daily cap, the allow-list and the bank-change cooling-off, using the same loaded rulebook values. A wallet must not trust a single upstream check.

  On success it writes, in one transaction:
  - a `supplier_payment` event in the exact FORMATS.md §3.13 shape, with `wallet_ref` `wal_<ulid>`
  - the proposal status change, if the table supports it
  - audit records for the payment

  Simulated balance: the opening balance comes from the tenant's bank account in the seeded data. Never let the balance go negative.
- `oplog.py`: `export_operation_log(conn, tenant_id, out_dir)` writes JSONL operation logs (proposals, verdicts, approvals, payments, refusals, and the audit chain with a verify result). This is submission deliverable 06, so make each line self-explanatory and add a README header file.
- The migration file `20261014120000_verdict_ids_and_wallet.sql` is **additive only**. The `verdicts` table lacks `id`, `policy_version` and `previous_verdict_id`, which the contract `Verdict` has, and its primary key `(tenant_id, proposal_id)` blocks re-runs. Add those columns, keep the existing rows valid, and change the key to `(tenant_id, id)` with an index on `proposal_id`. Add any wallet table you need (for example `wallet_accounts`, `approvals`) with `tenant_id`, forced row-level security and a tenant_isolation policy **in exactly the style of the existing security migration**, and append-only triggers where the history must not change. Write nothing that drops data.
- Tests use the throwaway-database pattern from `ledger/tests/conftest.py`, and every write goes through `tenant_session` (RLS on). They must prove:
  - Payment with no verdict, a block verdict, a tampered verdict hash, an escalation approved by the proposer, an expired condition, or over cap: each one is **refused**, with an audit record.
  - The S-01 flow: escalate, then owner approval, then exactly one `supplier_payment`, then the audit chain verifies.
  - DEMO-1 never pays.
  - Editing any audit row (as superuser, in the test) makes `verify` report that row's seq.
  - Tenant A cannot read or write tenant B's wallet or audit rows.

  Add a Hypothesis test that random sequences of appends always verify.

## How to run things (Windows, from `Y:\Fiona\services\engine`)
- Tests: `uv run pytest guardian_checks wallet -q`. The full suite (`uv run pytest -q`) must stay green as well.
- Lint and format: `uv run ruff check guardian_checks wallet` and `uv run ruff format guardian_checks wallet`. The pre-commit hook rejects unformatted files.
- The local Postgres is portable PG17, managed by `engine.ledger.db`. If the server isn't running, start it once in its own terminal: from `Y:\Fiona\services`, run `uv run --project engine python -m engine.ledger.db start`. Never start or kill it from inside a test run.

## Git (one working tree shared with other agents)
- Never run checkout, switch, stash, reset, clean, rebase, `git add -A`, `git add .` or `commit -a`, and never push.
- Commit only your paths, after your tests pass: `git add services/engine/guardian_checks docs/status/antigravity-build.md`, then `git commit -m "AG-D5: <what>" -- services/engine/guardian_checks docs/status/antigravity-build.md`. Use the prefix `AG-D6:` for wallet commits, which also include `services/engine/wallet` and the migration file. If you hit `index.lock`, wait and retry.
- Commit in small steps (rules and context; the checks; the combiner; scenario tests green; audit; wallet; oplog; migration and RLS tests).

## Status file: `docs/status/antigravity-build.md`
Keep a table with the columns Step, Status, Commit, and the real pytest summary line. Under it, add a **Questions** list (everything you were unsure about) and a **Deviations** list (anything that differs from guardian.yaml or scenarios.yaml, and why). When both tasks are done and green, write `D5+D6 DONE: <pytest summary line>` at the top and stop.

## Definition of done
- Every scenario's `expected_checks` passes.
- Controls are not blocked.
- The property tests pass.
- The wallet refuses in every unsafe case.
- The audit chain detects edits.
- RLS isolation is proven.
- The full engine suite and ruff are green.
- Nothing outside your paths was changed.
