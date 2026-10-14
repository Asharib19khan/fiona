"""Full JSON Schema validation against the bundled contracts (generated schema.json)."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class ContractError(ValueError):
    """Data does not match a contract. `errors` lists (json_path, message), never the data itself."""

    def __init__(self, name: str, errors: list[tuple[str, str]]) -> None:
        self.name = name
        self.errors = errors
        summary = "; ".join(f"{p}: {m}" for p, m in errors[:5])
        super().__init__(f"{name} is invalid ({len(errors)} error(s)): {summary}")


@cache
def _bundle() -> dict[str, Any]:
    return json.loads(files("fiona_contracts").joinpath("schema.json").read_text(encoding="utf-8"))


def definitions() -> list[str]:
    """Names of every contract definition."""
    return sorted(_bundle()["$defs"])


@cache
def _validator(name: str) -> Draft202012Validator:
    bundle = _bundle()
    if name not in bundle["$defs"]:
        raise KeyError(f"No contract named {name!r}")
    schema = {"$schema": bundle["$schema"], "$defs": bundle["$defs"], "$ref": f"#/$defs/{name}"}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(name: str, data: Any) -> None:
    """Raise ContractError if `data` does not satisfy contract `name` (e.g. "Proposal")."""
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        raise ContractError(name, [(e.json_path, e.message) for e in errors])
