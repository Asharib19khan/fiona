# Lane A: requests to other lanes

| Date | To | Request | Status |
|---|---|---|---|
| 2026-10-13 | Yahya | Run `uv run ruff format forecast decisions` (4 files failed the CI format check). | sent |
| 2026-10-13 | Daniyal | Run `uv run ruff format ledger` (4 files). | done (e6d6758) |
| 2026-10-13 | Yahya | R3: `forecast/money.py` keeps amounts as floats internally; floats must never cross a module boundary or reach a response. | sent via fiona-b7 |
| 2026-10-13 | Yahya | Final Figure / Finding / FigureInput / Threshold field list for A2 by Wed 14 10:00 PKT. | promised |
| 2026-10-13 | Daniyal | Confirm `engine.ledger.db` subcommands (`reset`, `demo-data`) match `pnpm db:reset` / `pnpm demo-data`. | confirmed |
| 2026-10-13 | Abdullah | G-04 needs `bill.created_by` and `decision.user_id`; A2 will carry both on Proposal and decision records. | to do in A2 |
