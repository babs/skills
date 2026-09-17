#!/usr/bin/env python3
"""Dbmate-style async PostgreSQL migration runner.

Single-file, zero-framework migration tool using asyncpg and structlog.

Usage:
    db_migrate.py                          # Apply pending migrations
    db_migrate.py --dry-run                # Show what would be applied without executing
    db_migrate.py --status                 # Show migration status
    db_migrate.py --rollback [N]           # Rollback last N applied migrations (default 1)
    db_migrate.py --baseline               # Mark all migrations applied without running them
    db_migrate.py --create "add users"     # Create new migration file
    db_migrate.py --verbose                # Enable debug logging
    db_migrate.py --version                # Print tool version

Commands (--status, --rollback, --baseline, --dry-run, --create) are mutually
exclusive — combining them is rejected at parse time.

Migration files: YYYYMMDDHHMMSS_description.sql

    -- migrate:up
    CREATE TABLE ...;

    -- migrate:down
    DROP TABLE ...;

Blocks run in a transaction by default; disable per block with the dbmate
`transaction:false` option (e.g. for CREATE INDEX CONCURRENTLY):

    -- migrate:up transaction:false
    CREATE INDEX CONCURRENTLY ...;

A transaction:false block must contain a single statement: the driver executes
multi-statement strings inside an implicit transaction.

Environment:
    DATABASE_URL       PostgreSQL connection string (required)
    MIGRATIONS_DIR     Path to migrations directory (default: ./db/migrations)
    SCHEMA_NAME        PostgreSQL schema for tracking table (default: public)
"""

import argparse
import asyncio
import logging
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import structlog

# Lives in this file because it is vendored standalone. Stamped by the release
# workflow; pyproject.toml mirrors it (enforced by a unit test).
__version__ = "1.1.0"

log: structlog.stdlib.BoundLogger = structlog.get_logger()

_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Shared with pre-existing deployments of this tool — keep stable so concurrent
# runners (e.g. parallel k8s Jobs) always contend on the same lock.
ADVISORY_LOCK_ID = 8675309

# Gap between connection attempts while waiting for the database (see wait_for_database).
DB_WAIT_POLL_SECONDS = 2.0

MIGRATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.schema_migrations (
    version VARCHAR(14) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

MIGRATION_TEMPLATE = """\
-- Migration: {description}
-- Created: {timestamp}

-- migrate:up


-- migrate:down

"""


class MigrationError(Exception):
    """Raised when a migration operation fails."""


def validate_schema_name(schema: str) -> None:
    """Validate schema is a safe PostgreSQL identifier."""
    if not _VALID_IDENTIFIER.match(schema):
        raise MigrationError(f"invalid schema name: {schema!r}")


def setup_logging(verbose: bool = False) -> None:
    is_tty = sys.stdout.isatty()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if is_tty else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG if verbose else logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def normalize_database_url(url: str) -> str:
    """Strip SQLAlchemy driver suffixes so asyncpg can connect."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _match_migration_block(content: str, direction: str) -> re.Match[str] | None:
    """Match a migration block: group(1) = marker options, group(2) = SQL."""
    pattern = rf"--\s*migrate:{direction}([ \t][^\n]*)?\n(.*?)(?=--\s*migrate:|$)"
    return re.search(pattern, content, re.DOTALL | re.IGNORECASE)


def parse_migration(content: str, direction: str = "up") -> str | None:
    """Extract SQL block for the given direction from a migration file."""
    match = _match_migration_block(content, direction)
    if not match:
        return None
    sql = match.group(2).strip()
    return sql or None


def parse_transaction_option(content: str, direction: str = "up") -> bool:
    """Return whether the block should run in a transaction (dbmate `transaction:false` option)."""
    match = _match_migration_block(content, direction)
    if not match:
        return True
    options = match.group(1) or ""
    return "transaction:false" not in options.lower()


def discover_migrations(migrations_dir: Path) -> list[tuple[str, Path]]:
    """Return sorted (version, path) pairs from the migrations directory."""
    if not migrations_dir.exists():
        log.warning("migrations_dir_missing", path=str(migrations_dir))
        return []

    migrations: list[tuple[str, Path]] = []
    for f in sorted(migrations_dir.glob("*.sql")):
        match = re.match(r"^(\d{14})_", f.name)
        if match:
            migrations.append((match.group(1), f))
        else:
            log.warning("skipping_invalid_filename", file=f.name)
    return migrations


def create_migration(migrations_dir: Path, description: str) -> Path:
    """Create a new empty migration file and return its path."""
    migrations_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", description.lower()).strip("_") or "migration"
    filename = f"{timestamp}_{slug}.sql"
    path = migrations_dir / filename
    path.write_text(
        MIGRATION_TEMPLATE.format(description=description, timestamp=now.strftime("%Y-%m-%d %H:%M:%S UTC"))
    )
    log.info("migration_created", file=filename)
    return path


async def wait_for_database(database_url: str, wait_timeout: float) -> asyncpg.Connection:
    """Connect, retrying transient failures until ``wait_timeout`` seconds have elapsed.

    A Kubernetes Job or a compose ``depends_on`` often starts the runner before PostgreSQL
    accepts connections; without a wait the Job crash-loops (and with a low ``backoffLimit``
    it fails the deploy). ``wait_timeout <= 0`` connects exactly once — the default, so this
    changes nothing for a CLI run against a down database.

    Only transient conditions are retried: a refused connection / unresolved host (OSError)
    and PostgreSQL still starting up. A wrong password or a missing database is a permanent
    misconfiguration and fails immediately rather than after the whole budget.
    """
    deadline = time.monotonic() + wait_timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            return await asyncpg.connect(database_url, timeout=30)
        except (OSError, asyncpg.CannotConnectNowError) as e:
            if time.monotonic() + DB_WAIT_POLL_SECONDS > deadline:
                raise
            log.info("database_wait", attempt=attempt, error=str(e))
            await asyncio.sleep(DB_WAIT_POLL_SECONDS)


def parse_wait_timeout(raw: str) -> float:
    """Parse DB_WAIT_TIMEOUT. Raises MigrationError so a typo fails loudly, not silently at 0."""
    try:
        return float(raw)
    except ValueError as e:
        raise MigrationError(f"DB_WAIT_TIMEOUT must be a number of seconds, got {raw!r}") from e


async def acquire_lock(conn: asyncpg.Connection) -> None:
    """Block until this session holds the migration advisory lock."""
    await conn.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_ID)


async def release_lock(conn: asyncpg.Connection) -> None:
    await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)


async def _execute_unwrapped(conn: asyncpg.Connection, sql: str, source: str) -> None:
    """Run a transaction:false block without a transaction wrapper."""
    try:
        await conn.execute(sql)
    except asyncpg.ActiveSQLTransactionError as e:
        # asyncpg sends multi-statement strings as one simple query, which PostgreSQL
        # wraps in an implicit transaction — CONCURRENTLY & friends then refuse to run.
        raise MigrationError(
            f"{source}: {e} (a transaction:false block must contain a single statement)"
        ) from e


async def ensure_schema_and_table(conn: asyncpg.Connection, schema: str) -> None:
    validate_schema_name(schema)
    if schema != "public":
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    await conn.execute(MIGRATIONS_TABLE_DDL.format(schema=schema))


async def get_applied_versions(conn: asyncpg.Connection, schema: str) -> set[str]:
    validate_schema_name(schema)
    rows = await conn.fetch(f"SELECT version FROM {schema}.schema_migrations ORDER BY version")
    return {r["version"] for r in rows}


async def run_migrate(
    conn: asyncpg.Connection, schema: str, migrations_dir: Path, dry_run: bool = False
) -> int:
    """Apply all pending migrations. Returns count applied (or would-be applied in dry-run)."""
    await ensure_schema_and_table(conn, schema)
    applied = await get_applied_versions(conn, schema)
    all_migrations = discover_migrations(migrations_dir)
    pending = [(v, p) for v, p in all_migrations if v not in applied]

    if not pending:
        log.info("no_pending_migrations")
        return 0

    log.info("pending_migrations_found", count=len(pending))
    for version, path in pending:
        content = path.read_text()
        up_sql = parse_migration(content, "up")
        if not up_sql:
            raise MigrationError(f"no -- migrate:up block in {path.name}")

        if dry_run:
            log.info("would_apply_migration", file=path.name)
            continue

        use_tx = parse_transaction_option(content, "up")
        log.info("applying_migration", file=path.name, transaction=use_tx)
        if use_tx:
            async with conn.transaction():
                await conn.execute(up_sql)
                await conn.execute(f"INSERT INTO {schema}.schema_migrations (version) VALUES ($1)", version)
        else:
            # dbmate `transaction:false`: run unwrapped (e.g. CREATE INDEX CONCURRENTLY).
            # Version recorded only after success — a partial failure leaves the migration pending.
            await _execute_unwrapped(conn, up_sql, path.name)
            await conn.execute(f"INSERT INTO {schema}.schema_migrations (version) VALUES ($1)", version)

    if dry_run:
        log.info("dry_run_complete", pending=len(pending))
    else:
        log.info("migrations_applied", count=len(pending))
    return len(pending)


async def run_rollback(conn: asyncpg.Connection, schema: str, migrations_dir: Path, count: int = 1) -> int:
    """Rollback the last N applied migrations. Returns count rolled back."""
    if count < 1:
        raise MigrationError(f"rollback count must be >= 1, got {count}")

    await ensure_schema_and_table(conn, schema)

    rows = await conn.fetch(
        f"SELECT version FROM {schema}.schema_migrations ORDER BY version DESC LIMIT $1", count
    )
    if not rows:
        log.info("nothing_to_rollback")
        return 0

    migration_map = dict(discover_migrations(migrations_dir))
    rolled_back = 0
    for row in rows:
        version = row["version"]
        path = migration_map.get(version)
        if not path:
            raise MigrationError(f"migration file for version {version} not found on disk")

        content = path.read_text()
        down_sql = parse_migration(content, "down")
        if not down_sql:
            raise MigrationError(f"no -- migrate:down block in {path.name}")

        use_tx = parse_transaction_option(content, "down")
        log.info("rolling_back", file=path.name, transaction=use_tx)
        if use_tx:
            async with conn.transaction():
                await conn.execute(down_sql)
                await conn.execute(f"DELETE FROM {schema}.schema_migrations WHERE version = $1", version)
        else:
            await _execute_unwrapped(conn, down_sql, path.name)
            await conn.execute(f"DELETE FROM {schema}.schema_migrations WHERE version = $1", version)
        log.info("rolled_back", file=path.name)
        rolled_back += 1

    return rolled_back


async def run_baseline(conn: asyncpg.Connection, schema: str, migrations_dir: Path) -> int:
    """Mark all pending migrations as applied without executing them. Returns count baselined."""
    await ensure_schema_and_table(conn, schema)
    applied = await get_applied_versions(conn, schema)
    pending = [(v, p) for v, p in discover_migrations(migrations_dir) if v not in applied]

    if not pending:
        log.info("nothing_to_baseline")
        return 0

    for version, path in pending:
        await conn.execute(f"INSERT INTO {schema}.schema_migrations (version) VALUES ($1)", version)
        log.info("baselined_migration", file=path.name)

    log.info("baseline_complete", count=len(pending))
    return len(pending)


async def run_status(conn: asyncpg.Connection, schema: str, migrations_dir: Path) -> None:
    """Print migration status table."""
    await ensure_schema_and_table(conn, schema)
    applied = await get_applied_versions(conn, schema)
    all_migrations = discover_migrations(migrations_dir)

    if not all_migrations:
        print(f"No migration files found in {migrations_dir}")
        return

    pending_count = 0
    for version, path in all_migrations:
        marker = "applied" if version in applied else "pending"
        if marker == "pending":
            pending_count += 1
        print(f"  [{marker:>7}]  {path.name}")

    print()
    if pending_count:
        print(f"  {pending_count} pending migration(s)")
    else:
        print("  All migrations applied.")


async def async_main(args: argparse.Namespace) -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        log.error("DATABASE_URL environment variable is required")
        sys.exit(1)

    database_url = normalize_database_url(database_url)
    schema = os.environ.get("SCHEMA_NAME", "public")
    migrations_dir = Path(os.environ.get("MIGRATIONS_DIR", "db/migrations"))

    try:
        validate_schema_name(schema)
        wait_timeout = parse_wait_timeout(os.environ.get("DB_WAIT_TIMEOUT", "0"))
    except MigrationError as e:
        log.error("invalid_configuration", error=str(e), schema=schema)
        sys.exit(1)

    conn = await wait_for_database(database_url, wait_timeout)
    try:
        # Every command touches the tracking table (ensure_schema_and_table), so always
        # serialize on the advisory lock — cheap for read-only commands, and avoids the
        # concurrent-first-run race on CREATE TABLE IF NOT EXISTS.
        await acquire_lock(conn)
        if args.status:
            await run_status(conn, schema, migrations_dir)
        elif args.rollback is not None:
            await run_rollback(conn, schema, migrations_dir, count=args.rollback)
        elif args.baseline:
            await run_baseline(conn, schema, migrations_dir)
        else:
            await run_migrate(conn, schema, migrations_dir, dry_run=args.dry_run)
    except MigrationError as e:
        log.error("migration_failed", error=str(e))
        sys.exit(1)
    finally:
        try:
            await release_lock(conn)
        finally:
            await conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async PostgreSQL migration runner")
    # One command per invocation — combining e.g. --dry-run with --rollback would
    # otherwise silently execute the destructive branch.
    command = parser.add_mutually_exclusive_group()
    command.add_argument("--status", action="store_true", help="Show migration status")
    command.add_argument(
        "--rollback",
        nargs="?",
        const=1,
        type=int,
        metavar="N",
        help="Rollback last N applied migrations (default: 1)",
    )
    command.add_argument(
        "--baseline", action="store_true", help="Mark all migrations applied without running them"
    )
    command.add_argument(
        "--dry-run", action="store_true", help="Show pending migrations without applying them"
    )
    command.add_argument("--create", metavar="DESC", help="Create a new migration file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    setup_logging(verbose=args.verbose)

    if args.create:
        migrations_dir = Path(os.environ.get("MIGRATIONS_DIR", "db/migrations"))
        create_migration(migrations_dir, args.create)
        return

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
