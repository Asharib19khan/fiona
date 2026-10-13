# Daniyal lane status (fiona-b0)

Dates follow docs/orchestrator/PLAN.md §4 (re-plan for the 20 Oct deadline).

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| D2a-F | Fixture file formats (`data/fixtures/FORMATS.md`) | done | Wed 14 | Tue 13 | Orchestrator rulings applied; awaiting fiona-19 objections until G1 |
| D1 | Ledger schema: migrations, RLS, auth shim, seed | done | Wed 14 | Tue 13 | 15 tables, forced RLS, 47 tests; `python -m engine.ledger.db reset` + `seed` |
| D2a | Generator v0: Karachi, 2 months, seed 42 | done | Wed 14 | Tue 13 | `data/fixtures/ten_karachi_apparel/`; 14 tests (reproducible, coherent, demo threads) |
| D2 | Generator v1 (Karachi only): 24 months, all planted issues, answer key, rising costs, loan, lease, opening balances, ~20 PDFs | todo | Thu 15 | Tue 13 | Also tune cash so the week-7 dip exists (cash grows too fast in v0) |
| D3 | Importers + postings + debits=credits property test | todo | Fri 16 | Tue 13 | |
| D4 | Reconciliation passes 1-3, pass-4 intake, duplicate detector | todo | Fri 16 | Tue 13 | |
| D5 | Guardian deterministic checks G-01..G-13 + mandate enforcement | todo | Sat 17 | Tue 13 | G-14/G-15 Tier 2 if green early |
| D6 | Wallet sandbox, hash-chained audit, operation-log export | todo | Sun 18 | Tue 13 | Export: JSONL + readable report + chain verification |
| W | Screens: bills, reconcile, wallet, audit | todo | Sun 18 | Tue 13 | fiona-19 screen kit |
| D7 | Shenzhen persona + tenant switch (Tier 2) | todo | Mon 19 | Tue 13 | Only on green Tier 1 |
| D9 | POS reconciliation (Tier 2) | todo | Mon 19 | Tue 13 | |
| D10-D12 | Invoices, tax simulators, connectors (Tier 3) | todo | - | Tue 13 | |
