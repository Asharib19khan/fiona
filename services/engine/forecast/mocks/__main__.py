"""Rebuild every Yahya-lane mock fixture: `uv run python -m engine.forecast.mocks` (from services/engine, PYTHONPATH=..)."""

from __future__ import annotations

from engine.forecast.mocks.registry import write_everything

if __name__ == "__main__":
    for path in write_everything():
        print(path)
