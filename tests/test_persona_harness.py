"""
Spanner-emulator harness shared by this lane's tests (persona, wardrobe,
social, rewards, media). Not a test module itself; pytest collects nothing here.

Each test session creates a fresh, uniquely named database and applies
``tests/fixtures/persona/interim_foundation.sql`` followed by V002..V005 in
order — i.e. every run exercises the migrations from an empty schema.

If the emulator is unreachable, Spanner-backed tests are skipped with an
explicit reason (they are then *not_run*, never passed).
"""

from __future__ import annotations

import os
import re
import socket
import uuid
from pathlib import Path
from typing import List

import pytest

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "brandme-data" / "spanner" / "migrations"
INTERIM = REPO / "tests" / "fixtures" / "persona" / "interim_foundation.sql"
LANE_MIGRATIONS = ("V002_persona.sql", "V003_wardrobe.sql", "V004_social.sql", "V005_rewards.sql")

EMULATOR = os.environ.get("SPANNER_EMULATOR_HOST", "localhost:9010")
PROJECT = "consumer-domains-test"
INSTANCE = "consumer-domains"


def split_ddl(sql: str) -> List[str]:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [s.strip() for s in body.split(";") if s.strip()]


def lane_ddl() -> List[str]:
    stmts = split_ddl(INTERIM.read_text())
    for name in LANE_MIGRATIONS:
        path = MIGRATIONS_DIR / name
        if path.exists():
            stmts.extend(split_ddl(path.read_text()))
    return stmts


def emulator_up() -> bool:
    host, port = EMULATOR.split(":")
    try:
        with socket.create_connection((host, int(port)), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def spanner_db():
    if not emulator_up():
        pytest.skip(f"Spanner emulator not reachable at {EMULATOR}; Spanner-backed tests NOT RUN")
    os.environ["SPANNER_EMULATOR_HOST"] = EMULATOR
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import spanner
    from google.cloud.spanner_admin_instance_v1.types import Instance

    client = spanner.Client(project=PROJECT)
    instance = client.instance(INSTANCE)
    try:
        op = client.instance_admin_api.create_instance(
            parent=f"projects/{PROJECT}",
            instance_id=INSTANCE,
            instance=Instance(
                config=f"projects/{PROJECT}/instanceConfigs/emulator-config",
                display_name="consumer domains",
                node_count=1,
            ),
        )
        op.result(60)
    except AlreadyExists:
        pass
    db_id = "cd" + uuid.uuid4().hex[:20]
    database = instance.database(db_id, ddl_statements=lane_ddl())
    database.create().result(120)
    yield database
    try:
        database.drop()
    except Exception:
        pass
