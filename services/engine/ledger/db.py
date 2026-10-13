"""Database helper for the Fiona engine: connect, migrate, reset, tenant-scoped sessions.

CLI (run from services/engine):
    python -m engine.ledger.db start | stop | status | url        shared local server (fiona_dev)
    python -m engine.ledger.db reset [--database NAME]            drop, recreate and migrate a database
    python -m engine.ledger.db migrate [--database NAME]          apply pending migrations
    python -m engine.ledger.db seed [--database NAME]             load fixture reference data

Without DATABASE_URL, the portable server from ``ledger.pg_local`` is used and started on
demand. With DATABASE_URL, every command targets that server. The database name in the URL
is the default target.

Tenant isolation: all tenant work runs inside ``tenant_session``. It switches to the
``fiona_engine`` role (no BYPASSRLS) and sets ``app.tenant_id`` for the transaction only.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg

from engine.ledger import pg_local

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
LOCAL_SHIM = REPO_ROOT / "supabase" / "local" / "supabase_shim.sql"
DEV_DATABASE = "fiona_dev"
ENGINE_ROLE = "fiona_engine"
TENANT_ID_RE = re.compile(r"^ten_[a-z0-9_]+$")
DB_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
# A migration that needs an extension the server lacks (pgvector on the portable build) starts
# with this header and is skipped locally. Supabase cloud has the extension and runs it.
REQUIRES_RE = re.compile(r"^--\s*fiona:requires-extension\s+(\w+)", re.MULTILINE)


def _remote_url() -> str | None:
    return os.environ.get("DATABASE_URL") or None


def is_local() -> bool:
    """True when the managed portable server is in use (the shim is applied only then)."""
    return _remote_url() is None


def default_database() -> str:
    url = _remote_url()
    if url:
        return urlsplit(url).path.lstrip("/") or "postgres"
    return DEV_DATABASE


def dsn(dbname: str | None = None) -> str:
    name = dbname or default_database()
    url = _remote_url()
    if url:
        parts = urlsplit(url)
        return urlunsplit(parts._replace(path="/" + name))
    pg_local.start()
    return pg_local.dsn(name)


def connect(dbname: str | None = None, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(dsn(dbname), autocommit=autocommit)


def _check_name(name: str) -> str:
    if not DB_NAME_RE.match(name):
        raise ValueError(f"Unsafe database name: {name!r}")
    return name


def create_database(name: str) -> None:
    with connect("postgres", autocommit=True) as conn:
        conn.execute(f'create database "{_check_name(name)}"')


def drop_database(name: str) -> None:
    if name == "postgres":
        raise ValueError("Refusing to drop the 'postgres' maintenance database")
    with connect("postgres", autocommit=True) as conn:
        conn.execute(f'drop database if exists "{_check_name(name)}" with (force)')


def database_exists(name: str) -> bool:
    with connect("postgres", autocommit=True) as conn:
        row = conn.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()
    return row is not None


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migrations(conn: psycopg.Connection, *, local: bool | None = None) -> list[str]:
    """Apply pending migrations in order, one transaction each. Returns the versions applied.

    Applied versions are recorded in supabase_migrations.schema_migrations, the same table the
    Supabase CLI uses, so local and cloud bookkeeping agree.
    """
    local = is_local() if local is None else local
    applied: list[str] = []
    with conn.transaction():
        if local:
            conn.execute(LOCAL_SHIM.read_text(encoding="utf-8"))
        conn.execute("create schema if not exists supabase_migrations")
        conn.execute(
            "create table if not exists supabase_migrations.schema_migrations"
            " (version text primary key, statements text[], name text)"
        )
    done = {r[0] for r in conn.execute("select version from supabase_migrations.schema_migrations")}
    available = {r[0] for r in conn.execute("select name from pg_available_extensions")}
    for path in migration_files():
        version, _, rest = path.stem.partition("_")
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        missing = [ext for ext in REQUIRES_RE.findall(sql) if ext not in available]
        if missing:
            print(
                f"skip {path.name}: extension {', '.join(missing)} not available here",
                file=sys.stderr,
            )
            continue
        with conn.transaction():
            conn.execute(sql)
            conn.execute(
                "insert into supabase_migrations.schema_migrations (version, statements, name)"
                " values (%s, %s, %s)",
                (version, [sql], rest),
            )
        applied.append(version)
    return applied


def reset(dbname: str | None = None) -> list[str]:
    """Drop and recreate the database, then apply every migration. Returns versions applied."""
    name = dbname or default_database()
    drop_database(name)
    create_database(name)
    with connect(name, autocommit=True) as conn:
        return apply_migrations(conn)


@contextmanager
def tenant_session(conn: psycopg.Connection, tenant_id: str) -> Iterator[psycopg.Connection]:
    """Run a block as the engine role, scoped to one tenant, inside one transaction.

    Row-level security then hides every other tenant's rows and rejects writes into them.
    """
    if not TENANT_ID_RE.match(tenant_id):
        raise ValueError(f"Invalid tenant id: {tenant_id!r}")
    if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        # Inside an outer transaction this block would be a savepoint, and SET LOCAL would
        # outlive it. Require a fresh transaction so the role and tenant end with the block.
        raise RuntimeError(
            "tenant_session needs a connection with no open transaction (use autocommit=True)"
        )
    with conn.transaction():
        conn.execute(f"set local role {ENGINE_ROLE}")
        conn.execute("select set_config('app.tenant_id', %s, true)", (tenant_id,))
        yield conn


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m engine.ledger.db", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "command", choices=["start", "stop", "status", "url", "reset", "migrate", "seed"]
    )
    parser.add_argument(
        "--database",
        default=None,
        help="target database (default: fiona_dev or the DATABASE_URL one)",
    )
    parser.add_argument(
        "--fixtures", default=None, help="fixtures directory for seed (default: data/fixtures)"
    )
    args = parser.parse_args(argv)

    if args.command in {"start", "stop", "status"} and not is_local():
        print("DATABASE_URL is set; the portable server is not used.")
        return 0
    if args.command == "start":
        pg_local.start()
        if not database_exists(DEV_DATABASE):
            create_database(DEV_DATABASE)
        print(f"running: {pg_local.dsn(DEV_DATABASE)}")
    elif args.command == "stop":
        pg_local.stop()
        print("stopped")
    elif args.command == "status":
        print("running" if pg_local.is_running() else "stopped")
    elif args.command == "url":
        print(dsn(args.database))
    elif args.command == "reset":
        versions = reset(args.database)
        print(f"reset {args.database or default_database()}: applied {len(versions)} migrations")
    elif args.command == "migrate":
        with connect(args.database, autocommit=True) as conn:
            versions = apply_migrations(conn)
        print(f"applied {len(versions)} migrations: {', '.join(versions) or 'none pending'}")
    elif args.command == "seed":
        from engine.ledger import seed

        fixtures = Path(args.fixtures) if args.fixtures else seed.DEFAULT_FIXTURES
        with connect(args.database, autocommit=True) as conn:
            counts = seed.seed_reference_data(conn, fixtures)
        for tenant, table_counts in counts.items():
            summary = ", ".join(f"{t}={n}" for t, n in table_counts.items())
            print(f"seeded {tenant}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
