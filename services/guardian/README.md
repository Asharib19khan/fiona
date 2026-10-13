# services/guardian

**Owner:** Asharib (fiona-19). Package `fiona_guardian`, port 8200, Fly app `fiona-guardian`.

The independent checker. Given a review bundle (a Proposal plus the raw rows it relies on), it runs the deterministic checks, adds an adversarial review on Opus, and combines them into the strictest outcome: `block` > `escalate` > `approve_with_conditions` > `approve`.

- **Independent (R8):** no shared code or prompts with `services/agents`, its own Anthropic key (`GUARDIAN_ANTHROPIC_API_KEY`), its own deploy. The only engine import allowed is `engine.guardian_checks`, as a library (`scripts/check-boundaries.py`).
- **Fail closed (R9):** any unavailable or invalid check gives at least `escalate`. A language model can only tighten a verdict, never loosen one.
- Never reads the database and never calls the wallet.

```sh
uv run uvicorn fiona_guardian.main:app --reload --port 8200
uv run pytest
```
