# Asharib lane (fiona-19)

Dates follow PLAN.md §4 (submission Tue 20 Oct, 20:59 PKT).

| ID | Task | Status | Due | Updated | Note |
|---|---|---|---|---|---|
| A1 | Monorepo (pnpm, Turborepo, uv), CI, lint, env template, engine skeleton with router auto-discovery | done | Tue 13 Oct | 2026-10-13 | verify-a1 PASS (fresh clone, frozen install, pnpm dev, 4/4 healthy in 169s, no secrets); 9c0aa77, 3b30035, 5d9d81c. CI not yet run (no GitHub repo) |
| S2 | Accounts and secrets kit (checklist, `.env.example`, env checks, smoke test, rotation runbook, gitleaks) | done (kit) | Tue 13 Oct | 2026-10-13 | Kit verified; accounts and keys are Asharib's: docs/lane-a/S2_SETUP.md. `pnpm smoke:keys` proves them once created |
| A2 | Contracts core (Proposal, Verdict, Finding, LedgerEvent, Mandate, Figure, Money) + TS/Pydantic generation | todo | Wed 14 Oct (G1) | 2026-10-13 | Inputs: FORMATS.md sign-off, Abdullah's Mandate shape (4f4fc26), Yahya's Figure list, proposal types per PLAN.md |
| A3 | Web shell, design system, themes, screen kit, deployed on mocks | todo | Thu 15 Oct | 2026-10-13 | |
| A4 | Bill extraction + Controller / Treasurer / CFO agents | todo | Fri 16 Oct (G2) | 2026-10-13 | Recorded-response stub until the Anthropic key exists |
| A5 | Briefing, approvals, mandates and autonomy-ladder UI (visible and enforced) | todo | Sat 17 Oct | 2026-10-13 | |
| A6 | Guardian adversarial review (Opus) + verdict combiner | todo | Sat 17 Oct | 2026-10-13 | |
| A7 | Council mode on the financing question | todo | Sun 18 Oct | 2026-10-13 | |
| A8 | Live link, GitHub push, replay cache, README + deployment instructions | todo | Sun 18 Oct (G3) | 2026-10-13 | |
| A10 | Command bar with voice (Tier 2) | todo | Mon 19 Oct | 2026-10-13 | Only on top of a green Tier 1 |
| A9 / A11 / A12 | Onboarding extras, memory/batch/observability, accountant + lender views | parked (Tier 3) | Shenzhen final | 2026-10-13 | Moved by fiona-b7's re-plan |
