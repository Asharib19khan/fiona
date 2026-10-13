# Fiona: Build Plan (re-planned for the 20 October deadline)

Owner: fiona-b7 (orchestrator session). Updated Tue 13 Oct 2026, 20:00 PKT.
This file overrides the *Build Blueprint* and *Team Roadmap* wherever they disagree. Contracts, data model, Guardian rules and conventions in the Blueprint still apply unless changed here.

## 0. The deadline moved: read this first

The official rules (PBCSF Appendix 2, International Track) say: **"Registration and submission share the same deadline: October 20, 2026, 23:59 (Beijing Time, UTC+8)"**, which is **Tue 20 Oct, 20:59 PKT**. Submissions can be updated any time before then, and the latest version counts. The 2 November date in our documents came from a tentative IEEE chapter post and is wrong.

| Date | Event |
| --- | --- |
| **Tue 20 Oct, 20:59 PKT** | Registration and submission close. Nothing changes after this. |
| 20–31 Oct | Online review by WeBank experts and university scholars |
| 31 Oct | Finalists announced |
| 20–23 Nov | Shenzhen: check-in, WeBank HQ visit, Grand Final. At least one member must attend in person. |

**Topic E, verbatim:** *"A finance copilot for small-business owners, offering financing-option matching, cash-flow management with alerts, and business financial analysis."*
**Scoring:** task completion 40%, security and compliance 30%, innovation and interaction 30%. Everything is in English.

**Required submission (English):**

| # | Item | Rule | Owner |
| --- | --- | --- | --- |
| 01 | Technical documentation | System architecture, core algorithm description, security design | Abdullah, with Asharib |
| 02 | Presentation deck | For a final presentation of 10 minutes or less | Abdullah |
| 03 | Demo video | Optional, 5 minutes or less (we submit one, because item 06 needs it) | Abdullah (script), Asharib (recording) |
| 04 | Source code | GitHub repository link, README, deployment instructions, test cases | Asharib |
| 05 | Security self-assessment report | Permission-tier implementation and a known-risk list | Abdullah, with Daniyal and Asharib |
| 06 | Execution evidence | Simulated-account or sandbox operation logs, plus the demo video | Daniyal (log export), Abdullah (package) |

## 1. Scope: everything, in order of what is scored

Nothing is thrown away, but the order changes. **Tier 1 must be excellent by Sun 18. Tier 2 goes in only on top of a green Tier 1, by the Mon 19 freeze. Tier 3 is built 21 Oct to 19 Nov for the Shenzhen final** (finalists present live, so the full vision lands there).

| Tier | What | Why |
| --- | --- | --- |
| **1. Scored core** | **Financing-option matching** (new: catalogue, eligibility, cost, debt-service coverage after borrowing, ranked options, CFO memo). **Cash-flow management with alerts** (13-week forecast, alert findings, briefing cards, payment timing, Treasurer payments within mandate). **Business financial analysis** (Stage Detector, ratios, health score, simple statements, reconciliation and duplicate findings). **The participation loop:** bill → extraction → checks → Guardian (4 checks) → mandate tiers → sandbox wallet or owner approval → ledger → hash-chained audit. **Security:** permission tiers (autonomy ladder and mandates) enforced and visible, RLS, documents treated as data (with a prompt-injection test), secrets hygiene. Briefing-first web app, live link, all six deliverables. | Task completion 40%, security 30% |
| **2. Innovation extras** | Council mode (loan versus investor debate, dissent on record), explain-any-number, command bar with voice (English, Urdu, Chinese), Launch Lab (simple Monte Carlo), the Shenzhen persona and tenant switch, inventory analytics, dividend decision, POS reconciliation, framework lens for inventory | Innovation and interaction 30% |
| **3. Shenzhen final** | Expo native app (the installable web app covers Oct 20), the other three decisions, full Launch Lab with Chronos-2, rulepacks, XBRL, consolidation and FX, connectors (accounting import, email, WhatsApp), FBR and fapiao simulators, accountant console, lender view, MCP server, Sentry, PostHog and Langfuse, memory tool, batch, industry-pack workflows | Builds the full vision for the live final |

## 2. Gates

| Gate | When (PKT) | What must be true |
| --- | --- | --- |
| G1 | **Wed 14, 23:59** | Contracts core frozen; every endpoint has a mock; rulebook v1, Guardian rules and mandates; generator v0 real files; workspace builds; **registration sent** |
| G2 | **Fri 16, 23:59** | Generator v1 (Karachi, 24 months, planted issues, answer key); importers and ledger; Stage Detector and ratios; cash forecast and alerts on ledger data; financing catalogue and matcher v1; reconciliation and duplicates; Guardian deterministic checks; bill extraction live; web shell with the briefing on live data; GitHub repository pushed |
| G3 | **Sun 18, 23:59** | The whole Tier 1 loop works end to end on the live link, plus council mode. **Submission v1 uploaded**, with deliverables 01 to 06 in first draft. |
| G4 | **Mon 19, 18:00** | Feature freeze: Tier 2 is in or out. Video recorded, deck final, security report final, execution logs exported, finance QA signed. |
| G5 | **Tue 20, 17:00** | Final submission update uploaded, nearly 4 hours before the 20:59 cut-off. After that, only fixes for something broken. |

## 3. Sessions and folder ownership

| Session | Lane | Owns (only the owner writes here) |
| --- | --- | --- |
| fiona-b7 | Orchestrator | `docs/orchestrator/`; final say on scope, dates, cuts and contract disputes |
| fiona-19 | Asharib: platform, experience, agents | root config, CI, deploy, `apps/web` (shell, design system, agent surfaces), `packages/ui`, `packages/contracts` (signed off with Daniyal), `services/agents`, `services/guardian`, `services/engine/{pyproject.toml,__init__.py,app/}`, `docs/decision-log.md`, `README.md` |
| fiona-fa | Abdullah: finance brain, analysis, deliverables | `rulebook/`, `services/engine/analysis/`, `services/engine/frameworks/`, `evals/`, `docs/pitch/`, `docs/submission/` |
| fiona-b0 | Daniyal: data, ledger, safety | `supabase/`, `data/generator/`, `data/fixtures/`, `services/engine/ledger/`, `services/engine/guardian_checks/`, `services/engine/connectors/` |
| fiona-79 | Yahya: forecasting, decisions, financing | `services/engine/forecast/`, `services/engine/decisions/`, `services/engine/financing/`, `data/public/` |

**Engine conventions (D-010):** the package is `engine`; import it as `engine.<module>`. Each module folder has `__init__.py`, and endpoints live in `<module>/api.py`, which exposes `router` (an APIRouter with full `/v1/...` paths) that `app/main.py` auto-mounts. The database helper is `python -m engine.ledger.db`. Run commands are `pnpm db:reset`, `pnpm demo-data`, `pnpm dev` and `pnpm test`.

**Domain screens** are built by the domain lane under `apps/web/app/(app)/<route>/`, using only `packages/ui` and the screen kit; fiona-19 reviews them.

| Routes | Owner |
| --- | --- |
| `forecast`, `financing`, `inventory`, `launch-lab` | Yahya |
| `bills`, `reconcile`, `wallet`, `audit` | Daniyal |
| `analysis` (stage, ratios, health, statements) | Abdullah |

fiona-19 owns the briefing, approvals, mandates and autonomy, council, command bar, explain drawer and onboarding.

## 4. Lane queues (Tier 1 first)

### Asharib lane (fiona-19)

| ID | Task | Due |
| --- | --- | --- |
| A1 | Workspace commit (package.json, Turborepo, engine skeleton, CI) | Tue 13, tonight |
| A2 | Contracts core: Proposal (types: payment, bill_approval, journal_adjustment, send_document, purchase_order, reconciliation_match), Verdict, Finding, LedgerEvent, Mandate (Abdullah's shape), Figure, Money; TS client generation | **Wed 14 (G1)** |
| A3 | Web shell, design system, **screen kit**, deployed on mock data | Thu 15 |
| A4 | Agent runtime: bill extraction (Haiku, structured output, citations, timeouts), then the Controller, Treasurer and CFO Strategist with tool use | **Fri 16 (G2)** |
| A5 | Briefing, approvals, **mandates and autonomy ladder UI** (the permission tiers the judges score), explain-any-number drawer | Sat 17 |
| A6 | Guardian adversarial review (Opus) and the verdict combiner | Sat 17 |
| A7 | Council mode on the financing question (CFO, Treasurer, Growth and Guardian), producing a memo with the dissent on record | Sun 18 |
| A8 | Live link (Vercel, Fly.io, Supabase), GitHub push, demo replay cache, installable web app, README and deployment instructions | **Sun 18 (G3)** |
| A10 | Command bar (Ctrl+K), typed or spoken in English, Urdu and Chinese | Mon 19 (Tier 2) |

### Daniyal lane (fiona-b0)

| ID | Task | Due |
| --- | --- | --- |
| D1 | Schema, RLS, auth shim, seed | **Wed 14 (G1)** |
| D2a | Generator v0, real seed-42 files | **Wed 14 (G1)** |
| D2 | Generator v1, Karachi: 24 months, every planted issue, answer key, rising purchase costs, loan schedule, lease, opening balances, about 20 rendered bill PDFs | Thu 15 |
| D3 | Importers and journal postings (debits equal credits, tested by property test) | **Fri 16 (G2)** |
| D4 | Reconciliation (passes 1 to 3, plus pass-4 intake) and the duplicate detector | Fri 16 |
| D5 | Guardian deterministic checks (all twelve rules) and mandate enforcement | Sat 17 |
| D6 | Wallet sandbox (caps, allow-list, cooling-off, conditions), hash-chained audit, **operation-log export** (deliverable 06) | **Sun 18 (G3)** |
| — | Screens: bills (with the Guardian verdict), reconcile, wallet, audit | Sun 18 |
| D7 | Shenzhen persona (CNY, CAS) and tenant switch | Mon 19 (Tier 2) |
| D9 | POS reconciliation | Mon 19 (Tier 2) |

### Yahya lane (fiona-79)

| ID | Task | Due |
| --- | --- | --- |
| Y0 | Schemas and mocks for every endpoint | **Wed 14 (G1)** |
| Y1 | 13-week cash forecast, buffer breach, **alert findings** | **Fri 16 (G2)** |
| Y10 | **Financing-option matcher** (new): reads Abdullah's catalogue; eligibility per option; effective annual cost, instalment, debt-service coverage and runway after borrowing; ranked with reasons; "insufficient data, need X" | **Fri 16 (G2)** |
| Y4 | Decisions: debt versus equity (Tier 1); dividend versus reinvest (Tier 2) | Sat 17 |
| Y6 | Findings feed ranked by money at stake | Sat 17 |
| Y8 | Payment-timing optimiser (early-payment discount against the cost of money) | Sun 18 |
| — | Screens: forecast, financing | Sun 18 |
| Y3 | Inventory analytics, and its screen | Mon 19 (Tier 2) |
| Y5 | Launch Lab, simple Monte Carlo | Mon 19 (Tier 2) |
| Y7 | Evaluation numbers: forecast backtest against a naive baseline | Mon 19 |

### Abdullah lane (fiona-fa)

| ID | Task | Due |
| --- | --- | --- |
| S1 | Rules summary in `docs/pitch/S1-rules.md` | Done |
| B1 | Rulebook v1 (stage rules, decision thresholds, stage priorities, `launch_lab.yaml`) | **Wed 14 (G1)** |
| B2 | Guardian rules G-01 to G-12, default mandates, and the Mandate shape sent to fiona-19 | **Wed 14 (G1)** |
| B14 | **Financing catalogue** (new) in `rulebook/financing.yaml`: option types (term loan, running finance, invoice discounting, supplier credit, equipment lease, government and central-bank refinance schemes, microfinance, equity or angel investment, revenue-based financing) with eligibility rules, cost ranges, tenors and collateral, for Pakistan and China. **Every row gives its source and as-of date, and any example product is labelled "illustrative".** | Thu 15 |
| B3 | Planted-issue scenarios with expected verdicts (with Daniyal) | Thu 15 |
| Y2 | Stage Detector, ratio library, health score, `metrics.yaml` | **Fri 16 (G2)** |
| B4 | Gold memos (financing choice, debt versus equity) and rubric | Sat 17 |
| — | Screen: analysis | Sun 18 |
| D-01 to 06 | Deliverables, first drafts: technical documentation, deck, video script, security self-assessment, execution-evidence package | **Sun 18 (G3)** |
| B6 | Finance QA: recompute every number shown in the demo | **Mon 19 (G4)** |
| D-final | All deliverables final; video recorded with Asharib | **Mon 19 (G4)** |

## 5. Engineering rules

1. **The model decides, the engine computes, the Guardian checks.** Claude is called only in `services/agents` and `services/guardian`. Engine modules never call Claude. Where a model is needed, an agent submits a suggestion as data and the engine verifies it.
2. **Every number is a Figure**, with value or money, `metric_id`, inputs and `source_refs`. Money is integer minor units plus a currency code, and floats never cross a module boundary or reach a response.
3. **Documents are data.** Instructions inside bills, emails and uploads are never followed. Keep a test that proves it.
4. **Quality bar.** Every screen has loading, empty, error and success states and works at 375px and 1440px with no console errors. Every AI call has a timeout, and every stream ends with a done or error event. There are no hardcoded AI answers except the labelled demo replay cache.
5. **Tests ship with every task** (the judges ask for test cases): pytest with Hypothesis for the engine, Vitest and Playwright for the web app.
6. **Licensing** (the rules require it): use only properly licensed code and data. Do not commit Kaggle datasets (M5, Favorita). Prefer synthetic data and UCI Online Retail II (CC BY 4.0), and keep `THIRD_PARTY_NOTICES.md` current.

## 6. Git: trunk-based in a shared working tree

- Everyone works on `main` in `Y:\Fiona`. **Never** run checkout, switch, stash, reset, clean, rebase, `git add -A`, `git add .` or `commit -a`.
- Commit only your own paths: `git add <paths>` then `git commit -m "D4: one-to-many pass" -- <paths>`. If you hit `index.lock`, retry.
- Run your lane's tests before you commit. Shared lockfile changes go in the same commit, and fiona-19 is told.

## 7. Reporting

- Keep `docs/status/<lane>.md` current, using the columns ID, Task, Status, Due, Updated, Note.
- Message fiona-b7 when a task is done (say how it was verified), when you are blocked for more than 30 minutes, when a date is at risk, and before any contract change.
- Lanes message each other directly to coordinate, and copy fiona-b7 on contracts, dates and scope.

## 8. Local environment

- No Docker, `make`, Supabase CLI, system Postgres or `gh`. Node 24, Python 3.12 / 3.13, uv and corepack (pnpm) are available.
- Database: portable Postgres 17 outside the repo (Daniyal's helper, `DATABASE_URL`); Supabase cloud for the deployed demo. Tests use their own throwaway database.
- pgvector: cloud only; locally it sits in a separate, skippable migration.

## 9. Orchestrator rulings

| # | Date | Ruling |
| --- | --- | --- |
| R1 | 13 Oct | Fixture formats are approved: `*_minor` integers everywhere, deterministic ULIDs, `customer_receipt` events come from reconciliation. |
| R2 | 13 Oct | The owner's cash buffer is a tenant policy (`tenant.policies.cash_buffer_minor`), not a Mandate field. |
| R3 | 13 Oct | One source of numbers: Daniyal's seeded generator. No parallel datasets. |
| R4 | 13 Oct | G-08 tests the payment's incremental effect against the baseline forecast. |
| R5 | 13 Oct | The generator models rising purchase costs, a lease, a loan schedule and opening balances; sale-event `cost_minor` is informational. |
| R6 | 13 Oct | The deadline is Tue 20 Oct, 20:59 PKT (official rules). The scope is ordered by scoring weight into three tiers (§1); Tier 3 is built for the Shenzhen final. |
| R8 | 13 Oct | Tenancy (R15 from fiona-19): engine endpoints take the tenant only via `engine.app.tenancy.TenantId`, never as a query or body field. Mock mode uses the `X-Fiona-Tenant` header; live mode fails closed with 401. |
| R9 | 13 Oct | The Verdict check carries its own `outcome`, and the strictest outcome wins. Conditions are machine-readable so the wallet can enforce them. Health is shown as categorical bands, never as a score. G-13 is Tier 1. Karachi Treasurer caps are PKR 150k per payment and 450k per day. |
| R7 | 13 Oct | Financing-option matching is Tier 1: it is the first phrase of Topic E and was missing from our plan. |

## 10. Only Asharib (the user) can do these

| Item | When | Unblocks |
| --- | --- | --- |
| **Register the team** (the form comes from fintechathon.g-ican.com; questions to wangyr@pbcsf.tsinghua.edu.cn). Registration closes with the submission deadline, and the organiser's reply may take days. | **Wed 14** | Everything |
| Confirm all four members are full-time students at accredited universities outside mainland China, Hong Kong, Macao and Chinese Taipei, that at least 60% are non-Chinese nationals, and who can travel to Shenzhen on 20–23 Nov | Wed 14 | Eligibility |
| Find out how the submission is uploaded (portal or email) | Wed 14 | G3 |
| Anthropic API key or keys with a spending cap, in `.env.local` | **Wed 14** | A4, A6, all agents |
| Supabase, Vercel and Fly.io accounts | Wed 14 | Deploys |
| GitHub repository (public by submission) and `gh auth login` on this machine | Fri 16 | Deliverable 04 |
