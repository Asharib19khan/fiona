# Yahya lane status (fiona-79)

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| Y5-core | Launch Lab core: unit economics, demand profile, month-by-month inventory/cash simulation, Monte Carlo sampling, TVM (NPV, IRR, payback), policy loader | done | (pulled forward) | Tue 13 | 65 pytest + Hypothesis tests pass (`uv run --no-project --with pytest --with hypothesis --with numpy --with pydantic --with pyyaml python -m pytest --import-mode=importlib services/engine/forecast services/engine/decisions`). Not committed yet (no git) |
| Y0 | Schemas + fixture-backed mocks for every Yahya endpoint | doing | Wed 14 | Tue 13 | Shapes follow `data/fixtures/FORMATS.md` (money `_minor`, rates `_bp`); waiting on A2 for the shared Figure/Money/Finding models |
| Y1 | 13-week cash forecast, first week below `tenant.policies.cash_buffer_minor` | todo | Sun 18 | Tue 13 | |
| Y3 | Inventory: ABC-XYZ, fast/slow/dead, reorder points + draft POs, margin, GMROI, variants, bundles | todo | Thu 22 | Tue 13 | |
| Y4 | Five decisions: debt/equity, dividend/reinvest, asset investment (NPV/IRR/payback, lease vs buy), liability pay-down, innovation budget + pilot size | todo | Fri 23 | Tue 13 | TVM primitives already in `decisions/tvm.py` |
| Y8 | Payment-timing optimiser (early-payment discounts vs cost of money) | todo | Fri 23 | Tue 13 | |
| Y6 | Findings feed ranked by money at stake | todo | Fri 23 | Tue 13 | |
| Y5 | Launch Lab complete: demand signals, seasonal calendars, analogue curves + Chronos-2, Monte Carlo, break-even, payback, NPV, cannibalisation, affordability via Y1, decision rules, levers, findings | todo | Tue 27 | Tue 13 | Core done (Y5-core) |
| Y9 | MCP server over the engine (read tools + proposal submission) | todo | Wed 28 | Tue 13 | |
| Y7 | Evaluation: cash-forecast backtest vs naive baseline, M5/Favorita, Launch Lab range coverage | todo | Wed 28 | Tue 13 | |
| W-Y | Screens: forecast, inventory, decisions, launch-lab | todo | from W3 | Tue 13 | Built with fiona-19's screen kit |
