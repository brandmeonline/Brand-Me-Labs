"""Dev-form My Data composition: every real handler in one registry (real migrations, Spanner emulator).

One account deletion runs across the consumer domains, commerce, rights and
foundation's platform records and finishes every category, including the
rights rows on both sides of a transfer intent.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from google.cloud import spanner
from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject

from brandme_core.domains.media.store import MemoryMediaStore
from brandme_core.domains.privacy.composition import compose_my_data, compose_registry

ROOT = Path(__file__).resolve().parents[1]
MEMBER = "11111111-1111-4111-8111-111111111111"
SENDER = "22222222-2222-4222-8222-222222222222"
CONTRACT = "ab" * 32
DOMAINS = {"commerce", "media", "persona", "platform", "rewards", "rights", "social", "wardrobe"}


class MemoryObjectStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, data, content_type):
        self.objects[key] = data
        return f"mem://{key}"

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture(scope="module")
def database():
    host, _, port = os.environ.get("SPANNER_EMULATOR_HOST", "127.0.0.1:9010").partition(":")
    try:
        socket.create_connection((host, int(port)), timeout=1).close()
    except OSError:
        pytest.skip("Spanner emulator not running")
    client = spanner.Client(project="test-project")
    inst = client.instance("my-data-composition", configuration_name="projects/test-project/instanceConfigs/emulator-config",
                           node_count=1)
    if not inst.exists():
        inst.create().result(60)
    db = inst.database("mydata-" + uuid.uuid4().hex[:12])
    db.create().result(60)
    spec = importlib.util.spec_from_file_location("composition_migrations", ROOT / "brandme-data/spanner/migrations/runner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.migrate_up(db, log=lambda *_: None)
    yield db
    db.drop()


def rows(db, sql):
    with db.snapshot() as snap:
        return [list(r) for r in snap.execute_sql(sql)]


def test_registry_covers_every_real_domain_and_refuses_strict_modes(database):
    assert {c.domain for c in compose_registry().categories()} == DOMAINS
    with pytest.raises(ValueError, match="demo or development"):
        compose_my_data(database, MemoryObjectStore(), environment="sandbox")


def test_account_deletion_finishes_every_category_across_all_domains(database):
    now = datetime.now(timezone.utc)
    ent, received = "c1" * 32, "c2" * 32
    with database.batch() as b:
        b.insert("RightsEntitlements", ["network", "contract_address", "entitlement_id", "asset_id", "issuer_id", "epoch", "status",
                                        "transferable", "reprintable", "controller_subject_ref", "last_tx_id", "last_block_height",
                                        "finalized_at", "updated_at"],
                 [["preprod", CONTRACT, ent, str(uuid.uuid4()), "15" * 32, 1, "active", True, False, MEMBER, "tx", 1, now, COMMIT_TIMESTAMP]])
        b.insert("TransferIntents", ["intent_id", "network", "contract_address", "entitlement_id", "from_subject_ref",
                                     "recipient_subject_ref", "recipient_commitment", "rights_scope_json", "expected_epoch", "state",
                                     "expires_at", "created_at", "updated_at"],
                 [[str(uuid.uuid4()), "preprod", CONTRACT, ent, MEMBER, None, None, JsonObject({"rights_scope": ["transfer"]}), 1,
                   "AwaitingRecipient", now + timedelta(hours=1), now, COMMIT_TIMESTAMP],
                  [str(uuid.uuid4()), "preprod", CONTRACT, received, SENDER, MEMBER, "c0" * 32, JsonObject({"rights_scope": ["transfer"]}),
                   3, "ReadyToProve", now + timedelta(hours=1), now, COMMIT_TIMESTAMP]])
    svc = compose_my_data(database, MemoryObjectStore(), environment="development", media_store=MemoryMediaStore())
    receipt = svc.run_deletion(svc.request_deletion(MEMBER, now))
    statuses = {k: r["status"] for k, r in receipt["categories"].items()}
    assert {k.split(".")[0] for k in statuses} == DOMAINS
    assert not {s for s in statuses.values() if s.startswith("pending")}, statuses
    assert receipt["completed_at"] is not None
    assert rows(database, "SELECT controller_subject_ref FROM RightsEntitlements") == [[None]]
    assert rows(database, "SELECT from_subject_ref, recipient_subject_ref, state FROM TransferIntents") == [[SENDER, None, "Cancelled"]]
