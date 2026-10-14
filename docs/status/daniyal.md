> **HANDOFF (held Wed 14 Oct, fiona-b0, by orchestrator order)**
> 1. Done: D1, D2a; A2 contracts signed off (condition met in 5a4295f, rc.2); mandates.json now has status + created_at and validates as contract Mandate (4978762).
> 2. Half-done: D2. The v1 persona config is parked at `data/generator/wip/karachi_apparel_v1.toml.wip` (24 months from 1 Jul 2024, B3 plants with Abdullah's IDs, proposals, loan, leases, payroll, assets, stock builds, NRV, POS anomalies). `build.py` is still v0; no v1 code is written yet.
> 3. Next step: write build.py v1 for that config (calendar and holidays, cost and price factors, plants, proposals as contract ProposalDraft with Evidence kinds bill/document and created_by Actor, finance schedules, a holdout through as_of+91 days, ~20 PDFs). Move the .wip file back to personas/, then tune: FY26 CFO < -2% of revenue (raise stock builds, payroll ~2.9M/month, drawings), FY25 growth, week-7 dip (weeks from as_of+1) below 200,000,000 with weeks 1-6 above, 85-90% of bills within the cap. Then D3.
> 4. Files: data/generator/{build.py, core.py, render.py, write.py, __init__.py, tests/}, data/fixtures/FORMATS.md.
> 5. Open: 4 B3 totals are unreachable with 18% half-up tax, so plants come out 1 minor unit higher (fiona-fa told); clearing = receivable (fiona-fa told).

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
