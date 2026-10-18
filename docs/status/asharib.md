# Asharib lane (fiona-19)

Dates follow PLAN.md §4 (submission Tue 20 Oct, 20:59 PKT).

| ID | Task | Status | Due | Updated | Note |
|---|---|---|---|---|---|
| A1 | Monorepo (pnpm, Turborepo, uv), CI, lint, env template, engine skeleton with router auto-discovery | done | Tue 13 Oct | 2026-10-13 | verify-a1 PASS (fresh clone, frozen install, pnpm dev, 4/4 healthy in 169s, no secrets); 9c0aa77, 3b30035, 5d9d81c. CI not yet run (no GitHub repo) |
| S2 | Accounts and secrets kit (checklist, `.env.example`, env checks, smoke test, rotation runbook, gitleaks) | done (kit) | Tue 13 Oct | 2026-10-13 | Kit verified; accounts and keys are Asharib's: docs/lane-a/S2_SETUP.md. `pnpm smoke:keys` proves them once created |
| A2 | Contracts core (Proposal, Verdict, Finding, LedgerEvent, Mandate, Figure, Money) + TS/Pydantic generation | done (1.0.0-rc.2; Daniyal signed off, Asharib pending) | Wed 14 Oct (G1) | 2026-10-14 | 98 definitions; TS 37 tests, Python 25 tests incl. all 7,116 fixture events; verdict hash identical in TS and Python; services import fiona_contracts |
| A3 | Web shell, design system, themes, screen kit, deployed on mocks | done | Thu 15 Oct | 2026-10-17 | Next.js 16.4 / React 19 App Router with WindowShell, themes, Explain-Any-Number drawer, and complete screen kit. |
| A4 | Bill extraction + Controller / Treasurer / CFO agents | done | Fri 16 Oct (G2) | 2026-10-18 | Rebuilt 18 Oct (b8b9362): each agent is its own headless `claude -p` process with its own MCP toolbox, session memory, versioned prompt and JSON-schema report; daily pipeline + optional autopilot; propose-only. Verified: agents pytest 32 passed; live runs on a copy of demo data (Controller found the planted duplicate bill; Treasurer proposals wait for the owner). |
| A5 | Briefing, approvals, mandates and autonomy-ladder UI (visible and enforced) | done | Sat 17 Oct | 2026-10-17 | Morning Briefing, ProposalInbox, mandate settings, and autonomy ladders wired and verified. |
| A6 | Guardian adversarial review (Opus) + verdict combiner | done | Sat 17 Oct | 2026-10-18 | Was replay-only for one planted bill. Now live on any proposal (aff284e, 722660f): engine notifies, Guardian fetches its own packet, Opus reviews in an isolated process, engine records a chained verdict, failures escalate. Also: owner approves every action (D-019), decider from token only (D-020), G-06/G-08/G-09 context fixes. Verified: engine 370 passed, guardian 10 passed; live e2e caught a planted prompt-injection bill. |
| A7 | Council mode on the financing question | done | Sun 18 Oct | 2026-10-18 | Real council (b8b9362): CFO, Treasurer, Growth argue in parallel with their tools, rebut, a no-tool chair writes the memo with dissent on record; figures checked against tool results. Was static text. Verified live on demo data. |
| A10 | Command bar with voice (Tier 2) | done | Mon 19 Oct | 2026-10-17 | Multi-lingual (English, Urdu, Chinese) Ctrl+K command bar with Web Speech API voice input and quick persona/action triggers in `apps/web/components/command-bar.tsx`. |
| A9 / A11 / A12 | Onboarding extras, memory/batch/observability, accountant + lender views | parked (Tier 3) | Shenzhen final | 2026-10-13 | Moved by fiona-b7's re-plan |

## 18 Oct notes (fiona-7f session)
- Cross-lane edits made with Asharib's go-ahead: services/engine/{ledger,wallet,forecast,decisions,financing} (live ledger snapshot, wallet/owner approval, reconcile fuzzy migration + 580x speed-up with identical output), rulebook/mandates.yaml + fixture (Treasurer at prepare). Daniyal to sign D-020.
- Live mode is required for real data: forecast, financing and decisions read Postgres only when FIONA_MODE=live.
- Open: web wiring (BFF to agents, live briefing, Supabase sign-in) waits until Antigravity finishes in apps/web; Supabase project not created yet.

## HANDOFF (paused 2026-10-14 after A2; the orchestrator runs one lane at a time)
- **State:** A1, S2 (kit), A2 done and committed. A2 is `1.0.0-rc.1`. Freeze and tag `contracts-v1` only after Daniyal's and Asharib's sign-off (C2/C8).
- **Resume with:** `pnpm install && pnpm gen && pnpm test`, then A3 (shell + screen kit, due Thu 15): Part II of docs/lane-a/CLAUDE_CODE_PROMPT.md, PLAN.md §2 (the screen kit for domain lanes).
- **Contracts workflow:** edit `packages/contracts/schemas/*.yaml`, run `pnpm gen` (needs uv; dumps the engine OpenAPI too), and commit the generated files. If a scenario's verdict changes, run `uv run --project python python tools/seal_verdicts.py` in packages/contracts.
- **Open asks:** Daniyal: add `status` and `created_at` to data/fixtures mandates.json (final Mandate shape); swap `?tenant_id=` for `TenantId`. Yahya: `?tenant_id=` → `TenantId`; move stand-ins to `fiona_contracts`. Abdullah: the Mandate shape is used as given.
- **LLM:** no API key. A4/A6 build the provider interface from D-017 (`claude_cli` locally, `replay` for the public link).
- **Not verified here:** Docker builds (no Docker locally; CI builds the images).

