# Asharib lane (fiona-19)

Dates follow PLAN.md §4 (submission Tue 20 Oct, 20:59 PKT).

| ID | Task | Status | Due | Updated | Note |
|---|---|---|---|---|---|
| A1 | Monorepo (pnpm, Turborepo, uv), CI, lint, env template, engine skeleton with router auto-discovery | done | Tue 13 Oct | 2026-10-13 | verify-a1 PASS (fresh clone, frozen install, pnpm dev, 4/4 healthy in 169s, no secrets); 9c0aa77, 3b30035, 5d9d81c. CI not yet run (no GitHub repo) |
| S2 | Accounts and secrets kit (checklist, `.env.example`, env checks, smoke test, rotation runbook, gitleaks) | done (kit) | Tue 13 Oct | 2026-10-13 | Kit verified; accounts and keys are Asharib's: docs/lane-a/S2_SETUP.md. `pnpm smoke:keys` proves them once created |
| A2 | Contracts core (Proposal, Verdict, Finding, LedgerEvent, Mandate, Figure, Money) + TS/Pydantic generation | done (1.0.0-rc.2; Daniyal signed off, Asharib pending) | Wed 14 Oct (G1) | 2026-10-14 | 98 definitions; TS 37 tests, Python 25 tests incl. all 7,116 fixture events; verdict hash identical in TS and Python; services import fiona_contracts |
| A3 | Web shell, design system, themes, screen kit, deployed on mocks | todo | Thu 15 Oct | 2026-10-13 | |
| A4 | Bill extraction + Controller / Treasurer / CFO agents | todo | Fri 16 Oct (G2) | 2026-10-13 | Recorded-response stub until the Anthropic key exists |
| A5 | Briefing, approvals, mandates and autonomy-ladder UI (visible and enforced) | todo | Sat 17 Oct | 2026-10-13 | |
| A6 | Guardian adversarial review (Opus) + verdict combiner | todo | Sat 17 Oct | 2026-10-13 | |
| A7 | Council mode on the financing question | todo | Sun 18 Oct | 2026-10-13 | |
| A8 | Live link, GitHub push, replay cache, README + deployment instructions | todo | Sun 18 Oct (G3) | 2026-10-13 | |
| A10 | Command bar with voice (Tier 2) | todo | Mon 19 Oct | 2026-10-13 | Only on top of a green Tier 1 |
| A9 / A11 / A12 | Onboarding extras, memory/batch/observability, accountant + lender views | parked (Tier 3) | Shenzhen final | 2026-10-13 | Moved by fiona-b7's re-plan |

## HANDOFF (paused 2026-10-14 after A2; the orchestrator runs one lane at a time)
- **State:** A1, S2 (kit), A2 done and committed. A2 is `1.0.0-rc.1`. Freeze and tag `contracts-v1` only after Daniyal's and Asharib's sign-off (C2/C8).
- **Resume with:** `pnpm install && pnpm gen && pnpm test`, then A3 (shell + screen kit, due Thu 15): Part II of docs/lane-a/CLAUDE_CODE_PROMPT.md, PLAN.md §2 (the screen kit for domain lanes).
- **Contracts workflow:** edit `packages/contracts/schemas/*.yaml`, run `pnpm gen` (needs uv; dumps the engine OpenAPI too), and commit the generated files. If a scenario's verdict changes, run `uv run --project python python tools/seal_verdicts.py` in packages/contracts.
- **Open asks:** Daniyal: add `status` and `created_at` to data/fixtures mandates.json (final Mandate shape); swap `?tenant_id=` for `TenantId`. Yahya: `?tenant_id=` → `TenantId`; move stand-ins to `fiona_contracts`. Abdullah: the Mandate shape is used as given.
- **LLM:** no API key. A4/A6 build the provider interface from D-017 (`claude_cli` locally, `replay` for the public link).
- **Not verified here:** Docker builds (no Docker locally; CI builds the images).

