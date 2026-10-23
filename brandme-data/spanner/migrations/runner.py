#!/usr/bin/env python3
"""Versioned Spanner GoogleSQL migrations with a checksum ledger.

    python brandme-data/spanner/migrations/runner.py up [--create-database] [--wait SECONDS]
    python brandme-data/spanner/migrations/runner.py status
    python brandme-data/spanner/migrations/runner.py verify   # exit 1 on checksum drift / pending

Files are ``V<NNN>_<name>.sql`` in this directory. Each file is applied as one
DDL batch, then recorded in ``SchemaMigrations`` with its SHA-256 checksum.
Spanner DDL is not transactional, so the runner writes an ``applying`` ledger
row first: a batch that fails part-way leaves that row behind and later runs
refuse to continue until an operator inspects the schema (``repair``).
Nothing is ever masked with ``|| true``.

Services call :func:`assert_schema_supported` at startup so a deployment
refuses to run against an unsupported schema range.

Version reservations (do not reuse another lane's number): V001 identity/platform
(foundation), V002 persona, V003 wardrobe, V004 social, V005 rewards,
V006 providers, V007 commerce, V008 rights, V009 privacy.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

MIGRATIONS_DIR = Path(__file__).resolve().parent
FILE_RE = re.compile(r"^V(\d{3})_([a-z0-9_]+)\.sql$")
LEDGER_DDL = """CREATE TABLE SchemaMigrations (
  version INT64 NOT NULL,
  name STRING(128) NOT NULL,
  checksum STRING(64) NOT NULL,
  state STRING(16) NOT NULL,
  statement_count INT64 NOT NULL,
  applied_by STRING(128) NOT NULL,
  started_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  applied_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (version)"""


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    statements: tuple[str, ...]


def split_statements(sql: str) -> list[str]:
    """Strip ``--`` comments and split on ``;`` outside string literals."""
    out, buf, quote = [], [], None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote is None and sql.startswith("--", i):
            nl = sql.find("\n", i)
            i = len(sql) if nl == -1 else nl
            continue
        if ch in ("'", '"', "`"):
            if quote is None:
                quote = ch
            elif quote == ch:
                quote = None
        if ch == ";" and quote is None:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    found: dict[int, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        m = FILE_RE.match(path.name)
        if not m:
            raise MigrationError(f"{path.name}: migration files must be named V<NNN>_<name>.sql")
        version = int(m.group(1))
        if version in found:
            raise MigrationError(f"duplicate migration version V{version:03d}")
        raw = path.read_bytes()
        statements = tuple(split_statements(raw.decode("utf-8")))
        if not statements:
            raise MigrationError(f"{path.name}: no statements")
        found[version] = Migration(version, m.group(2), path, hashlib.sha256(raw).hexdigest(), statements)
    return [found[v] for v in sorted(found)]


def _wait_for_emulator(client, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            list(client.list_instance_configs())
            return
        except Exception as exc:  # emulator not accepting connections yet
            if time.monotonic() > deadline:
                raise MigrationError(f"Spanner not reachable after {seconds}s: {exc}") from exc
            time.sleep(1)


def open_database(create: bool = False, wait: float = 0.0):
    from google.cloud import spanner

    project = os.environ.get("SPANNER_PROJECT_ID", "test-project")
    instance_id = os.environ.get("SPANNER_INSTANCE_ID", "brandme-instance")
    database_id = os.environ.get("SPANNER_DATABASE_ID", "brandme-db")
    client = spanner.Client(project=project)
    if wait:
        _wait_for_emulator(client, wait)
    instance = client.instance(instance_id)
    database = instance.database(database_id)
    if create:
        if not os.environ.get("SPANNER_EMULATOR_HOST"):
            raise MigrationError("--create-database is only allowed against the emulator")
        if not instance.exists():
            instance = client.instance(
                instance_id,
                configuration_name=f"projects/{project}/instanceConfigs/emulator-config",
                node_count=1,
            )
            instance.create().result(120)
        database = instance.database(database_id)
        if not database.exists():
            database.create().result(120)
    elif not database.exists():
        raise MigrationError(f"database {project}/{instance_id}/{database_id} does not exist")
    return database


def _table_exists(database, table: str) -> bool:
    from google.cloud.spanner_v1 import param_types

    with database.snapshot() as snap:
        rows = list(
            snap.execute_sql(
                "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '' AND TABLE_NAME = @t",
                params={"t": table},
                param_types={"t": param_types.STRING},
            )
        )
    return bool(rows)


def ensure_ledger(database) -> None:
    if not _table_exists(database, "SchemaMigrations"):
        database.update_ddl([LEDGER_DDL]).result(300)


def read_ledger(database) -> dict[int, dict]:
    if not _table_exists(database, "SchemaMigrations"):
        return {}
    with database.snapshot() as snap:
        rows = snap.execute_sql(
            "SELECT version, name, checksum, state, statement_count, applied_at FROM SchemaMigrations ORDER BY version"
        )
        return {
            r[0]: {"name": r[1], "checksum": r[2], "state": r[3], "statement_count": r[4], "applied_at": r[5]}
            for r in rows
        }


def plan(migrations: Iterable[Migration], ledger: dict[int, dict], allow_out_of_order: bool = False) -> list[Migration]:
    migrations = list(migrations)
    by_version = {m.version: m for m in migrations}
    for version, row in ledger.items():
        if row["state"] != "applied":
            raise MigrationError(
                f"V{version:03d} is in state {row['state']!r} (a previous batch failed part-way); "
                "inspect the schema, then run `repair --version` before continuing"
            )
        m = by_version.get(version)
        if m is None:
            raise MigrationError(f"V{version:03d} is applied but its file is missing")
        if m.checksum != row["checksum"]:
            raise MigrationError(f"V{version:03d} checksum drift: ledger {row['checksum'][:12]}…, file {m.checksum[:12]}…")
    pending = [m for m in migrations if m.version not in ledger]
    highest = max(ledger, default=0)
    late = [m for m in pending if m.version < highest]
    if late and not allow_out_of_order:
        raise MigrationError(
            "out-of-order migrations " + ", ".join(f"V{m.version:03d}" for m in late)
            + f" are older than applied V{highest:03d}; merge order must be fixed or use --allow-out-of-order (non-production)"
        )
    return pending


def apply(database, migration: Migration, applied_by: str) -> None:
    from google.cloud import spanner

    def _start(tx):
        tx.insert(
            "SchemaMigrations",
            columns=("version", "name", "checksum", "state", "statement_count", "applied_by", "started_at"),
            values=[(migration.version, migration.name, migration.checksum, "applying",
                     len(migration.statements), applied_by, spanner.COMMIT_TIMESTAMP)],
        )

    database.run_in_transaction(_start)
    database.update_ddl(list(migration.statements)).result(600)

    def _finish(tx):
        tx.update(
            "SchemaMigrations",
            columns=("version", "state", "applied_at"),
            values=[(migration.version, "applied", spanner.COMMIT_TIMESTAMP)],
        )

    database.run_in_transaction(_finish)


def migrate_up(database, migrations: Optional[list[Migration]] = None, applied_by: str = "runner",
               allow_out_of_order: bool = False, log=print) -> list[int]:
    migrations = load_migrations() if migrations is None else migrations
    ensure_ledger(database)
    pending = plan(migrations, read_ledger(database), allow_out_of_order)
    for m in pending:
        log(f"applying V{m.version:03d}_{m.name} ({len(m.statements)} statements)")
        try:
            apply(database, m, applied_by)
        except Exception as exc:
            raise MigrationError(f"V{m.version:03d}_{m.name} failed: {exc}") from exc
    if not pending:
        log("schema up to date")
    return [m.version for m in pending]


def assert_schema_supported(database, minimum: int, maximum: Optional[int] = None) -> int:
    """Refuse to run against a schema outside [minimum, maximum]. Returns current version."""
    ledger = read_ledger(database)
    bad = [v for v, r in ledger.items() if r["state"] != "applied"]
    if bad:
        raise MigrationError(f"schema has incomplete migrations: {bad}")
    current = max(ledger, default=0)
    if current < minimum or (maximum is not None and current > maximum):
        raise MigrationError(f"schema version {current} outside supported range [{minimum}, {maximum or '∞'}]")
    return current


def _status(database) -> int:
    ledger = read_ledger(database)
    files = {m.version: m for m in load_migrations()}
    rc = 0
    for v in sorted(set(ledger) | set(files)):
        row, f = ledger.get(v), files.get(v)
        if row and f and row["checksum"] == f.checksum and row["state"] == "applied":
            state = "applied"
        elif row and f and row["checksum"] != f.checksum:
            state, rc = "CHECKSUM DRIFT", 1
        elif row and row["state"] != "applied":
            state, rc = f"INCOMPLETE ({row['state']})", 1
        elif row and not f:
            state, rc = "FILE MISSING", 1
        else:
            state, rc = "pending", 1
        name = (f.name if f else row["name"])
        print(f"V{v:03d}_{name:<24} {state}")
    return rc


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("up")
    up.add_argument("--create-database", action="store_true", help="emulator only")
    up.add_argument("--wait", type=float, default=0.0)
    up.add_argument("--allow-out-of-order", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    rep = sub.add_parser("repair", help="mark an inspected, completed `applying` row as applied")
    rep.add_argument("--version", type=int, required=True)
    args = p.parse_args(argv)

    try:
        if args.cmd == "up":
            if args.allow_out_of_order and os.environ.get("BRANDME_MODE", "") in ("sandbox", "production"):
                raise MigrationError("--allow-out-of-order is refused in sandbox/production")
            db = open_database(create=args.create_database, wait=args.wait)
            migrate_up(db, applied_by=os.environ.get("HOSTNAME", "runner"), allow_out_of_order=args.allow_out_of_order)
            return _status(db)
        db = open_database()
        if args.cmd in ("status", "verify"):
            return _status(db)
        if args.cmd == "repair":
            from google.cloud import spanner

            def _repair(tx):
                tx.update("SchemaMigrations", columns=("version", "state", "applied_at"),
                          values=[(args.version, "applied", spanner.COMMIT_TIMESTAMP)])

            db.run_in_transaction(_repair)
            print(f"V{args.version:03d} marked applied by operator repair")
            return 0
    except MigrationError as exc:
        print(f"migration error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
