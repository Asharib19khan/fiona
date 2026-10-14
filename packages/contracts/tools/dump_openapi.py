"""Write the engine's OpenAPI document (FastAPI) to a file, deterministically.

    python dump_openapi.py <services dir> <output path>

packages/contracts/tools/gen.mjs runs this against a clean export of the committed HEAD, so
uncommitted work in the shared working tree never leaks into the contract (CI does the same).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("FIONA_MODE", "mock")
services, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
sys.path.insert(0, str(services))

from engine.app.main import create_app  # noqa: E402

spec = create_app().openapi()
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    encoding="utf-8",
    newline="\n",  # LF on Windows too, so the file is byte-identical to CI's
)
print(f"  wrote {out.name} ({len(spec.get('paths', {}))} paths) from committed HEAD")
