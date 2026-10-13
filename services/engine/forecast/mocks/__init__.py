"""Fixture-backed mocks for Yahya-lane endpoints (served when FIONA_MODE=mock).

Each builder constructs the response with the real Pydantic models, so a mock can never
drift from its schema; `python -m engine.forecast.mocks` rewrites the JSON files and a test
checks that the committed files equal the builders' output. All data is SYNTHETIC and
describes the invented Karachi apparel tenant from data/fixtures/FORMATS.md.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

MOCK_TENANT = "ten_karachi_apparel"
CURRENCY = "PKR"
AS_OF = date(2026, 10, 22)
GENERATED_AT = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)
CASH_BUFFER_MINOR = 200_000_000  # tenant.json -> policies.cash_buffer_minor


def envelope() -> dict:
    return {"mode": "mock", "tenant_id": MOCK_TENANT, "generated_at": GENERATED_AT}


def dump(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def write_all(builders: dict[str, BaseModel], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in builders.items():
        path = folder / f"{name}.json"
        path.write_text(dump(model), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def load(folder: Path, name: str, model: type[BaseModel]) -> BaseModel:
    return model.model_validate_json((folder / f"{name}.json").read_text(encoding="utf-8"))
