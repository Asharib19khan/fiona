"""Loads the demo business into the local database the first time only (run by `pnpm dev`).

Never touches a database that already holds the demo tenant, and never touches a remote
database (DATABASE_URL set). Run from services/ with the engine's uv project.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())  # services/, so the `engine` package imports

from engine.ledger import db, pg_local

TENANT = os.environ.get("DEMO_TENANT_ID") or "ten_karachi_apparel"


def start_local_server() -> None:
    """Start the portable Postgres without waiting on its output pipes.

    pg_local.start() captures pg_ctl's output; on Windows the background server inherits those
    pipes and keeps them open, so a first start never returns. Starting it here (output to the
    log file only) means the engine finds it already running and skips its own start.
    """
    if not (pg_local.install_dir() / "bin").is_dir():
        print("[setup] Downloading the local database (one time, about 30 MB)...", flush=True)
    pg_local.install()
    data = pg_local.data_dir()
    if not (data / "PG_VERSION").exists():
        print("[setup] Creating the local database cluster...", flush=True)
        data.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                pg_local._exe("initdb"),
                "-D",
                str(data),
                "-U",
                pg_local.SUPERUSER,
                "-A",
                "trust",
                "-E",
                "UTF8",
                "--locale=C",
                "--no-instructions",
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if pg_local.is_running():
        return
    print("[setup] Starting the local database...", flush=True)
    flags = 0
    if os.name == "nt":  # keep the server alive after this process exits
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    options = f"-p {pg_local.port()} -c listen_addresses=localhost -c synchronous_commit=off"
    subprocess.run(
        [
            pg_local._exe("pg_ctl"),
            "start",
            "-D",
            str(data),
            "-l",
            str(pg_local.log_file()),
            "-o",
            options,
            "-w",
            "-t",
            "60",
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


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
    start_local_server()
    if demo_loaded():
        return 0
    print(
        "[setup] First run: loading the demo business into the local database (a minute or two)..."
    )
    return db._main(["demo-data"]) or 0


if __name__ == "__main__":
    sys.exit(main())
