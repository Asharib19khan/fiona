"""python -m data.generator --seed 42 --persona karachi_apparel --months 2 --out data/fixtures/"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from data.generator import load_mandates, load_persona
from data.generator.build import generate
from data.generator.write import write_tenant


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m data.generator", description="Fiona synthetic data generator"
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--persona", required=True, help="persona config name in data/generator/personas/"
    )
    parser.add_argument("--months", type=int, default=2)
    parser.add_argument("--out", type=Path, default=Path("data/fixtures"))
    args = parser.parse_args(argv)
    persona = load_persona(args.persona)
    mandates, mandates_source = load_mandates(persona["tenant"]["id"])
    output = generate(persona, args.seed, args.months, mandates)
    target = write_tenant(
        output,
        args.out,
        seed=args.seed,
        persona=args.persona,
        months=args.months,
        mandates_source=mandates_source,
    )
    print(
        f"SYNTHETIC data for {output.tenant['id']} ({output.tenant['period']['start']}..{output.tenant['period']['end']}) "
        f"-> {target}: {len(output.events)} events, {len(output.bank_rows)} bank lines, "
        f"{len(output.pos_rows)} POS rows, {len(output.bills)} bills"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
