> **HANDOFF (paused Wed 14 Oct, fiona-b0, by orchestrator order)**
> 1. Done: D1 (schema, RLS, seed) and D2a (generator v0, seed-42 fixtures), both committed; FORMATS.md signed off by fiona-19; Linux PG17 checksum pinned.
> 2. Half-done: D2. The v1 persona config is written and parked at `data/generator/wip/karachi_apparel_v1.toml.wip` (24 months from 1 Jul 2024, holidays and seasons, cost and price inflation, two suppliers per category, loan, leases, payroll, assets, stock builds, NRV, POS anomalies, every B3 plant and proposal). `build.py` is still v0.
> 3. Next step: rewrite `data/generator/build.py` to v1 for that config (plants, proposals, finance schedules, holdout, PDFs), move the .wip file back to `personas/karachi_apparel.toml`, then tune for: FY26 CFO < -2% of revenue with CFI and CFF < 0, FY25 growth; week-7 dip (weeks from as_of+1) below 200,000,000 with weeks 1-6 above; 85-90% of bills within the 150k cap. Then extend the tests and FORMATS.md.
> 4. Files: data/generator/{build.py, core.py, render.py, write.py, __init__.py, tests/}, data/fixtures/FORMATS.md.
> 5. Open: totals 14,950,000 / 9,900,000 / 9,500,000 / 7,400,000 can't be reached as subtotal + round(18% x subtotal), so the plants will be 1 minor unit off (tell fiona-fa). Answer fiona-fa: `clearing` = receivable, and add neutral classes prepayments and other_opex plus a current/non-current loan split.

# Daniyal lane status (fiona-b0)

Dates follow docs/orchestrator/PLAN.md §4 (re-plan for the 20 Oct deadline).

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| D2a-F | Fixture file formats (`data/fixtures/FORMATS.md`) | done | Wed 14 | Tue 13 | Orchestrator rulings applied; awaiting fiona-19 objections until G1 |
| D1 | Ledger schema: migrations, RLS, auth shim, seed | done | Wed 14 | Tue 13 | 15 tables, forced RLS, 47 tests; `python -m engine.ledger.db reset` + `seed` |
| D2a | Generator v0: Karachi, 2 months, seed 42 | done | Wed 14 | Tue 13 | `data/fixtures/ten_karachi_apparel/`; 14 tests (reproducible, coherent, demo threads) |
| D2 | Generator v1 (Karachi only): 24 months, all planted issues, answer key, rising costs, loan, lease, opening balances, ~20 PDFs | doing | Thu 15 | Wed 14 | Also tune cash so the week-7 dip exists (cash grows too fast in v0) |
| D3 | Importers + postings + debits=credits property test | todo | Fri 16 | Tue 13 | |
| D4 | Reconciliation passes 1-3, pass-4 intake, duplicate detector | todo | Fri 16 | Tue 13 | |
| D5 | Guardian deterministic checks G-01..G-13 + mandate enforcement | todo | Sat 17 | Tue 13 | G-14/G-15 Tier 2 if green early |
| D6 | Wallet sandbox, hash-chained audit, operation-log export | todo | Sun 18 | Tue 13 | Export: JSONL + readable report + chain verification |
| W | Screens: bills, reconcile, wallet, audit | todo | Sun 18 | Tue 13 | fiona-19 screen kit |
| D7 | Shenzhen persona + tenant switch (Tier 2) | todo | Mon 19 | Tue 13 | Only on green Tier 1 |
| D9 | POS reconciliation (Tier 2) | todo | Mon 19 | Tue 13 | |
| D10-D12 | Invoices, tax simulators, connectors (Tier 3) | todo | - | Tue 13 | |
