---
description: Finish a Fiona task - run checks, commit own paths, update status, report to fiona-b7
argument-hint: <TaskID>
---
Finish task $ARGUMENTS.

1. Run the checks for what you touched: `pnpm lint`, `pnpm typecheck`, `pnpm test` (or `uv run ruff check . && uv run ruff format --check . && uv run pytest` in the service). Run the task's done-when command. Fix failures; never silence a test.
2. `pnpm check:boundaries` and `node scripts/check-env-coverage.mjs` must pass. If you read a new env var, add it to `scripts/lib/env-spec.mjs` and run `pnpm gen:env`.
3. Commit only your own paths (`git add <paths>`, then `git commit -m "$ARGUMENTS: …" -- <paths>`).
4. Update `docs/status/<lane>.md` (status `done`, date, one-line note on how you verified it).
5. Message fiona-b7: task ID, status, how you verified it (command + key output line), what's next, blockers.
