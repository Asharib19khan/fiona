# services/engine

**Skeleton owner:** Asharib (fiona-19): `app/`, `__init__.py`, `pyproject.toml`, `package.json`, `Dockerfile`, `fly.toml`.
**Modules** are owned by their lanes (`docs/orchestrator/PLAN.md` §1): `ledger/`, `guardian_checks/`, `connectors/` (Daniyal) · `forecast/`, `decisions/`, `mcp/` (Yahya) · `analysis/`, `frameworks/` (Abdullah).

One FastAPI app, Python 3.12, managed with uv (D-007, D-010).

## Module convention
- The package is `engine`: import as `engine.<module>` (for example `engine.guardian_checks`). Every module folder has an `__init__.py`.
- To serve endpoints, put `router = APIRouter()` with full `/v1/...` paths in `<module>/api.py`. `app/main.py` discovers and mounts it, so never edit main.py. A broken `api.py` fails startup and CI loudly.
- Contract paths nobody serves yet answer `501 not_implemented` with the owning module. Unknown paths answer `404`. Both use the contract error envelope with a `request_id`.
- Raise `engine.app.errors.ApiError(status, code, message, details)` for client-visible errors.
- `FIONA_MODE=mock|live` (default `mock`): serve fixtures in mock mode (R2). Read it with `engine.app.main.fiona_mode()`.
- `engine.guardian_checks` must stay a standalone library: the Guardian imports it, and it may not import other engine modules (`scripts/check-boundaries.py`).
- Add dependencies with `uv add <pkg>` from this folder, and commit `pyproject.toml` with `uv.lock`.

## Commands (from services/engine)
```sh
uv run uvicorn engine.app.main:app --app-dir .. --reload --port 8000   # or: pnpm dev at the root
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
From the root, `pnpm db:reset` and `pnpm demo-data` run `python -m engine.ledger.db …` through `scripts/engine-py.mjs`.

## Deploy
Fly.io app `fiona-engine`. Build context is the repo root: `fly deploy --config services/engine/fly.toml --dockerfile services/engine/Dockerfile .`
