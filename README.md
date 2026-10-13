# Fiona

A finance team made of AI agents that works for a small or medium business. The agents read one canonical ledger, prepare work and, within limits the owner sets, act. A separate agent, the Guardian, checks every action before it happens. The owner looks in through **the Window**, a browser console at `apps/web`.

FinTechathon 2026 · International AI Track · Direction E: "AI as a Financial Participant".

## Run it

Requirements: Node 24, Python 3.12 and [uv](https://docs.astral.sh/uv/). pnpm comes from Corepack.

```sh
corepack enable          # once per machine; provides the pinned pnpm
pnpm install             # JavaScript workspace; also installs the git hooks
pnpm doctor              # checks tools and your .env.local (prints no values)
pnpm dev                 # web :3000, engine :8000, agents :8100, guardian :8200
```

With no `.env.local`, everything starts in **mock mode** and needs no keys. Each Python service creates its own `.venv` with `uv` the first time it runs.

**Local database.** Start the shared local Postgres once, in its own terminal, from `services/`: `uv run --project engine python -m engine.ledger.db start`. Never let a test run you might Ctrl-C be the process that starts it, because a console Ctrl-C kills the server. Tests create and drop their own throwaway databases on that server; `pnpm db:reset` resets the shared `fiona_dev` database.

| Command | What it does |
|---|---|
| `pnpm dev` | Starts all four services (Turborepo) |
| `pnpm lint` / `pnpm typecheck` / `pnpm test` / `pnpm build` | Workspace-wide checks |
| `pnpm doctor` | Tool versions and env check |
| `pnpm db:reset` / `pnpm demo-data` | Local database and seeded demo data (Lane D) |
| `pnpm verify:a1` | Fresh clone to a temp folder; proves `pnpm dev` comes up with no secrets |

## Layout

```
apps/web                Next.js console (the Window)
packages/contracts      shared schemas and the generated client
packages/ui             shared components and design tokens
services/engine         FastAPI app: ledger, guardian_checks, forecast, decisions, …
services/agents         Claude runtime, prompts, tool bridge, briefing
services/guardian       adversarial review and verdict combiner
rulebook/               YAML rules, mandates, scenarios, rulepacks
data/                   synthetic data generator and fixtures
docs/                   blueprint, plan, decision log, lane notes
```

Rules for contributors (and Claude sessions) are in [CLAUDE.md](CLAUDE.md).
