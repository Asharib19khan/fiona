"""Loads the demo business into the local database the first time only (run by `pnpm dev`).

Never touches a database that already holds the demo tenant, and never touches a remote
database (DATABASE_URL set). Run from services/ with the engine's uv project.
"""

import os
import sys

sys.path.insert(0, os.getcwd())  # services/, so the `engine` package imports

from engine.ledger import db

TENANT = os.environ.get("DEMO_TENANT_ID") or "ten_karachi_apparel"


def demo_loaded() -> bool:
    name = db.default_database()
    if not db.database_exists(name):
        return False
    try:
        with db.connect(name) as conn:
            row = conn.execute("select 1 from public.tenants where id = %s", (TENANT,)).fetchone()
            return row is not None
    except Exception:  # missing tables: the database was never migrated
        return False


def main() -> int:
    if os.environ.get("DATABASE_URL"):
        return 0
    if demo_loaded():
        return 0
    print(
        "[setup] First run: loading the demo business into the local database (a minute or two)..."
    )
    return db._main(["demo-data"]) or 0


if __name__ == "__main__":
    sys.exit(main())
