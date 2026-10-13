---
description: Start a Fiona task - read status and plan, check dependencies, then plan the work
argument-hint: <TaskID, e.g. A3 or D4>
---
Start task $ARGUMENTS.

1. Read `CLAUDE.md`, `docs/orchestrator/PLAN.md` (your lane's queue and §3–§5), your `docs/status/<lane>.md` and the recent entries in `docs/decision-log.md`.
2. Find the task's "done when" line and its dependencies. If a dependency isn't ready, build against its mock or fixture; don't wait.
3. Plan briefly: the files you will create or change (only your lane's folders), the tests, and the exact command that proves "done when".
4. Mark the task `doing` in your status file, then build. Commit trunk-based, scoped to your own paths: `git add <paths>`, then `git commit -m "$ARGUMENTS: …" -- <paths>`.
