"""Fiona synthetic data generator (Daniyal lane). Stdlib only; deterministic by seed.

All output is SYNTHETIC. File formats: data/fixtures/FORMATS.md.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PERSONAS = Path(__file__).parent / "personas"
RULEBOOK_MANDATES = Path(__file__).resolve().parents[2] / "rulebook" / "mandates.yaml"


def load_persona(name: str) -> dict:
    path = PERSONAS / f"{name}.toml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in PERSONAS.glob("*.toml")))
        raise SystemExit(f"Unknown persona {name!r}. Available: {available}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_mandates(tenant_id: str, path: Path = RULEBOOK_MANDATES) -> tuple[list[dict], str]:
    """The tenant's mandates from Abdullah's rulebook (the source of truth for caps and scopes).

    Returns the mandate list and a source label. PyYAML is the generator's only non-stdlib
    import, and only this step needs it.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment hint
        raise SystemExit(
            "Reading rulebook/mandates.yaml needs PyYAML: uv run --with pyyaml python -m data.generator ..."
        ) from exc
    with path.open(encoding="utf-8") as handle:
        rulebook = yaml.safe_load(handle)
    persona = rulebook["persona_mandates"][tenant_id]
    mandates = []
    for m in persona["mandates"]:
        mandate = {"tenant_id": tenant_id, **m}
        # Contract Mandate requires these; the rulebook leaves them implicit for defaults.
        mandate.setdefault("status", "active")
        mandate.setdefault("created_at", f"{m['effective_from']}T00:00:00Z")
        mandates.append(mandate)
    return mandates, f"rulebook/mandates.yaml v{rulebook['mandates_version']}"
