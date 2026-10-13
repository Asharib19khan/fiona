# Yahya lane status (fiona-79)

Queue per docs/orchestrator/PLAN.md §4 (deadline Tue 20 Oct, 20:59 PKT).

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| Y5-core | Launch Lab core: unit economics, demand profile, inventory/cash simulation, Monte Carlo, TVM, policy loader | done | (pulled forward) | Tue 13 | 15773ee. Reorder planner fixed in Y0 commit (orders sized from arrival; MOQ rounding only when margin beats write-down) |
| Y0 | Schemas + fixture-backed mocks for every Yahya endpoint (cash, findings, inventory, launch-lab, debt-equity, dividend, payment-timing, financing) | done | Wed 14 (G1) | Tue 13 | 8 mocks in `forecast/mocks/data/`, rebuilt by `python -m engine.forecast.mocks`; drift, no-float and API tests; 165 engine tests pass |
| Y1 | 13-week cash forecast, first week below `tenant.policies.cash_buffer_minor`, alert findings | todo | Fri 16 (G2) | Tue 13 | |
| Y10 | Financing-option matcher over `rulebook/financing.yaml`, DSCR from `engine.analysis.coverage` | todo | Fri 16 (G2) | Tue 13 | Schema agreed with fiona-fa |
| Y4 | Debt vs equity (Tier 1); dividend vs reinvest (Tier 2) | todo | Sat 17 | Tue 13 | |
| Y6 | Findings feed ranked by money at stake | todo | Sat 17 | Tue 13 | Ranking + dedupe done (`forecast/feed/rank.py`) |
| Y8 | Payment-timing optimiser | todo | Sun 18 | Tue 13 | |
| W-Y | Screens: forecast, financing | todo | Sun 18 | Tue 13 | |
| Y3 | Inventory analytics + screen | todo | Mon 19 (Tier 2) | Tue 13 | |
| Y5 | Launch Lab API live (resolver from ledger + market data) + screen | todo | Mon 19 (Tier 2) | Tue 13 | Analysis service done (`launch_lab/service.py`); resolver remaining |
| Y7 | Evaluation: forecast backtest vs naive baseline (synthetic + UCI Online Retail II) | todo | Mon 19 | Tue 13 | |
| T3 | Tier 3: other three decisions, Chronos-2, MCP server (Y9) | todo | Shenzhen final | Tue 13 | |
