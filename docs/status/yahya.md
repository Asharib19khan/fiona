# Yahya lane status (fiona-79)

> **HANDOFF (updated Fri 16 Oct; lanes run one at a time)**
> 1. Done: Y5-core, Y0 (all 8 mocks), Y1 cash forecast (dd0eea6). Plus a shared `tvm.irr` fix: it now searches in log space so 120-month schedules don't underflow.
> 2. Y10 progress: `POST /v1/financing/match` now uses fixture-backed business figures and the matcher, with the static mock retained when the mock tenant has no ledger fixture. Fixture-date and currency mismatches return contract errors.
> 3. Also fixed Y10: invoice-discounting DSCR service counts interest only over the first 12 months while preserving bullet cash flows for EAC; dotted input paths now render as readable labels.
> 4. Y10 test coverage is complete for fixture ranking, hard amount eligibility, readable missing data, nullable pricing, reduced-size DSCR, invoice-discount service, EAC, and API snapshot/currency guards. The focused engine regression set passed: 40 tests; Ruff check and format passed.
> 5. Remaining dependency: EBITDA is still a labelled STUB (operating cash flow proxy); replace it with engine.analysis EBITDA when Abdullah exposes the approved figure. Y1 was re-run against the current generator ledger and passed.

Queue per docs/orchestrator/PLAN.md §4 (deadline Tue 20 Oct, 20:59 PKT).

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| Y5-core | Launch Lab core: unit economics, demand profile, inventory/cash simulation, Monte Carlo, TVM, policy loader | done | (pulled forward) | Tue 13 | 15773ee. Reorder planner fixed in Y0 commit (orders sized from arrival; MOQ rounding only when margin beats write-down) |
| Y0 | Schemas + fixture-backed mocks for every Yahya endpoint (cash, findings, inventory, launch-lab, debt-equity, dividend, payment-timing, financing) | done | Wed 14 (G1) | Tue 13 | 8 mocks in `forecast/mocks/data/`, rebuilt by `python -m engine.forecast.mocks`; drift, no-float and API tests; 165 engine tests pass |
| Y1 | 13-week cash forecast, first week below `tenant.policies.cash_buffer_minor`, alert findings | done (v0 data) | Fri 16 (G2) | Wed 14 | `forecast/cash/engine.py` on seed-42 ledger: 8 tests (planted dip -> high finding in the right week, every open bill/invoice scheduled once, loan stops at last instalment, seasonality after a year, determinism, runs on generator files). Served by GET /v1/forecast/cash and the findings feed. Re-test against D2's week-7 dip on Thu |
| Y10 | Financing-option matcher over `rulebook/financing.yaml`, DSCR from `engine.analysis.coverage` | done, pending approved EBITDA | Fri 16 (G2) | Fri 16 | Fixture-backed API, invoice DSCR treatment, readable missing-input labels and matcher/API regression coverage complete. It uses the explicitly labelled operating-cash-flow proxy until the analysis lane publishes approved EBITDA. |
| Y4 | Debt vs equity (Tier 1); dividend vs reinvest (Tier 2) | done | Sat 17 | Fri 16 | Both Debt-versus-equity and Dividend-versus-reinvest complete with cash forecast buffer checks, opportunity costs, and full regression tests. |
| Y6 | Findings feed ranked by money at stake | todo | Sat 17 | Tue 13 | Ranking + dedupe done (`forecast/feed/rank.py`) |
| Y8 | Payment-timing optimiser | todo | Sun 18 | Tue 13 | |
| W-Y | Screens: forecast, financing | todo | Sun 18 | Tue 13 | |
| Y3 | Inventory analytics + screen | done | Mon 19 (Tier 2) | Tue 13 | Inventory analytics engine, ABC-XYZ matrix, dead-stock detection and screen live. |
| Y5 | Launch Lab API live (resolver from ledger + market data) + screen | done | Mon 19 (Tier 2) | Sat 17 | Live ledger & inventory resolver (`forecast/launch_lab/resolver.py`) with demand profile and full simulation wired to POST /v1/launch-lab/simulate. |
| Y7 | Evaluation: forecast backtest vs naive baseline (synthetic + UCI Online Retail II) | synthetic evaluation done | Mon 19 | Fri 16 | Synthetic 13-week held-out backtest and seasonal-naive baseline are implemented and documented; UCI comparison awaits a licensed dataset. |
| T3 | Tier 3: other three decisions, Chronos-2, MCP server (Y9) | todo | Shenzhen final | Tue 13 | |
