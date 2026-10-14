"""Write the engine's OpenAPI document (FastAPI) to a file, deterministically.

Run from services/ with the engine's environment (packages/contracts/tools/gen.mjs does this):
    uv run --project engine python ../packages/contracts/tools/dump_openapi.py <repo-relative output>
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("FIONA_MODE", "mock")
SERVICES = Path(__file__).resolve().parents[3] / "services"
sys.path.insert(0, str(SERVICES))

from engine.app.main import create_app  # noqa: E402

out = SERVICES.parent / sys.argv[1]
spec = create_app().openapi()
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(f"  wrote {sys.argv[1]} ({len(spec.get('paths', {}))} paths)")
