> **HANDOFF (paused after D3, Wed 14 Oct, fiona-b0)**
> 1. Done: D1, D2a, D2 (4551520), D5 review (955692f), D6 review (b2097b3), D3 (0214d94), /v1 import, ledger, wallet and audit endpoints (3875d65, 3e1645a), OpenAPI regenerated (f302342).
> 2. Wallet completion: each simulated supplier payment now creates the balanced Dr 2000 / Cr 1000 journal in the same tenant transaction; wallet regression coverage passes.
> 3. D4 progress: deterministic exact, rule and one-to-many proposals, proposal persistence, review-decision preservation, `POST /v1/reconcile/run`, `GET /v1/reconcile/matches`, and ranked unmatched-bank-line findings are implemented and tested. `POST /v1/bills/check` runs read-only G-05 duplicate-document detection on imported bills.
> 4. Files: services/engine/ledger/{importers,posting,demo,api}.py; new module services/engine/ledger/reconcile.py (planned).
> 5. Open: posting simplifications (cost of sales at item cost, no depreciation or monthly input/output tax offset; frameworks engine B5 owns those). customer_receipt events from D4 must not post (the bank line already posts Dr 1000 / Cr 1100). Fixtures: regenerate at most once more (orchestrator ruling).

# Daniyal lane status (fiona-b0)

Dates follow docs/orchestrator/PLAN.md §4 (re-plan for the 20 Oct deadline).

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| D2a-F | Fixture file formats (`data/fixtures/FORMATS.md`) | done | Wed 14 | Tue 13 | Orchestrator rulings applied; awaiting fiona-19 objections until G1 |
| D1 | Ledger schema: migrations, RLS, auth shim, seed | done | Wed 14 | Tue 13 | 15 tables, forced RLS, 47 tests; `python -m engine.ledger.db reset` + `seed` |
| D2a | Generator v0: Karachi, 2 months, seed 42 | done | Wed 14 | Tue 13 | `data/fixtures/ten_karachi_apparel/`; 14 tests (reproducible, coherent, demo threads) |
| D2 | Generator v1 (Karachi): 24 months from 1 Jul 2024, all B3 plants, answer key, finance schedules, PDFs | done | Thu 15 | Wed 14 | 23 tests. FY25 growth, FY26 shake-out (CFO -3.5% of revenue), week-7 dip 1.66M < 2M buffer (weeks 1-6 >= 8.2M), 91% of bills within cap, net margin ~9%; holdout in data/fixtures/holdout/ |
| D3 | Importers + postings + debits=credits property test | done | Fri 16 | Wed 14 | `python -m engine.ledger.db demo-data` loads 74,931 events, 298,622 journal lines in ~85 s; importer events equal the generator's; idempotent; row errors; cash ties to the bank; Hypothesis property |
| D4 | Reconciliation passes 1-3, duplicate detector, findings | done, except pass-4 model intake | Fri 16 | Fri 16 | Deterministic proposals remain reviewable; reruns preserve confirmed/rejected matches. G-05 duplicate checking is served by `POST /v1/bills/check`; three-way, tax and bank-detail checks still need their approved intake/context mapping. |
| D5 | Guardian deterministic checks G-01..G-13 + mandate enforcement | done (review) | Sat 17 | Wed 14 | Built by Antigravity (75f5a8d), reviewed and fixed in 955692f: G-09 resolver (removed a '999' test hack), no threshold literals, G-03 phone-by-user, G-08 horizon/latest-date/statutory, G-13 fail-closed. Tests generated from scenarios.yaml: 36 pass, S-12 skipped (model) |
| D6 | Wallet sandbox, hash-chained audit, operation-log export | done | Sun 18 | Fri 16 | Wallet payments journal-post Dr 2000 / Cr 1000 in their transaction; `/v1/wallet/pay`, `/v1/audit`, `/v1/import/{bank,pos,bills}`, and `/v1/ledger/events` are served. |
| W | Screens: bills, reconcile, wallet, audit | todo | Sun 18 | Tue 13 | fiona-19 screen kit |
| D7 | Shenzhen persona + tenant switch (Tier 2) | done | Mon 19 | Sat 17 | `rulebook/country_packs/CN.yaml` (USCC regex, PBOC LPR, CAS framework) + /v1/whoami tenant resolution + G-05/G-11 fapiao duplicate and USCC format test suite. |
| D9 | POS reconciliation (Tier 2) | done | Mon 19 | Sat 17 | `services/engine/ledger/pos_reconcile.py` (cash drawer variances, card/digital fee matching, unbanked cash) served at POST /v1/reconcile/pos. |
| D10-D12 | Invoices, tax simulators, connectors (Tier 3) | todo | - | Tue 13 | |
