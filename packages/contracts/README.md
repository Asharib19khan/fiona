# packages/contracts: Fiona contracts v1

**Owners:** Asharib (fiona-19) and Daniyal (fiona-b0). **Frozen at G1 (Wed 14 Oct 2026, 23:59 PKT):** after that, additive changes only. Message the orchestrator first; see `.claude/commands/contract-change.md`.

The only surface shared across boxes (R1). One source, generated into both languages:

```
schemas/*.yaml  ── pnpm gen ──▶ generated/fiona.schema.json         JSON Schema 2020-12, one $defs namespace
                              ▶ generated/ts/types.ts               TypeScript types
                              ▶ python/fiona_contracts/models.py    Pydantic v2 models
services/engine (FastAPI) ────▶ openapi/engine.v1.json ─▶ generated/ts/engine-api.ts   typed engine client
```

Never edit anything under `generated/`, `openapi/` or `python/fiona_contracts/models.py` by hand. Edit `schemas/*.yaml`, run `pnpm gen` (or `pnpm --filter @fiona/contracts gen`), and commit the output with the change. CI fails if generated code is stale.

## What is in it

| File | Objects |
|---|---|
| `schemas/common.yaml` | `Money`, `Currency`, `Timestamp` (UTC, `Z`), `Date`, prefixed IDs (`ProposalId`, `VerdictId`, `PartyId`, `Sku` …), `RuleId` (G-01…G-15), `AgentName`, `Actor`, `Evidence`, `Action`, `Period`, `Meta`, `ErrorEnvelope` |
| `schemas/figures.yaml` | `Figure`, `FigureInput`, `Threshold`, `Unit`, `Origin` (every number is a Figure; ratios in basis points) |
| `schemas/findings.yaml` | `Finding`, `Severity`, `FindingSource` |
| `schemas/proposals.yaml` | `ProposalDraft` (what an agent submits) and `Proposal` (stored), each a union of six types: `payment`, `bill_approval`, `journal_adjustment`, `send_document`, `purchase_order`, `reconciliation_match`; `DecisionRequest`, `Decision` |
| `schemas/verdicts.yaml` | `Verdict`, `Check` (with per-check `outcome`), `Condition` (`pay_on`, `max_amount_minor`, `before_time`), `Outcome`, `CheckName` |
| `schemas/mandates.yaml` | `Mandate` (autonomy per action type, caps, categories, payment windows), `AutonomyLevel`, `ActionType`, `TenantPolicies` (`cash_buffer_minor`) |
| `schemas/ledger.yaml` | `LedgerEvent`: a union of the nine event types, exactly as in `data/fixtures` (all 7,116 seed events validate) |

`examples/` holds a valid example per object, and `examples/scenarios/` holds the demo stories (planted bill → block, clean payment → approve, over cap → escalate, early payment → pay-later condition), each a Proposal with its Verdict and a real `verdict_hash`.

## Use it

**Python** (engine, agents, Guardian: already a path dependency of each service):
```python
from fiona_contracts import Money, Figure, Finding, Proposal, ProposalDraft, Verdict, Mandate, LedgerEvent
from fiona_contracts import validate, verdict_hash

Proposal.model_validate(data)        # shape (Pydantic, strict: unknown fields fail)
validate("Proposal", data)           # full schema, including cross-field rules (e.g. Figure money XOR value)
verdict_hash(verdict_dict)           # "sha256:…" over RFC 8785 canonical JSON, minus verdict_hash
```

**TypeScript** (web):
```ts
import { type Proposal, validate, verdictHash, createEngineClient } from "@fiona/contracts";
const engine = createEngineClient({ baseUrl: "/api/fiona" });   // asserts api_version "v1"; errors → FionaApiError
const { data } = await engine.GET("/v1/forecast/cash", { params: { query: { weeks: 13 } } });
```

## Rules the schemas enforce
- Money is integer minor units plus an ISO 4217 code; floats are rejected (and the hash refuses them).
- Timestamps end in `Z` (UTC). They stay strings in both languages, so they round-trip byte-for-byte for hashing.
- Strict objects: an unknown field is an error, so typos fail loudly.
- A draft can't carry `tenant_id`; the server adds it (R15).
- A passing check contributes `approve`; `approve_with_conditions` must carry a machine-checkable condition.
- Endpoint request and response models stay Pydantic in each engine module and reach the web through the engine's OpenAPI (PLAN.md §3.4).

## Tests
`pnpm --filter @fiona/contracts test` (Vitest: examples, scenarios, negative cases, client) and `uv run pytest` in `python/` (the same, plus every fixture ledger event).
