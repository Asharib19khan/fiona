# services/agents

**Owner:** Asharib (fiona-19). Package `fiona_agents`, port 8100, Fly app `fiona-agents`.

The Claude runtime: the LLM wrapper (the only module that imports `anthropic`), the tool bridge generated from the contract with per-agent allow-lists, bill extraction, the Controller, Treasurer, CFO Strategist and Growth Analyst, the briefing, the council and the Guide.

- Agents propose; they never move money. No tool reaches `/v1/wallet/pay` or `/v1/proposals/{id}/decision` (R7).
- Agents reach the engine only over HTTP. They never import `engine` or `fiona_guardian` (`scripts/check-boundaries.py`).

```sh
uv run uvicorn fiona_agents.main:app --reload --port 8100
uv run pytest
```
