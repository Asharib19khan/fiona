# Yahya lane status (fiona-79)

> **HANDOFF (paused Wed 14 Oct by orchestrator; lanes run one at a time)**
> 1. Done: Y5-core, Y0 (all 8 mocks), Y1 cash forecast (dd0eea6). Plus a shared `tvm.irr` fix: it now searches in log space so 120-month schedules don't underflow.
> 2. Half-done: Y10 financing matcher. `financing/{catalogue,conditions,business,matcher}.py` run end to end on rulebook/financing.yaml and the seed-42 ledger, but have no tests and are not wired to the API (`financing/api.py` still serves the mock).
> 3. Exact next step: write `financing/tests/test_matcher.py` (purpose/amount/hard-rule ineligibility, needs_information on unknown inputs, cost_unknown for null rows, DSCR fail -> possible_at_smaller_size with max_amount, ranking order, EAC hand checks). Then wire `POST /v1/financing/match` to `business_figures(load_fixture_snapshot(tenant))` + `match_financing` (mock fallback as in forecast/api.py `_cash`).
> 4. Fix while testing: (a) invoice discounting counts repeated 3-month principal as 12-month debt service (DSCR too low); count interest only, as for revolving. (b) Tidy "need X" labels (dotted input paths -> plain words). (c) EBITDA is a labelled STUB (operating cash flow proxy, about Rs 68.7M a year, so DSCR reads ~12x); swap in engine.analysis EBITDA when Abdullah exposes it.
> 5. Open questions: none blocking. Then Y4 debt/equity, Y6 feed, Y8; D2 re-test of Y1 when Daniyal's week-7 dip lands.

Queue per docs/orchestrator/PLAN.md §4 (deadline Tue 20 Oct, 20:59 PKT).

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| Y5-core | Launch Lab core: unit economics, demand profile, inventory/cash simulation, Monte Carlo, TVM, policy loader | done | (pulled forward) | Tue 13 | 15773ee. Reorder planner fixed in Y0 commit (orders sized from arrival; MOQ rounding only when margin beats write-down) |
| Y0 | Schemas + fixture-backed mocks for every Yahya endpoint (cash, findings, inventory, launch-lab, debt-equity, dividend, payment-timing, financing) | done | Wed 14 (G1) | Tue 13 | 8 mocks in `forecast/mocks/data/`, rebuilt by `python -m engine.forecast.mocks`; drift, no-float and API tests; 165 engine tests pass |
| Y1 | 13-week cash forecast, first week below `tenant.policies.cash_buffer_minor`, alert findings | done (v0 data) | Fri 16 (G2) | Wed 14 | `forecast/cash/engine.py` on seed-42 ledger: 8 tests (planted dip -> high finding in the right week, every open bill/invoice scheduled once, loan stops at last instalment, seasonality after a year, determinism, runs on generator files). Served by GET /v1/forecast/cash and the findings feed. Re-test against D2's week-7 dip on Thu |
| Y10 | Financing-option matcher over `rulebook/financing.yaml`, DSCR from `engine.analysis.coverage` | doing (paused) | Fri 16 (G2) | Wed 14 | Engine runs end to end; tests + API wiring next (see HANDOFF) |
| Y4 | Debt vs equity (Tier 1); dividend vs reinvest (Tier 2) | todo | Sat 17 | Tue 13 | |
| Y6 | Findings feed ranked by money at stake | todo | Sat 17 | Tue 13 | Ranking + dedupe done (`forecast/feed/rank.py`) |
| Y8 | Payment-timing optimiser | todo | Sun 18 | Tue 13 | |
| W-Y | Screens: forecast, financing | todo | Sun 18 | Tue 13 | |
| Y3 | Inventory analytics + screen | todo | Mon 19 (Tier 2) | Tue 13 | |
| Y5 | Launch Lab API live (resolver from ledger + market data) + screen | todo | Mon 19 (Tier 2) | Tue 13 | Analysis service done (`launch_lab/service.py`); resolver remaining |
| Y7 | Evaluation: forecast backtest vs naive baseline (synthetic + UCI Online Retail II) | todo | Mon 19 | Tue 13 | |
| T3 | Tier 3: other three decisions, Chronos-2, MCP server (Y9) | todo | Shenzhen final | Tue 13 | |
