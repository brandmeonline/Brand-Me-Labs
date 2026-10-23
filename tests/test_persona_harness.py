"""
Spanner-emulator harness shared by this lane's tests (persona, wardrobe,
social, rewards, media). Not a test module itself; pytest collects nothing here.

Each test session creates a fresh, uniquely named database and applies every
migration in ``brandme-data/spanner/migrations`` (foundation V001 + this lane's
V002..V005, plus whatever other lanes have merged) through the foundation
migration runner and its checksum ledger, i.e. from an empty schema.

If the emulator is unreachable, Spanner-backed tests are skipped with an
explicit reason (they are then *not_run*, never passed).
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
import uuid
from pathlib import Path
from typing import Iterable

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "brandme-data" / "spanner" / "migrations" / "runner.py"
EMULATOR = os.environ.get("SPANNER_EMULATOR_HOST", "localhost:9010")
PROJECT = "consumer-domains-test"
INSTANCE = "consumer-domains"

# Scopes a fully signed-in first-party member session holds in these tests.
MEMBER_SCOPES = frozenset(
    {
        "profile:read",
        "profile:write",
        "wardrobe:read",
        "wardrobe:write",
        "outfits:read",
        "outfits:write",
        "social:read",
        "social:write",
        "rewards:read",
        "privacy:manage",
    }
)


def load_runner():
    spec = importlib.util.spec_from_file_location("bm_migrations_lane", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bm_migrations_lane"] = mod
    spec.loader.exec_module(mod)
    return mod


def emulator_up() -> bool:
    host, _, port = EMULATOR.partition(":")
    try:
        with socket.create_connection((host, int(port or 9010)), timeout=1):
            return True
    except OSError:
        return False


def new_migrated_database():
    """A fresh emulator database with every migration applied by the runner."""
    if not emulator_up():
        pytest.skip(f"Spanner emulator not reachable at {EMULATOR}; Spanner-backed tests NOT RUN")
    os.environ["SPANNER_EMULATOR_HOST"] = EMULATOR
    from google.cloud import spanner

    client = spanner.Client(project=PROJECT)
    instance = client.instance(INSTANCE)
    if not instance.exists():
        client.instance(
            INSTANCE, configuration_name=f"projects/{PROJECT}/instanceConfigs/emulator-config", node_count=1
        ).create().result(120)
        instance = client.instance(INSTANCE)
    database = instance.database("cd" + uuid.uuid4().hex[:20])
    database.create().result(120)
    applied = load_runner().migrate_up(database, applied_by="consumer-domains-tests", log=lambda *_: None)
    assert applied and applied[0] == 1, f"runner did not apply from V001 on an empty database: {applied}"
    database.applied_versions = applied
    return database


@pytest.fixture(scope="session")
def spanner_db():
    database = new_migrated_database()
    yield database
    try:
        database.drop()
    except Exception:
        pass


def insert_member(db, member_id: str | None = None, *, account_state: str = "active") -> str:
    """Create a V001 Members row (the persona aggregate is interleaved in it)."""
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    member_id = member_id or str(uuid.uuid4())

    def tx(t):
        t.insert(
            "Members",
            columns=(
                "member_id",
                "locale",
                "timezone",
                "age_eligibility_status",
                "account_state",
                "environment",
                "onboarding_state",
                "version",
                "created_at",
                "updated_at",
            ),
            values=[
                (member_id, "en-US", "UTC", "self_declared_adult", account_state, "development", "not_started", 1,
                 COMMIT_TIMESTAMP, COMMIT_TIMESTAMP)
            ],
        )

    from brandme_core.domains.persona.kernel import run_txn

    run_txn(db, tx)
    return member_id


def member(db, scopes: Iterable[str] = MEMBER_SCOPES, **kw):
    from brandme_core.domains.persona.kernel import member_principal

    return member_principal(insert_member(db), scopes, **kw)


def count(db, sql: str, **params) -> int:
    from google.cloud.spanner_v1 import param_types

    with db.snapshot() as s:
        return list(s.execute_sql(sql, params=params, param_types={k: param_types.STRING for k in params}))[0][0]


class AbortCause:
    """grpc.Call stand-in: the client reads retry delay from trailing metadata."""

    def trailing_metadata(self):
        return []


class AbortOnceDB:
    """Wraps a Database so the first attempt of each transaction raises ABORTED
    *after* the domain callback has buffered all its mutations (incl. outbox)."""

    def __init__(self, db):
        self._db = db
        self.attempts = 0

    def __getattr__(self, name):
        return getattr(self._db, name)

    def run_in_transaction(self, fn, *a, **kw):
        from google.api_core.exceptions import Aborted

        state = {"n": 0}

        def wrapped(txn, *fa, **fkw):
            state["n"] += 1
            self.attempts += 1
            out = fn(txn, *fa, **fkw)
            if state["n"] == 1:
                raise Aborted("injected abort after buffering mutations", errors=[AbortCause()])
            return out

        return self._db.run_in_transaction(wrapped, *a, **kw)
