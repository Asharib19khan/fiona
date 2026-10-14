"""Fiona shared contracts (v1).

    from fiona_contracts import Money, Figure, Finding, Proposal, Verdict, Mandate, LedgerEvent
    from fiona_contracts import validate, canonical_json, verdict_hash

`models` is generated from packages/contracts/schemas (run `pnpm gen`); never edit it by hand.
The Pydantic models check shapes. `validate(name, data)` runs the full JSON Schema, including the
cross-field rules (e.g. a Figure has money or value, never both).
"""

from fiona_contracts.hashing import canonical_json, verdict_hash
from fiona_contracts.models import *  # noqa: F403  (the generated __all__ lists every model)
from fiona_contracts.models import __all__ as _models
from fiona_contracts.validate import ContractError, definitions, validate

API_VERSION = "v1"

__all__ = [
    "API_VERSION",
    "ContractError",
    "canonical_json",
    "definitions",
    "validate",
    "verdict_hash",
    *_models,
]
