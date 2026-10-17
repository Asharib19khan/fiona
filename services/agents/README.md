# services/agents

**Owner:** Asharib (fiona-19). Package `fiona_agents`, port 8100, Fly app `fiona-agents`.

This service currently has a credential-free replay path and a first live bill-extraction vertical slice. `POST /v1/agents/extract-bill` accepts one bounded PDF/JPEG/PNG/WebP, requires a 60-second BFF JWT (`aud=fiona-agents`, role `owner` or `finance`), requests schema-constrained output from Anthropic, normalizes decimals using BFF-supplied tenant currency metadata, checks arithmetic/currency consistency, and returns the generated `BillExtraction` contract. Documents are processed in memory and are not stored by this service.

The extraction provider is opt-in: `FIONA_LLM_PROVIDER=replay` remains the default; `anthropic_api` enables only this extraction endpoint. It requires `ANTHROPIC_API_KEY`. Tests use a mocked HTTP transport and never make a provider call. Do not enable a live call until the account spend cap and runtime budget guard are in place. The Controller, Treasurer, general agent runtime, and replay/evaluation pipeline are not implemented yet.

- Agents propose; they never move money. No tool reaches `/v1/wallet/pay` or `/v1/proposals/{id}/decision` (R7).
- Agents reach the engine only over HTTP. They never import `engine` or `fiona_guardian` (`scripts/check-boundaries.py`).
- Extraction rejects unsupported/mismatched file bytes, oversized documents (12 MB/50 pages), invalid citations, malformed provider output, currency conflicts and amount precision beyond the tenant currency. Model-supplied source spans are never marked text-verified by the server.

```sh
uv run uvicorn fiona_agents.main:app --reload --port 8100
uv run pytest
```
