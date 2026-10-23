"""Commerce store fixtures: every parametrized test runs on the in-memory store and on Spanner.

The Spanner variant uses one emulator database per test module, migrated with the
repository's migration runner (V001 foundation outbox + V006/V007), and wipes
the commerce and outbox tables before each test. Without a reachable emulator
the Spanner variant is skipped with an explicit reason, never reported as passed.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
# Children before parents (OrderLines is interleaved ON DELETE NO ACTION).
WIPE_ORDER = (
    "OrderLines", "Orders", "ReturnRequests", "CartLines", "Carts", "QuoteLines", "CheckoutQuotes",
    "ApprovalChallenges", "PurchaseApprovals", "MemberSurfaceKeys", "Ap2UsedMandates", "PurchaseOperations",
    "DelegationBudgetEntries", "AgentDelegations", "CommerceIdempotencyKeys", "ProviderWebhookReceipts",
    "OutboxEvents",
)


def emulator_up() -> bool:
    host = os.environ.get("SPANNER_EMULATOR_HOST", "")
    if not host:
        return False
    h, _, p = host.partition(":")
    try:
        with socket.create_connection((h, int(p or 9010)), timeout=1):
            return True
    except OSError:
        return False


def _runner():
    spec = importlib.util.spec_from_file_location("bm_migrations", REPO / "brandme-data/spanner/migrations/runner.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bm_migrations"] = mod
    spec.loader.exec_module(mod)
    return mod


def migrated_commerce_database():
    from google.cloud import spanner

    project = os.environ.get("SPANNER_PROJECT_ID", "test-project")
    client = spanner.Client(project=project)
    instance = client.instance("brandme-instance")
    if not instance.exists():
        client.instance("brandme-instance", configuration_name=f"projects/{project}/instanceConfigs/emulator-config",
                        node_count=1).create().result(60)
        instance = client.instance("brandme-instance")
    db = instance.database(f"t-com-{uuid.uuid4().hex[:8]}")
    db.create().result(60)
    _runner().migrate_up(db, log=lambda *_: None)
    return db


def wipe(db) -> None:
    from google.cloud.spanner_v1 import KeySet

    def _tx(tx):
        for table in WIPE_ORDER:
            tx.delete(table, KeySet(all_=True))
    db.run_in_transaction(_tx)


@pytest.fixture(scope="module")
def _spanner_db():
    if not emulator_up():
        pytest.skip("Spanner emulator not reachable (SPANNER_EMULATOR_HOST)")
    db = migrated_commerce_database()
    yield db
    db.drop()


@pytest.fixture(params=["memory", "spanner"])
def commerce_store(request):
    if request.param == "memory":
        from brandme_core.domains.commerce.store import InMemoryCommerceStore
        return InMemoryCommerceStore()
    db = request.getfixturevalue("_spanner_db")
    wipe(db)
    from brandme_core.domains.commerce.spanner_store import SpannerCommerceStore
    return SpannerCommerceStore(db)
