"""Recompute verdict_hash in every example scenario (run after editing a scenario's verdict).

uv run --project python python tools/seal_verdicts.py      (from packages/contracts)
"""

from __future__ import annotations

import json
from pathlib import Path

from fiona_contracts import verdict_hash

SCENARIOS = Path(__file__).resolve().parents[1] / "examples" / "scenarios"

for path in sorted(SCENARIOS.glob("*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    verdict = data["verdict"]
    new = verdict_hash(verdict)
    if verdict.get("verdict_hash") != new:
        verdict["verdict_hash"] = new
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"sealed {path.name}: {new}")
    else:
        print(f"ok     {path.name}")
