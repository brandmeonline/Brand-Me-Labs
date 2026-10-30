"""Authenticated rights command service against the Spanner emulator (real migrations through V016).

Covers the service boundary (credential, principal headers, scope, recent
authentication, idempotency keys), the transfer intent lifecycle (create,
replay, conflict, recipient binding, proving arguments, expiry, stale epoch),
privacy and restore barriers, reprint quotes that never consume quota, and
ownership-proof challenges.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import socket
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.cloud import spanner
from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, KeySet

from brandme_core.domains.privacy.deletion import SubjectContext
from brandme_core.domains.rights.commands import AUDIENCE_DOMAIN, terms_digest
from brandme_core.domains.rights.privacy_handler import RightsPrivacyHandler
from brandme_core.rights_commands.app import create_app, verify_schema
from brandme_core.rights_commands.config import CommandConfig

ROOT = Path(__file__).resolve().parents[1]
SENDER = "11111111-1111-4111-8111-111111111111"
RECIPIENT = "22222222-2222-4222-8222-222222222222"
STRANGER = "55555555-5555-4555-8555-555555555555"
ASSET = "33333333-3333-4333-8333-333333333333"
ENTITLEMENT = "e1" * 32
ISSUER = "15" * 32
MANUFACTURER = "4d" * 32
ALLOWANCE = "a1" * 32
CONTRACT = "ab" * 32
TOKEN = "rights-command-test-token-32-characters"
INVITE = "inv_" + "x" * 44
COMMITMENT = "c0" * 32
TABLES = ("TransferIntents", "RightsEntitlements", "LicenseGrants", "ManufacturerCapabilities", "ReprintJobs",
          "IdempotencyRecords", "OutboxEvents", "ProcessingFreezes", "RestoreRuns")


def _env(db=None, **extra):
    return {"BRANDME_MODE": "development", "ENVIRONMENT": "development",
            "SPANNER_EMULATOR_HOST": os.environ.get("SPANNER_EMULATOR_HOST", "127.0.0.1:9010"),
            "SPANNER_PROJECT_ID": "test-project", "SPANNER_INSTANCE_ID": "rights-command-tests",
            "SPANNER_DATABASE_ID": db.database_id if db else "rights-commands",
            "RIGHTS_COMMAND_NETWORK": "preprod", "RIGHTS_COMMAND_CONTRACT_ADDRESS": CONTRACT,
            "RIGHTS_COMMAND_SERVICE_TOKEN": TOKEN, **extra}


@pytest.fixture(scope="module")
def database():
    host, _, port = _env()["SPANNER_EMULATOR_HOST"].partition(":")
    try:
        socket.create_connection((host, int(port)), timeout=1).close()
    except OSError:
        pytest.skip("Spanner emulator not running")
    client = spanner.Client(project="test-project")
    inst = client.instance("rights-command-tests", configuration_name="projects/test-project/instanceConfigs/emulator-config",
                           node_count=1)
    if not inst.exists():
        inst.create().result(60)
    db = inst.database("cmd-" + uuid.uuid4().hex[:16])
    db.create().result(60)
    spec = importlib.util.spec_from_file_location("rights_command_migrations", ROOT / "brandme-data/spanner/migrations/runner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.migrate_up(db, log=lambda *_: None)
    yield db
    db.drop()


@pytest.fixture
def db(database):
    with database.batch() as batch:
        for table in TABLES:
            batch.delete(table, KeySet(all_=True))
    with database.batch() as batch:
        batch.insert("RightsEntitlements",
                     ["network", "contract_address", "entitlement_id", "asset_id", "issuer_id", "epoch", "status", "transferable",
                      "reprintable", "controller_subject_ref", "last_tx_id", "last_block_height", "finalized_at", "updated_at"],
                     [["preprod", CONTRACT, ENTITLEMENT, ASSET, ISSUER, 3, "active", True, True, SENDER, "tx-issue", 10,
                       datetime.now(timezone.utc) - timedelta(days=1), COMMIT_TIMESTAMP]])
    return database


@pytest.fixture
def client(db):
    return TestClient(create_app(db, CommandConfig.from_env(_env(db))))


def headers(subject=SENDER, scopes="rights:read rights:transfer rights:reprint", auth_age=timedelta(minutes=1), key=None):
    h = {"authorization": f"Bearer {TOKEN}", "x-subject-ref": subject, "x-principal-scopes": scopes}
    if auth_age is not None:
        h["x-auth-time"] = (datetime.now(timezone.utc) - auth_age).isoformat()
    if key:
        h["idempotency-key"] = key
    return h


def offer(**overrides):
    return {"rights_scope": ["transfer", "display"], "recipient_invite": INVITE, "expires_in_seconds": 3600, **overrides}


def create(client, key="create-key-0000001", **overrides):
    return client.post(f"/rights/assets/{ASSET}/transfers", json=offer(**overrides), headers=headers(key=key))


def accept(client, intent_id, subject=RECIPIENT, key="accept-key-0000001", **body):
    return client.post(f"/rights/transfers/{intent_id}/accept",
                       json={"recipient_invite": INVITE, "recipient_commitment": COMMITMENT, **body},
                       headers=headers(subject=subject, key=key))


def rows(db, sql):
    with db.snapshot() as snap:
        return [list(r) for r in snap.execute_sql(sql)]


def test_config_requires_a_distinct_credential_and_a_test_network(database):
    assert CommandConfig.from_env(_env(database)).network == "preprod"
    with pytest.raises(ValueError, match="distinct"):
        CommandConfig.from_env(_env(database, RIGHTS_SERVICE_TOKEN=TOKEN))
    with pytest.raises(ValueError, match="test network"):
        CommandConfig.from_env(_env(database, RIGHTS_COMMAND_NETWORK="mainnet"))
    assert "rights-command-test-token" not in repr(CommandConfig.from_env(_env(database)))


def test_boundary_checks_credential_principal_scope_and_recent_auth(client):
    path, body = f"/rights/assets/{ASSET}/transfers", offer()
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers={**headers(key="k" * 16), "authorization": "Bearer wrong"}).status_code == 401
    assert client.post(path, json=body, headers={**headers(key="k" * 16), "x-principal-scopes": "rights:transfer admin"}).status_code == 401
    assert client.post(path, json=body, headers=headers(scopes="rights:read", key="k" * 16)).json() == {"error": "forbidden"}
    stale = client.post(path, json=body, headers=headers(auth_age=timedelta(minutes=11), key="k" * 16))
    assert (stale.status_code, stale.json()) == (401, {"error": "reauth_required"})
    assert client.post(path, json=body, headers=headers(auth_age=None, key="k" * 16)).json() == {"error": "reauth_required"}
    assert client.post(path, json=body, headers=headers()).json() == {"error": "idempotency_key_required"}
    assert client.get("/health").json()["status"] == "ready"


def test_transfer_offer_is_idempotent_holds_the_entitlement_and_stores_no_invite(client, db):
    first = create(client)
    assert first.status_code == 201
    view = first.json()
    assert (view["state"], view["role"], view["expected_epoch"], view["proving"]) == ("AwaitingRecipient", "sender", "3", None)
    assert view["terms_digest"] == terms_digest(["display", "transfer"], [])
    assert INVITE not in first.text and SENDER not in first.text
    replay = create(client)
    assert replay.status_code == 201 and replay.headers["idempotent-replayed"] == "true" and replay.json() == view
    assert create(client, rights_scope=["display"]).json() == {"error": "idempotency_key_reused"}
    assert create(client, key="create-key-0000002").json() == {"error": "transfer_in_progress"}
    [[invite, nonce, contract, state]] = rows(db, "SELECT invite_digest, offer_nonce, contract_address, state FROM TransferIntents")
    assert (invite, contract, state) == (hashlib.sha256(INVITE.encode()).hexdigest(), CONTRACT, "AwaitingRecipient")
    assert re.fullmatch(r"[0-9a-f]{64}", nonce)
    events = rows(db, "SELECT event_type, actor_ref FROM OutboxEvents")
    assert events == [["ownership.transfer.requested", f"member:{SENDER}"]]
    assert INVITE not in str(rows(db, "SELECT TO_JSON_STRING(response_body), request_digest FROM IdempotencyRecords"))


def test_recipient_binding_yields_exact_proving_arguments(client, db):
    intent = create(client).json()["intent_id"]
    assert accept(client, intent, subject=STRANGER, recipient_invite="inv_" + "y" * 44).status_code == 404
    assert accept(client, intent, subject=SENDER).json() == {"error": "recipient_is_sender"}
    assert accept(client, intent, recipient_commitment="0" * 64).json() == {"error": "invalid_request"}
    bound = accept(client, intent)
    assert bound.status_code == 200
    assert (bound.json()["state"], bound.json()["role"], bound.json()["proving"]) == ("ReadyToProve", "recipient", None)
    sender = client.get(f"/rights/transfers/{intent}", headers=headers()).json()
    proving = sender["proving"]
    assert proving["circuit"] == "offerTransfer" and proving["recipient_commitment"] == COMMITMENT
    assert proving["entitlement_id"] == ENTITLEMENT and proving["terms_digest"] == sender["terms_digest"]
    assert int(proving["expiry"]) == int(datetime.fromisoformat(sender["expires_at"]).timestamp())
    assert client.get(f"/rights/transfers/{intent}", headers=headers(subject=RECIPIENT)).json()["role"] == "recipient"
    assert client.get(f"/rights/transfers/{intent}", headers=headers(subject=STRANGER)).status_code == 404
    assert accept(client, intent, key="accept-key-0000002").json() == {"error": "invalid_transition"}
    assert rows(db, "SELECT recipient_subject_ref FROM TransferIntents") == [[RECIPIENT]]


def test_expired_and_stale_intents_cannot_be_bound(client, db):
    expired = create(client).json()["intent_id"]
    with db.batch() as batch:
        batch.update("TransferIntents", ["intent_id", "expires_at"], [[expired, datetime.now(timezone.utc) - timedelta(seconds=1)]])
    assert accept(client, expired).json() == {"error": "transfer_expired"}
    assert client.get(f"/rights/transfers/{expired}", headers=headers()).json()["state"] == "Expired"
    stale = create(client, key="create-key-0000002").json()["intent_id"]  # the expired intent no longer holds it
    with db.batch() as batch:
        batch.update("RightsEntitlements", ["network", "contract_address", "entitlement_id", "epoch"], [["preprod", CONTRACT, ENTITLEMENT, 4]])
    assert accept(client, stale).json() == {"error": "stale_intent"}


def test_commands_respect_ownership_deletion_freezes_and_restores(client, db):
    other = client.post(f"/rights/assets/{ASSET}/transfers", json=offer(), headers=headers(subject=STRANGER, key="create-key-0000001"))
    assert other.status_code == 404
    with db.batch() as batch:
        batch.update("RightsEntitlements", ["network", "contract_address", "entitlement_id", "transferable"], [["preprod", CONTRACT, ENTITLEMENT, False]])
    assert create(client).json() == {"error": "not_transferable"}
    with db.batch() as batch:
        batch.update("RightsEntitlements", ["network", "contract_address", "entitlement_id", "transferable"], [["preprod", CONTRACT, ENTITLEMENT, True]])
        batch.insert("ProcessingFreezes", ["subject_ref", "category", "reason", "deletion_job_id", "created_at"],
                     [[SENDER, "*", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP]])
    assert create(client).json() == {"error": "processing_frozen"}
    with db.batch() as batch:
        batch.delete("ProcessingFreezes", KeySet(all_=True))
        batch.insert("RestoreRuns", ["restore_id", "backup_ref", "backup_taken_at", "state", "started_at"],
                     [["r1", "gs://backups/old", datetime.now(timezone.utc) - timedelta(days=1), "restoring", datetime.now(timezone.utc)]])
    assert create(client).json() == {"error": "restore_in_progress"}
    assert client.get("/health").status_code == 503
    assert rows(db, "SELECT COUNT(*) FROM TransferIntents") == [[0]]


def test_a_frozen_sender_is_not_disclosed_to_the_recipient(client, db):
    intent = create(client).json()["intent_id"]
    with db.batch() as batch:
        batch.insert("ProcessingFreezes", ["subject_ref", "category", "reason", "deletion_job_id", "created_at"],
                     [[SENDER, "*", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP]])
    assert accept(client, intent).json() == {"error": "invalid_transition"}
    assert rows(db, "SELECT state, recipient_subject_ref FROM TransferIntents") == [["AwaitingRecipient", None]]


def test_recipient_deletion_cancels_an_unproven_offer(client, db):
    intent = create(client).json()["intent_id"]
    accept(client, intent)
    handler = RightsPrivacyHandler()
    ctx = SubjectContext(RECIPIENT, str(uuid.uuid4()), datetime.now(timezone.utc))
    with db.snapshot() as snap:
        assert handler.export(snap, ctx, "rights.transfers").records[0]["role"] == "recipient"
    assert db.run_in_transaction(lambda txn: handler.delete(txn, ctx, "rights.transfers")).rows_affected == 1
    assert rows(db, "SELECT state, recipient_subject_ref, recipient_commitment FROM TransferIntents") == [["Cancelled", None, None]]


def _license(db, quota=5, territory=("US",), used=2):
    with db.batch() as batch:
        batch.insert("LicenseGrants", ["license_id", "network", "entitlement_id", "issuer_id", "permissions", "territory",
                                       "allowance_id", "quota_granted", "created_at"],
                     [[str(uuid.uuid4()), "preprod", ENTITLEMENT, ISSUER, ["personal_manufacture"], list(territory), ALLOWANCE,
                       quota, datetime.now(timezone.utc)]])
        batch.insert("ManufacturerCapabilities", ["manufacturer_id", "issuer_id", "display_name", "processes", "territories",
                                                  "active", "updated_at"],
                     [[MANUFACTURER, ISSUER, "Atelier", ["knit"], ["US"], True, COMMIT_TIMESTAMP]])
        if used:
            batch.insert("ReprintJobs", ["job_id", "network", "allowance_id", "entitlement_id", "manufacturer_id",
                                         "member_subject_ref", "job_commitment", "quantity", "state", "version", "created_at",
                                         "updated_at"],
                         [[str(uuid.uuid4()), "preprod", ALLOWANCE, ENTITLEMENT, MANUFACTURER, SENDER, "77" * 32, used,
                           "approved", 1, datetime.now(timezone.utc), COMMIT_TIMESTAMP]])


def quote(client, subject=SENDER, **body):
    return client.post(f"/rights/assets/{ASSET}/reprint-quotes",
                       json={"quantity": 3, "manufacturer_id": MANUFACTURER, "territory": "US", **body},
                       headers=headers(subject=subject))


def test_reprint_quote_reports_missing_conditions_and_never_consumes_quota(client, db):
    assert quote(client).json()["missing"] == ["license_missing"]
    _license(db)
    ok = quote(client).json()
    assert (ok["eligible"], ok["quota_remaining"], ok["price"], ok["price_status"]) == (True, "3", None, "unavailable")
    assert quote(client, quantity=4).json()["missing"] == ["quota_exceeded"]
    assert quote(client, territory="FR").json()["missing"] == ["territory_not_licensed", "manufacturer_not_capable"]
    assert quote(client, subject=STRANGER).status_code == 404
    assert quote(client, colour="red").json() == {"error": "invalid_request"}  # unknown field
    assert rows(db, "SELECT COUNT(*), SUM(quantity) FROM ReprintJobs") == [[1, 2]]
    assert rows(db, "SELECT COUNT(*) FROM IdempotencyRecords") == [[0]]


def test_challenge_binds_entitlement_epoch_and_audience_without_storing_anything(client, db):
    body = {"entitlement_id": ENTITLEMENT, "audience": "resale-partner", "challenge": "9" * 64, "ttl_seconds": 300}
    ok = client.post("/rights/challenges", json=body, headers=headers(scopes="rights:read"))
    assert ok.status_code == 201
    assert ok.json()["audience_digest"] == hashlib.sha256(AUDIENCE_DOMAIN + b"resale-partner").hexdigest()
    assert ok.json()["expected_epoch"] == "3"
    assert client.post("/rights/challenges", json=body, headers=headers(subject=STRANGER, scopes="rights:read")).status_code == 404
    assert client.post("/rights/challenges", json={**body, "challenge": "zz"}, headers=headers(scopes="rights:read")).status_code == 400
    assert rows(db, "SELECT COUNT(*) FROM OutboxEvents") == [[0]]


def test_schema_check_requires_v016(database):
    verify_schema(database)
