"""python -m data.generator --seed 42 --persona karachi_apparel --months 24 --out data/fixtures/"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from data.generator import load_mandates, load_persona, load_scenarios
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
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--out", type=Path, default=Path("data/fixtures"))
    args = parser.parse_args(argv)
    persona = load_persona(args.persona)
    mandates, source = load_mandates(persona["tenant"]["id"])
    output = generate(persona, args.seed, args.months, mandates, load_scenarios(), source)
    published, held_out = write_tenant(
        output, args.out, seed=args.seed, persona=args.persona, months=args.months
    )
    files = output["files"]
    print(
        f"SYNTHETIC data for {files['tenant.json']['id']} {files['tenant.json']['period']} -> {published}: "
        f"{len(files['events.jsonl'])} events, {len(files['bank_statement.csv'])} bank lines, "
        f"{len(files['pos_sales.csv'])} POS rows, {len(files['bills.json']['bills'])} bills; held out -> {held_out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
