"""Python import boundaries (R1, R8), checked statically with the standard library (D-009).

    python scripts/check-boundaries.py              # scan the repo; exit 1 on any violation
    python scripts/check-boundaries.py --self-test  # prove every rule fires on a bad import

Rules:
  agents-isolated     services/agents never imports the engine or the Guardian (HTTP only).
  guardian-isolated   services/guardian never imports the agents.
  guardian-engine     services/guardian imports nothing from the engine except engine.guardian_checks.
  engine-isolated     services/engine never imports the agents or the Guardian.
  checks-standalone   engine.guardian_checks imports no other engine module, so the Guardian can
                      use it as a library without pulling in the rest of the engine.

Relative imports are resolved before matching. Dynamic imports (importlib) are not seen;
code review catches those.
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache", ".hypothesis"}


@dataclass(frozen=True)
class Rule:
    name: str
    folder: str  # repo-relative folder the rule applies to
    forbid: tuple[str, ...]  # module prefixes that may not be imported
    allow: tuple[str, ...] = ()  # exceptions inside the forbidden prefixes
    why: str = ""


RULES = (
    Rule(
        "agents-isolated",
        "services/agents",
        ("engine", "fiona_guardian", "guardian", "services"),
        why="Agents reach the engine over HTTP only and never touch the Guardian (R1, R8).",
    ),
    Rule(
        "guardian-isolated",
        "services/guardian",
        ("fiona_agents", "agents", "services"),
        why="The Guardian shares no code with the agents (R8).",
    ),
    Rule(
        "guardian-engine",
        "services/guardian",
        ("engine",),
        allow=("engine.guardian_checks",),
        why="The Guardian may import engine.guardian_checks as a library and nothing else (R8).",
    ),
    Rule(
        "engine-isolated",
        "services/engine",
        ("fiona_agents", "fiona_guardian", "agents", "guardian", "services"),
        why="The engine never imports the agents or the Guardian (R1).",
    ),
    Rule(
        "checks-standalone",
        "services/engine/guardian_checks",
        ("engine",),
        allow=("engine.guardian_checks",),
        why="engine.guardian_checks must stay standalone so the Guardian can import it alone (R8).",
    ),
)


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _module_of(path: Path, root: Path) -> str | None:
    """Dotted module name for a file, for resolving relative imports."""
    rel = path.relative_to(root).with_suffix("")
    parts = rel.parts
    if parts[:2] == ("services", "engine"):
        dotted = ("engine", *parts[2:])
    elif parts[:1] == ("services",) and len(parts) > 2:
        dotted = parts[2:]  # services/agents/fiona_agents/x.py -> fiona_agents.x
    else:
        return None
    if dotted and dotted[-1] == "__init__":
        dotted = dotted[:-1]
    return ".".join(dotted)


def imported_modules(path: Path, root: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    here = _module_of(path, root)
    is_pkg = path.name == "__init__.py"
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                if here is None:
                    continue
                package = here.split(".") if is_pkg else here.split(".")[:-1]
                keep = len(package) - (node.level - 1)
                if keep < 0:
                    continue
                base = ".".join(package[:keep] + ([node.module] if node.module else []))
            found.append((node.lineno, base))
            # `from engine import ledger` imports engine.ledger
            found.extend((node.lineno, f"{base}.{a.name}") for a in node.names if a.name != "*")
    return found


def python_files(folder: Path):
    if not folder.exists():
        return
    for path in folder.rglob("*.py"):
        if not SKIP_DIRS.intersection(path.parts):
            yield path


def check(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    for rule in RULES:
        for path in python_files(root / rule.folder):
            for line, module in imported_modules(path, root):
                bad = any(_matches(module, p) for p in rule.forbid)
                if bad and not any(_matches(module, a) for a in rule.allow):
                    rel = path.relative_to(root).as_posix()
                    violations.append(f"{rel}:{line}: [{rule.name}] imports {module}. {rule.why}")
    return sorted(set(violations))


SELF_TEST_CASES = {
    # rule name -> (file, source) that must trigger it
    "agents-isolated": ("services/agents/fiona_agents/bad.py", "import engine.ledger\n"),
    "guardian-isolated": (
        "services/guardian/fiona_guardian/bad.py",
        "from fiona_agents.llm import client\n",
    ),
    "guardian-engine": (
        "services/guardian/fiona_guardian/bad2.py",
        "from engine.forecast import cash\n",
    ),
    "engine-isolated": ("services/engine/ledger/bad.py", "import fiona_guardian.combiner\n"),
    "checks-standalone": ("services/engine/guardian_checks/bad.py", "from ..ledger import db\n"),
}
ALLOWED_CASES = {
    "services/guardian/fiona_guardian/ok.py": "from engine.guardian_checks import policy\nimport fiona_contracts\n",
    "services/engine/guardian_checks/ok.py": "from . import arithmetic\nfrom engine.guardian_checks.policy import g03\n",
    "services/agents/fiona_agents/ok.py": "import httpx\nfrom fiona_agents.tools import bridge\n",
    "services/engine/forecast/ok.py": "from engine.ledger import db\n",
}


def self_test() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, (rel, source) in SELF_TEST_CASES.items():
            case_root = root / name
            (case_root / rel).parent.mkdir(parents=True, exist_ok=True)
            (case_root / rel).write_text(source, encoding="utf-8")
            if not any(f"[{name}]" in v for v in check(case_root)):
                failures.append(f"rule {name} did not fire on {rel}")
        ok_root = root / "allowed"
        for rel, source in ALLOWED_CASES.items():
            (ok_root / rel).parent.mkdir(parents=True, exist_ok=True)
            (ok_root / rel).write_text(source, encoding="utf-8")
        failures.extend(f"false positive: {v}" for v in check(ok_root))
    for f in failures:
        print(f"FAIL {f}")
    if not failures:
        print(
            f"self-test OK: all {len(SELF_TEST_CASES)} rules fire; {len(ALLOWED_CASES)} allowed imports pass."
        )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    violations = check()
    for v in violations:
        print(v)
    if violations:
        print(f"\n{len(violations)} import-boundary violation(s).")
        return 1
    print("import boundaries OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
