"""Emulator fixtures for foundation integration tests.

These tests need a running Spanner emulator (SPANNER_EMULATOR_HOST). Without
one they are skipped with an explicit reason; `pnpm check` reports skips as
not_run, never as passed.
"""
import importlib.util
import os
import socket
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("BRANDME_MODE", "development")


def _emulator_up() -> bool:
    host = os.environ.get("SPANNER_EMULATOR_HOST", "")
    if not host:
        return False
    h, _, p = host.partition(":")
    try:
        with socket.create_connection((h, int(p or 9010)), timeout=1):
            return True
    except OSError:
        return False


requires_spanner = pytest.mark.skipif(not _emulator_up(), reason="Spanner emulator not reachable (SPANNER_EMULATOR_HOST)")


def load_runner():
    spec = importlib.util.spec_from_file_location("bm_migrations", REPO / "brandme-data/spanner/migrations/runner.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bm_migrations"] = mod  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def runner():
    return load_runner()


def _new_database(name_prefix: str):
    from google.cloud import spanner

    project = os.environ.get("SPANNER_PROJECT_ID", "test-project")
    client = spanner.Client(project=project)
    instance = client.instance("brandme-instance")
    if not instance.exists():
        client.instance("brandme-instance", configuration_name=f"projects/{project}/instanceConfigs/emulator-config",
                        node_count=1).create().result(60)
        instance = client.instance("brandme-instance")
    db = instance.database(f"{name_prefix}-{uuid.uuid4().hex[:8]}")
    db.create().result(60)
    return db


@pytest.fixture
def empty_database():
    db = _new_database("t-empty")
    yield db
    db.drop()


@pytest.fixture(scope="module")
def migrated_database():
    db = _new_database("t-v001")
    load_runner().migrate_up(db, log=lambda *_: None)
    yield db
    db.drop()
