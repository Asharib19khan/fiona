---
description: Check a gate (G1..G5) - list each gate test, the evidence, and what is not yet demonstrable
argument-hint: <G1|G2|G3|G4|G5>
---
Gate check for $ARGUMENTS.

1. Read the gate's test in `docs/orchestrator/PLAN.md` (dates and scope there override the Blueprint).
2. For each item: run what can be run (`pnpm test`, `pnpm verify:a1`, service `/healthz`, the relevant demo step) and record the command and its key output line.
3. Report a table: item, evidence, PASS / FAIL / NOT DEMONSTRABLE YET. A gate is green only if every item is PASS when shown live. Never mark green on a plan or a promise.
