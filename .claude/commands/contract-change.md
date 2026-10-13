---
description: Checklist before changing packages/contracts (frozen at G1, Wed 14 Oct)
argument-hint: <short description of the change>
---
Proposed contract change: $ARGUMENTS.

1. **Message fiona-b7 first**, before editing anything. Say what changes and who consumes it.
2. Classify it. **Additive** (a new optional field, a new endpoint, a new enum value that consumers can ignore) needs acks from fiona-19 and fiona-b7. **Breaking** (renaming or removing a field, changing a type, making something required) needs Asharib **and** Daniyal, plus fiona-b7.
3. Add a row to `docs/decision-log.md` (ID, date, decision, why, owner, signatories).
4. Edit the JSON Schema, then `pnpm gen`, and commit the generated TypeScript and Python in the same commit. CI fails if generated code is stale.
5. Validate the examples and scenarios, and update any fixture or mock that uses the changed shape.
