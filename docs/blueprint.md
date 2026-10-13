# Fiona: Build Blueprint

Oct 12, 2026 · @Ye

This is the one technical plan all four of us build from: a thin slice that runs end to end, split into boxes with one owner each and a written contract between every pair of boxes.

## The slice we build

We build the five-minute demo and nothing else: seven moments, four of which are Must and three Should. The demo is the specification, so any feature that no moment needs waits until after the competition.

| # | Demo moment | What has to work underneath | Tasks | Tier |
| --- | --- | --- | --- | --- |
| 1 | Onboarding and Stage Detector | Importers load bank, POS and bill files; the Stage Detector reads the cash flows against the rulebook and shows its working | D3, Y2, B1 | Must |
| 2 | Morning briefing | Cash forecast, inventory and reconciliation findings are ranked by money at stake and shown as cards | Y1, Y3, Y6, D4, A5 | Must |
| 3 | The Guardian blocks a bill | A bill is extracted, checked for duplicates, three-way match, tax and bank-detail changes, and reviewed adversarially | A4, D4, D5, A6, B2, B3 | Must |
| 4 | Council mode: loan or investor | Debt-versus-equity numbers feed a debate between agents that ends in a memo with the dissent on record | Y4, A7, B4 | Should |
| 5 | Launch Lab | Demand proxies, a forecast with a range, break-even and payback, then a cash check | Y5, Y3, Y1 | Should |
| 6 | Approval by phone | A payment above the mandate reaches the phone; approval releases the wallet payment, the ledger and the audit log | A5, D6 | Must |
| 7 | Persona switch | A second tenant in another country and currency, with a framework lens | D7, D8 | Should |

Moment 4 is Should only as a council debate: its numbers (task Y4) are Must, because the decision engine is the core of the CFO Strategist. Moment 6 keeps its phone approval as the preferred path, with approval in a desktop browser as the fallback.

Task IDs refer to the *Fiona: Team Roadmap and Task Plan*. The vision, the features and the reasons behind them are in *Fiona: Project Documentation*; this blueprint only says how the slice is built.

## Architecture

&#91;embedded content: build architecture · 9 boxes, 1 contracts band\]

The web app and the agents never reach the engines except through the contracts band. That is what lets four people work in parallel: as long as a box keeps its contract, its inside can change freely.

**Rules for the boxes**

- Agents propose; only the wallet in Daniyal's ledger services can move money, and only with a cleared verdict ID.
- The Guardian service shares no code and no prompts with the agents it checks.
- The rulebook is data, not code: Yahya's and Daniyal's engines load it, so Abdullah can change a threshold without touching Python.
- Every box ships a mock by 14 October that returns fixture data in the contract's shape.

## Repository layout

One monorepo, one folder per box, one owner per folder. The rule for crossing folders: import only from `packages/contracts`, never from another box's internals.

```text
fiona/
  apps/
    web/                 Next.js 16 app and installable phone app      (Asharib)
  packages/
    contracts/           schemas, generated TypeScript client           (Asharib + Daniyal)
    ui/                  shared components and design tokens            (Asharib)
  services/
    engine/              FastAPI app that mounts the modules below
      ledger/            importers, reconciliation, wallet, audit       (Daniyal)
      guardian_checks/   policy, evidence, arithmetic rules             (Daniyal)
      forecast/          stage, ratios, cash, inventory, Launch Lab     (Yahya)
      decisions/         debt versus equity, dividend, NPV, IRR         (Yahya)
    agents/              Claude runtime, prompts, tool bridge           (Asharib)
    guardian/            adversarial review and verdict combiner        (Asharib)
  rulebook/              YAML rules, mandates, scenarios, rulepacks     (Abdullah)
  data/
    generator/           synthetic businesses and answer key            (Daniyal)
    fixtures/            generated sample files used by every mock      (Daniyal)
  docs/                  this blueprint, the roadmap, decision log
```

`services/guardian` imports `engine.guardian_checks` as a library but has its own deployment, its own model key and no access to the agents' prompts.

## Contracts

These are the agreements between boxes. They are frozen at G1 on 14 October; after that, only additive changes, and any breaking change needs Asharib's and Daniyal's sign-off and an entry in the decision log below.

**Conventions.** Identifiers are prefixed (`prop_`, `bill_`, `sup_`). Money is an integer in minor units plus a currency code, never a float. Timestamps are ISO 8601 in UTC; the interface converts them for display. Every response carries `api_version: "v1"`.

### Engine API

| Endpoint | Purpose | Built by | Called by |
| --- | --- | --- | --- |
| `POST /v1/import/bank`, `/pos`, `/bills` | Load bank lines, POS sales and extracted bills as ledger events | Daniyal | Import page, agents |
| `GET /v1/ledger/events` | Canonical events, filterable by date and type | Daniyal | Everyone |
| `POST /v1/reconcile/run`, `GET /v1/reconcile/matches` | Run the matching passes; read matches and leftovers | Daniyal | Controller |
| `POST /v1/bills/check` | Duplicate, three-way match, tax and bank-detail checks on one bill | Daniyal | Controller |
| `GET /v1/reconcile/findings` | Reconciliation findings as Finding objects | Daniyal | Briefing |
| `GET /v1/stage` | Life-cycle stage with its working | Yahya | CFO Strategist, briefing |
| `GET /v1/forecast/cash?weeks=13` | Weekly cash forecast and the first week below the buffer | Yahya | Treasurer |
| `GET /v1/forecast/findings` | Forecast and inventory findings as Finding objects | Yahya | Briefing |
| `GET /v1/inventory/analysis` | ABC–XYZ classes, reorder points, dead stock | Yahya | Growth Analyst |
| `POST /v1/decisions/debt-equity`, `/dividend` | Decision calculators with inputs and thresholds returned | Yahya | CFO Strategist, council |
| `POST /v1/launch-lab/simulate` | Product launch simulation: cases, break-even, payback | Yahya | Growth Analyst |
| `POST /v1/proposals` | An agent submits a Proposal; the Guardian runs; a Verdict returns | Daniyal (store), Asharib (combiner) | Agents |
| `GET /v1/proposals/{id}` | The proposal with its verdict | Daniyal | Web app |
| `POST /v1/proposals/{id}/decision` | The owner approves or rejects | Daniyal | Web app |
| `POST /v1/wallet/pay` | Executes a payment, only with a cleared verdict ID | Daniyal | Proposals service |
| `GET /v1/audit?proposal_id=` | The hash-chained record and whether it verifies | Daniyal | Web app |
| `GET /v1/briefing` | Composes all findings into ranked cards | Asharib | Web app |

### The Proposal object

Every agent action that touches money, a document going out or the ledger is a Proposal.

```json
{
  "id": "prop_01JC8Q2R7X",
  "tenant_id": "ten_karachi_apparel",
  "agent": "treasurer",
  "type": "payment",
  "created_at": "2026-10-22T09:15:00Z",
  "summary": "Pay supplier bill INV-2231 on 23 October",
  "amount": { "minor": 18450000, "currency": "PKR" },
  "payload": { "payee_id": "sup_017", "bill_id": "bill_2231", "pay_on": "2026-10-23" },
  "evidence": [
    { "kind": "ledger_row", "ref": "bill_2231" },
    { "kind": "document", "ref": "doc_88" }
  ],
  "reasoning": "Due on 24 October; cash stays above the buffer in every forecast week.",
  "mandate_ref": "mnd_treasurer_v1"
}
```

### The Verdict object

The Guardian returns exactly this, and the wallet refuses any payment without a verdict whose outcome is `approve` or a satisfied `approve_with_conditions`.

```json
{
  "proposal_id": "prop_01JC8Q2R7X",
  "outcome": "block",
  "checks": [
    { "name": "policy", "result": "fail", "rule": "G-03", "detail": "Supplier bank account changed 2 days ago" },
    { "name": "evidence", "result": "pass", "rule": "G-09", "detail": "Every claim cites a row or a file" },
    { "name": "arithmetic", "result": "pass", "rule": "G-07", "detail": "Lines and tax add up" },
    { "name": "adversarial", "result": "fail", "rule": "G-12", "detail": "Request presses for urgent payment to a new account" }
  ],
  "conditions": [],
  "decided_at": "2026-10-22T09:15:04Z",
  "verdict_hash": "sha256:9f2c41"
}
```

Outcomes are `approve`, `approve_with_conditions`, `escalate` and `block`. The combiner takes the strictest outcome across all checks.

### The Finding object

The briefing is built from findings that modules publish.

```json
{
  "id": "fnd_01JC8R4K2M",
  "source": "forecast",
  "severity": "high",
  "title": "Cash dips below your buffer in week 7",
  "money_at_stake": { "minor": 42000000, "currency": "PKR" },
  "evidence": [{ "kind": "forecast_run", "ref": "fc_0042" }],
  "actions": [{ "label": "Open forecast", "route": "/forecast" }]
}
```

### Ledger event types

| Event | Meaning | Key fields |
| --- | --- | --- |
| `sale` | A POS or invoiced sale | Lines (item, quantity, price, cost), payment method, cashier, register |
| `purchase_bill` | A supplier bill received | Supplier, number, dates, lines, tax, purchase order reference, document hash |
| `supplier_payment` | A payment made | Bill reference, bank account used, wallet reference |
| `customer_invoice` | An invoice issued | Customer, lines, tax, due date |
| `customer_receipt` | Money received against an invoice | Invoice reference, bank line |
| `bank_line` | A line on a bank statement | Date, narration, amount, balance, reference |
| `stock_movement` | Stock in, out or adjusted | Item, quantity, unit cost, reason |
| `bank_detail_change` | A party's bank account changed | Party, old and new account, how it was confirmed |
| `journal_adjustment` | A manual or agent-prepared adjustment | Debit and credit lines, reason, approver |

## Data model

Postgres on Supabase, one database, every table carrying `tenant_id` with row-level security so that one business can never read another. Events are the source of truth; postings and reports are derived from them.

| Table | Key columns | Notes | Owner |
| --- | --- | --- | --- |
| `tenants` | name, country, currency, framework, fiscal year start | Root of every other table; the persona switch changes the active tenant | Daniyal |
| `users` | tenant, role, passkey credential | Roles: owner, finance, viewer; handled by Supabase Auth | Asharib |
| `mandates` | tenant, agent, per-payment cap, daily cap, allowed action types, version | Defaults come from the rulebook; the owner edits them in the interface | Daniyal |
| `parties` | kind, name, tax ID, current bank account, bank account changed at, on allow-list | One row per customer or supplier; a bank change also writes an event | Daniyal |
| `events` | type, occurred at, payload, source | Append-only canonical store, shaped by the ledger event types above | Daniyal |
| `bank_lines` | date, narration, amount, balance, reference, matched event | Raw imported lines kept separately so matching is repeatable | Daniyal |
| `documents` | kind, storage path, SHA-256 hash, extracted fields | The hash drives the same-file duplicate check | Daniyal |
| `items` | SKU, name, unit cost, price, stock, reorder level, supplier, lead time | Variants such as size and colour are separate SKUs for now | Daniyal |
| `purchase_orders`, `goods_received` | supplier, lines, status | Needed for the three-way match | Daniyal |
| `accounts`, `journal_lines` | account code, debit, credit, event reference | Posted from events by rules; a property test asserts debits equal credits | Daniyal |
| `matches` | bank line, event, pass, confidence | Output of reconciliation | Daniyal |
| `proposals`, `verdicts` | as in the contracts | A verdict is immutable once written | Daniyal |
| `audit_log` | previous hash, record, hash | Hash-chained; `GET /v1/audit` re-verifies the chain | Daniyal |
| `forecast_runs` | tenant, kind, parameters, result, created at | Cached cash forecasts and Launch Lab runs, so the demo is repeatable | Yahya |

**Framework neutrality.** Events hold facts ("sold 3 units for 9,000, cost 5,400"), not framework treatments. The `accounts` table maps each account to a framework-neutral class, and the rulepacks in `rulebook/` apply a framework's treatment when a statement is produced.

## Agents

Asharib owns the runtime and the prompts; Abdullah owns the rubric that says whether an answer is good (task B4). Models are set by environment variables, so cost and speed can be tuned without changing code.

| Agent | Model | Tools it may call | Output | Autonomy in the demo |
| --- | --- | --- | --- | --- |
| Controller | Haiku 5.5 (`claude-haiku-5-5`) for extraction; Sonnet 5.5 for exceptions | `/import/bills`, `/bills/check`, `/reconcile/*` | Typed bill records; Proposals of type `bill_approval` and `journal_adjustment` | Prepare |
| Treasurer | Sonnet 5.5 (`claude-sonnet-5-5`) | `/forecast/cash`, `POST /proposals` | Proposals of type `payment` | Act within mandate, up to the cap |
| CFO Strategist | Sonnet 5.5 | `/stage`, `/decisions/*` | A decision memo: recommendation, numbers, assumptions, risks | Advise |
| Growth Analyst | Sonnet 5.5 | `/inventory/analysis`, `/launch-lab/simulate` | A launch memo: go, pilot or don't, with the probability of breaking even | Advise |
| Guardian review | Opus 5.5 (`claude-opus-5-5`) | None; reads the Proposal and the raw rows only | The `adversarial` check in the Verdict | Can block; never acts |
| Guide | Haiku 5.5 | None; reads a static product guide and the current screen | Answers and highlighted controls | No access to money |

**Rules every agent follows**

- **Numbers come from tools.** An agent states a figure only if a tool returned it, and cites the tool result; memos use a fixed schema whose numeric fields are filled from tool output, not typed by the model.
- **Documents are data.** Text inside a bill, email or upload is never treated as an instruction; the extraction prompt says so, and the Guardian checks for pressure in the wording.
- **Structured outputs.** Proposals, memos and extractions are validated against schemas from `packages/contracts`; an invalid output is retried once, then raised as an error, never repaired silently.
- **Replay fallback.** Responses to the scripted demo questions are cached by prompt hash and used only if the live call fails; the interface marks a replayed answer as replayed.
- **Prompts are versioned** in the repository and scored against Abdullah's gold memos and rubric whenever they change.

## Guardian rules v1

These twelve rules are a starting draft for Abdullah to confirm or change in task B2. They live in `rulebook/guardian.yaml`, so changing a threshold does not need code. When several rules fire, the combined outcome is the strictest: `block`, then `escalate`, then `approve_with_conditions`, then `approve`.

| ID | Rule | Check | Outcome | Draft threshold |
| --- | --- | --- | --- | --- |
| G-01 | Payment above the agent's per-payment cap | Policy | Escalate | Cap from the mandate |
| G-02 | Payee is not on the allow-list | Policy | Escalate | None |
| G-03 | Payee's bank account changed within the cooling-off period | Policy | Block until the owner confirms with the supplier by phone | 7 days |
| G-04 | The same actor proposes and approves | Policy | Block | None |
| G-05 | Duplicate bill: same supplier with an amount within tolerance, a near-identical invoice number, or the same file | Policy | Block | Amount within 1%; number similarity at least 0.9 |
| G-06 | Bill fails the three-way match (no purchase order or no goods received) | Policy | Escalate | Price and quantity within 2% |
| G-07 | Lines and tax do not add up to the bill total | Arithmetic | Block | 0.01 of the currency unit |
| G-08 | Cash would fall below the owner's buffer after the payment | Policy | Approve with conditions (pay on the latest safe date); escalate if no safe date exists | Buffer from the mandate |
| G-09 | A claim in the proposal has no evidence reference | Evidence | Block | None |
| G-10 | Total payments today would exceed the daily cap | Policy | Escalate | Cap from the mandate |
| G-11 | Supplier tax registration is missing or malformed | Policy | Escalate | Format from the country pack |
| G-12 | The adversarial reviewer rates its concern as high | Adversarial | Escalate | Reviewer's rating is high |

Each rule has a test built from one of Abdullah's scenarios (task B3), so every row above is proved by a case in the answer key.

## Build conventions

Few rules, all of them for one reason: four people merging for three weeks must never block each other.

| Topic | Rule |
| --- | --- |
| Branches | `main` is always deployable. Work happens on `lane/ID-short-name`, for example `daniyal/D4-reconcile`. Asharib merges to `integration` on gate days. |
| Pull requests | Small (aim for under 400 changed lines), reviewed by someone else within 24 hours, merged only when the build is green. |
| Commit messages | Start with the task ID: `D4: add one-to-many pass`. |
| Mocks | Every box has a mock that returns fixtures in the contract's shape by 14 October. The web app switches with `NEXT_PUBLIC_API_MODE=mock` or `live`. |
| Contracts | Live in `packages/contracts`. A change is additive, or goes through the decision log with both signatories. |
| Rulebook | YAML in `rulebook/`; only Abdullah edits thresholds, and every change names the scenario that motivated it. |
| Languages and tools | TypeScript in strict mode with ESLint; Python 3.12 or later with Ruff and pytest; pnpm and Turborepo for the workspace. |
| Secrets | Never committed. Local values go in `.env.local`; deployed values live in Vercel, Fly.io and Supabase. One Claude key with a spending cap; if a key leaks, rotate it the same day. |
| Reproducibility | The generator takes a seed; `make db-reset` and `make demo-data` rebuild the same database on any machine. |
| Definition of done | Runs from a clean clone, has a passing test, leaves the contract unchanged or logs the change, has its status updated in the roadmap, and has been shown at a Friday demo. |

## Testing and evaluation

Because the generator writes an answer key, every claim we make in the submission can be backed by a number we computed. Targets below are proposals for the team to confirm.

| What we test | How | Proposed target | Owner |
| --- | --- | --- | --- |
| Planted issues are caught | Run all twelve scenarios through the Controller and Guardian; compare with the answer key | 12 of 12 caught; false alarms on clean bills reported | Daniyal, Abdullah |
| Reconciliation | Match rate and wrong-match count against the generator's ground truth | At least 95% auto-matched, no wrong matches | Daniyal |
| Stage Detector | Compare with Abdullah's hand classification for both personas | Agrees on both | Yahya, Abdullah |
| Decision calculators | Abdullah recomputes every demo number in a spreadsheet | Every number matches within the stated rounding | Abdullah |
| Cash forecast | Hold out the last 13 weeks of generator data; report weighted absolute percentage error against a naive last-year baseline | Beats the baseline | Yahya |
| Launch Lab range | Share of held-out launches whose outcome falls inside the low-to-high range | Reported honestly, whatever it is | Yahya |
| Memo quality | Score agent memos against the gold memos with the rubric | Average of at least 8 out of 10 | Abdullah, Asharib |
| Safety properties | Property tests: debits equal credits; the audit chain verifies and detects an edit; the wallet refuses a payment with no cleared verdict | All pass on every build | Daniyal |
| Whole demo | Two timed run-throughs from the live link and from cache | Both inside five minutes | Everyone |

**An honest limit.** Synthetic data proves that the pipeline works and that the checks catch known problems; it does not prove real-world forecast accuracy. The submission should say so, and if even a few months of anonymised data from one real shop can be obtained, one demo moment should use it.

## Cuts and open decisions

The vision document describes the product we want; this build is a slice of it. These are the deliberate differences, so nobody builds something we decided to skip.

| In the vision stack | In the three-week build |
| --- | --- |
| Expo mobile app | Installable web app on the phone; Expo only if time remains |
| Redis and Arq job queue | FastAPI background tasks and a scheduled call; no queue |
| Engine exposed as an MCP server | Plain HTTP tool definitions for the agents; an MCP wrapper is a Could |
| pgvector search | Not needed for the slice |
| Sentry, PostHog, Langfuse | Structured logs and a traces table; Langfuse is a Could |
| XBRL import, WhatsApp capture, voice, credit-ready pack | Parked |
| Live bank, wallet and tax-authority integrations | Simulated wallet; fixtures for tax checks |
| Managed Agents, batch processing, memory tool | Not used |

### Open decisions

| Decision | Options | Recommendation | Owner | Decide by |
| --- | --- | --- | --- | --- |
| Phone app | Installable web app or Expo | Installable web app: one codebase, and passkeys work in current mobile browsers | Asharib | Wed 14 Oct |
| Wallet | Simulated, or a bank's sandbox API | Simulated, and labelled as simulated in the demo | Daniyal | Wed 14 Oct |
| Where Chronos-2 runs | In the engine container on CPU, or skip it for a classical model | Try CPU in the engine; fall back to the classical models in StatsForecast if memory or speed is a problem | Yahya | Fri 16 Oct |
| Bill inputs for extraction | JSON only, or also generated PDFs and photos | The generator renders about twenty bills as PDFs and photos so extraction is demonstrated for real | Daniyal, Asharib | Sat 17 Oct |
| Real business data | Synthetic only, or three months of anonymised real data | Ask one friendly shop; use it in one moment only | Abdullah | Wed 21 Oct |
| Interface language | English only, or also Urdu and Chinese | English interface; the command bar accepts Urdu and Chinese questions, since Claude reads both | Asharib | Thu 22 Oct |
| Guardian reviewer cost | Opus on every proposal, or only above a value | Opus on every proposal in the demo; threshold set by an environment variable | Asharib | Fri 23 Oct |

### Parked after G1

Ideas that arrive after 14 October go here instead of into the sprint:

- WhatsApp and photo capture of bills
- Urdu and Chinese voice
- Full CAS rulepack and XBRL import of published statements
- Credit-ready pack for a lender
- Consolidation across entities and ERP connectors
- Live tax-authority invoice checks
