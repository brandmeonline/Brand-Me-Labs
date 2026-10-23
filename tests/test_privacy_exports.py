"""Real Spanner transactions + HTTP object-store contract + private API."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from google.cloud import spanner

from brandme_core.privacy_exports.app import create_app
from brandme_core.privacy_exports.config import ExportConfig
from brandme_core.privacy_exports.service import CATEGORIES, ExportService, verify_schema
from brandme_core.privacy_exports.storage import MAX_PACKAGE, PrivateStore, StorageError
from brandme_core.read_api.reads import ReadError
from tests.fixtures.export_storage import BUCKET, storage_server
from tests.test_read_api import database, _entitlement, MEMBER, OTHER, CONTRACT, _deletion, _contract

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "export-service-test-token-32-characters"
PAST = datetime.now(timezone.utc) - timedelta(days=2)


def now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def db(database):
    with database.batch() as b:
        for table in ("PrivacyExportJobs", "PrivacyExportRequests", "PrivacyExportObjects", "RightsEntitlements", "ChainOperationSubjects", "ChainOperations",
                      "ReprintJobs", "TransferIntents", "DeletionJobs", "ProcessingFreezes", "DeletionTombstones", "RestoreRuns"):
            b.delete(table, spanner.KeySet(all_=True))
    return database


@pytest.fixture
def setup(db):
    with storage_server() as (host, state):
        config = ExportConfig("development", "test-project", "read-api-tests", db.database_id, "preprod", CONTRACT, BUCKET, TOKEN, host)
        store = PrivateStore(config)
        with TestClient(create_app(db, config, store)) as client:
            yield ExportService(db, config, store), client, state, config
        store.close()


def headers(subject=MEMBER, **extra):
    return {"authorization": f"Bearer {TOKEN}", "x-subject-ref": subject, **extra}


def request(service, categories=None, key=None, subject=MEMBER):
    return service.request(subject, categories or ["rights.control_links"], key or uuid.uuid4().hex, now())


def change(db, job_id, **values):
    with db.batch() as b:
        b.update("PrivacyExportJobs", columns=("environment", "job_id", *values), values=[("development", job_id, *values.values())])


def due(db):
    db.run_in_transaction(lambda tx: tx.execute_update("UPDATE PrivacyExportObjects SET cleanup_at = TIMESTAMP '2000-01-01T00:00:00Z' WHERE TRUE"))


def freeze(db, category="rights.control_links"):
    with db.batch() as b:
        b.insert("ProcessingFreezes", columns=("subject_ref", "category", "reason", "created_at"), values=[(MEMBER, category, "restriction", datetime.now(timezone.utc))])


def test_actual_migration_ready_and_end_to_end_selected_export(db, setup):
    service, client, state, _ = setup
    verify_schema(db)
    _entitlement(db)
    _entitlement(db, 2, subject=OTHER)
    _entitlement(db, 3, network="preview")
    _entitlement(db, 4, contract="ef" * 32)
    r = client.post("/exports", json={"categories": list(CATEGORIES), "reauth_at": now()}, headers=headers(**{"idempotency-key": uuid.uuid4().hex}))
    assert r.status_code == 202, r.text
    job = r.json()
    _contract("SelectedRightsExportStatus", job)
    assert job["coverage"]["full_account"] is False and not job["download_available"]
    assert service.run_once() == "ready"
    status = client.get(f'/exports/{job["job_id"]}', headers=headers())
    assert status.status_code == 200 and status.json()["download_available"]
    _contract("SelectedRightsExportStatus", status.json())
    for secret in ("subject_ref", "attempt_id", "object_generation", "package_ref", "lease_until"):
        assert secret not in status.json()
    r = client.get(f'/exports/{job["job_id"]}/download', headers=headers(**{"x-reauth-at": now()}))
    assert r.status_code == 200, r.text
    assert hashlib.sha256(r.content).hexdigest() == r.headers["x-export-sha256"] == status.json()["package_sha256"]
    package = r.json()
    _contract("SelectedRightsExportPackage", package)
    controls = next(s for s in package["sections"] if s["category"] == "rights.control_links")
    assert [r["entitlement_id"] for r in controls["records"]] == [f"{1:064x}"]
    assert controls["records"][0]["epoch"] == "9007199254740993"
    assert package["coverage"]["selected_categories_only"] is True
    assert "private, no-store" in r.headers["cache-control"] and "attachment;" in r.headers["content-disposition"]
    assert len(state.objects) == 1
    assert next(iter(state.objects.values()))[2]["cacheControl"] == "private, no-store"
    assert client.get(f'/exports/{job["job_id"]}', headers=headers(OTHER)).status_code == 404
    assert client.get(f'/exports/{job["job_id"]}/download', headers=headers(OTHER, **{"x-reauth-at": now()})).status_code == 404


def test_idempotency_replays_exact_result_conflicts_and_serializes(db, setup):
    service, _, _, _ = setup
    key = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: request(service, key=key), range(4)))
    assert len({j["job_id"] for j in jobs}) == 1
    with pytest.raises(ReadError, match="idempotency_conflict"):
        request(service, ["rights.operations"], key)
    assert request(service, key=key, subject=OTHER)["job_id"] != jobs[0]["job_id"]
    request(service)
    with pytest.raises(ReadError, match="export_limit_reached"):
        request(service)


@pytest.mark.parametrize("body", [{}, {"categories": []}, {"categories": ["persona.profile"]},
    {"categories": ["rights.control_links"] * 2}, {"categories": ["rights.control_links"], "subject_ref": OTHER}])
def test_explicit_supported_categories_only(setup, body):
    _, client, _, _ = setup
    assert client.post("/exports", json={**body, "reauth_at": now()}, headers=headers(**{"idempotency-key": uuid.uuid4().hex})).status_code == 400


def test_service_auth_reauth_closed_input_and_size_bounds(setup):
    _, client, _, _ = setup
    assert client.get("/capability").status_code == 401
    assert client.get("/capability", headers=headers(), params={"subject": OTHER}).status_code == 400
    body = {"categories": ["rights.control_links"], "reauth_at": now()}
    assert client.post("/exports", json=body, headers=headers()).status_code == 400
    assert client.post("/exports", content=b"x" * 4097, headers=headers()).status_code == 413
    h = headers(**{"idempotency-key": uuid.uuid4().hex})
    for date in (PAST.isoformat(), "2026-10-23", "invalid", (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()):
        assert client.post("/exports", json={**body, "reauth_at": date}, headers=h).status_code == 401
    duplicate = list(h.items()) + [("x-subject-ref", OTHER)]
    assert client.post("/exports", json=body, headers=duplicate).status_code in (400, 401)
    assert client.post("/exports", content='{"categories":[],"categories":["rights.control_links"],"reauth_at":"x"}', headers=h).status_code == 400


def test_stale_worker_cannot_finalize_and_cleanup_preserves_winner(db, setup):
    service, _, state, _ = setup
    job = request(service)
    first = service.claim()
    first_content = service.build(first)
    change(db, job["job_id"], lease_until=PAST, next_attempt_at=PAST)
    second = service.claim()
    second_content = service.build(second)
    first_gen = service.store.put(service.store.key(job["job_id"], first["attempt_id"]), first_content)
    second_key = service.store.key(job["job_id"], second["attempt_id"])
    second_gen = service.store.put(second_key, second_content)
    with pytest.raises(ReadError, match="export_lease_lost"):
        service.finish(first, first_gen, first_content)
    service.finish(second, second_gen, second_content)
    due(db)
    service.sweep()
    assert set(state.objects) == {second_key}
    assert service.download(MEMBER, job["job_id"], now())[0] == second_content


def test_lost_upload_ack_has_durable_cleanup_and_retry(db, setup):
    service, _, state, _ = setup
    job = request(service)
    state.lose_upload_ack = True
    assert service.run_once() == "retry_or_failed" and len(state.objects) == 1
    state.lose_upload_ack = False
    change(db, job["job_id"], next_attempt_at=PAST)
    assert service.run_once() == "ready" and len(state.objects) == 2
    due(db)
    service.sweep()
    assert len(state.objects) == 1


def test_lost_final_commit_ack_does_not_delete_ready_object(db, setup, monkeypatch):
    service, _, state, _ = setup
    job = request(service)
    finish = service.finish
    def lost(*args):
        finish(*args)
        raise RuntimeError("untrusted provider text")
    monkeypatch.setattr(service, "finish", lost)
    assert service.run_once() == "retry_or_failed"
    assert service.status(MEMBER, job["job_id"])["state"] == "ready"
    due(db)
    service.sweep()
    assert len(state.objects) == 1


def test_expiry_denies_download_and_failed_delete_is_retried(db, setup):
    service, _, state, _ = setup
    job = request(service)
    service.run_once()
    change(db, job["job_id"], expires_at=PAST)
    assert service.status(MEMBER, job["job_id"])["state"] == "expired"
    with pytest.raises(ReadError, match="export_expired"):
        service.download(MEMBER, job["job_id"], now())
    state.delete_failure = True
    due(db)
    service.sweep()
    assert len(state.objects) == 1
    state.delete_failure = False
    due(db)
    service.sweep()
    assert not state.objects
    # A process paused before upload may resume arbitrarily late. Its permanent
    # cleanup row survives a previous successful delete and finds it again.
    with db.snapshot() as s:
        attempt = list(s.execute_sql("SELECT job_id, attempt_id FROM PrivacyExportObjects"))[0]
    service.store.put(service.store.key(*attempt), b'{"late":true}')
    due(db)
    service.sweep()
    assert not state.objects


@pytest.mark.parametrize("phase", ["request", "build", "finalize", "download"])
def test_privacy_freeze_blocks_every_release_phase(db, setup, phase):
    service, _, state, _ = setup
    if phase == "request":
        freeze(db)
        with pytest.raises(ReadError, match="export_restricted"):
            request(service)
        return
    job = request(service)
    if phase == "download":
        service.run_once()
        freeze(db)
        with pytest.raises(ReadError, match="export_restricted"):
            service.download(MEMBER, job["job_id"], now())
        due(db)
        service.sweep()
        assert not state.objects
        return
    claimed = service.claim()
    content = service.build(claimed)
    freeze(db)
    with pytest.raises(ReadError, match="export_restricted"):
        if phase == "build":
            service.build(claimed)
        else:
            service.finish(claimed, "1", content)


def test_delete_during_download_is_checked_after_external_io(db, setup, monkeypatch):
    service, _, _, _ = setup
    job = request(service)
    service.run_once()
    get = service.store.get
    def concurrent(*args):
        data = get(*args)
        _deletion(db)
        return data
    monkeypatch.setattr(service.store, "get", concurrent)
    with pytest.raises(ReadError, match="export_restricted"):
        service.download(MEMBER, job["job_id"], now())


def test_new_tombstone_and_restore_barriers_cannot_resurrect_download(db, setup):
    service, client, _, _ = setup
    job = request(service)
    service.run_once()
    with db.batch() as b:
        b.insert("DeletionTombstones", columns=("subject_ref", "category", "tombstone_id", "deletion_job_id", "created_at"),
                 values=[(MEMBER, "rights.control_links", str(uuid.uuid4()), str(uuid.uuid4()), datetime.now(timezone.utc))])
    with pytest.raises(ReadError, match="export_restricted"):
        service.download(MEMBER, job["job_id"], now())
    with db.batch() as b:
        b.insert("RestoreRuns", columns=("restore_id", "backup_ref", "backup_taken_at", "state", "started_at"),
                 values=[(str(uuid.uuid4()), "backup", PAST, "restoring", PAST)])
    assert client.get("/health").status_code == 503
    assert client.get(f'/exports/{job["job_id"]}', headers=headers()).status_code == 503
    with pytest.raises(ReadError, match="restore_incomplete"):
        service.claim()


def test_oversized_export_fails_without_truncation_or_upload(db, setup, monkeypatch):
    service, _, state, _ = setup
    for i in (1, 2):
        _entitlement(db, i)
    monkeypatch.setattr("brandme_core.privacy_exports.service.MAX_ROWS", 1)
    job = request(service)
    assert service.run_once() == "retry_or_failed"
    assert service.status(MEMBER, job["job_id"])["failure_code"] == "export_too_large"
    assert not state.objects


def test_corrupt_bytes_never_released(setup):
    service, client, state, _ = setup
    job = request(service)
    service.run_once()
    key, (gen, data, meta) = next(iter(state.objects.items()))
    state.objects[key] = (gen, b"x" * len(data), meta)
    r = client.get(f'/exports/{job["job_id"]}/download', headers=headers(**{"x-reauth-at": now()}))
    assert r.status_code == 503 and "must-not-leak" not in r.text


@pytest.mark.parametrize("policy", [{"versioning": {"enabled": True}}, {"softDeletePolicy": {"retentionDurationSeconds": "604800"}},
    {"iamConfiguration": {"publicAccessPrevention": "inherited"}}, {"retentionPolicy": {"retentionPeriod": "3600"}},
    {"defaultEventBasedHold": True}, {"lifecycle": {"rule": []}}, {"objectRetention": {"mode": "Enabled"}}])
def test_storage_refuses_public_retained_or_unmanaged_buckets(setup, policy):
    service, client, state, _ = setup
    state.policy.update(policy)
    with pytest.raises(StorageError):
        service.store.check()
    assert client.get("/health").status_code == 503


def test_generation_preconditions_and_storage_bounds(setup):
    service, _, state, _ = setup
    key = service.store.key(str(uuid.uuid4()), str(uuid.uuid4()))
    generation = service.store.put(key, b'{}')
    with pytest.raises(StorageError):
        service.store.put(key, b'{}')
    with pytest.raises(StorageError):
        service.store.get(key, str(int(generation) + 1))
    with pytest.raises(StorageError):
        service.store.put(key, b'x' * (MAX_PACKAGE + 1))
    with pytest.raises(StorageError):
        service.store.get('https://other.example/secrets', generation)
    service.store.delete(key)
    assert not state.objects
    assert any(method == "DELETE" and query == {"ifGenerationMatch": [generation]} for method, _, query in state.calls)


def test_scope_and_allowlisted_columns_cover_operations_transfers_reprints(db, setup):
    from tests.test_rights import _stored_operation
    from brandme_core.domains.rights.reprint import ReprintService
    service, _, _, config = setup
    operation = _stored_operation(db, MEMBER, "Finalized")
    _stored_operation(db, OTHER, "Finalized")
    wrong_env = _stored_operation(db, MEMBER, "Finalized")
    wrong_contract = _stored_operation(db, MEMBER, "Finalized")
    with db.batch() as b:
        b.update("ChainOperations", columns=("operation_id", "args_json"), values=[(operation, json.dumps({"private_key": "never-export-this"}))])
        b.update("ChainOperations", columns=("operation_id", "environment"), values=[(wrong_env, "sandbox")])
        b.update("ChainOperations", columns=("operation_id", "contract_address"), values=[(wrong_contract, "ef" * 32)])
    jid = ReprintService(db).create(network="preprod", allowance_id="aa" * 32, entitlement_id="bb" * 32,
                                 manufacturer_id="cc" * 32, member_subject_ref=MEMBER, quantity=9007199254740993, job_commitment="dd" * 32)
    intent = str(uuid.uuid4())
    with db.batch() as b:
        b.insert("TransferIntents", columns=("intent_id", "network", "entitlement_id", "from_subject_ref", "rights_scope_json",
                 "expected_epoch", "state", "expires_at", "created_at", "updated_at"),
                 values=[(intent, "preprod", "aa" * 32, MEMBER, json.dumps({"internal_token": "never-export-this"}), 1,
                          "offered", datetime.now(timezone.utc) + timedelta(hours=1), PAST, PAST)])
    job = request(service, list(CATEGORIES))
    assert service.run_once() == "ready"
    data, _ = service.download(MEMBER, job["job_id"], now())
    assert b"never-export-this" not in data and b"args_json" not in data
    package = json.loads(data)
    _contract("SelectedRightsExportPackage", package)
    sections = {s["category"]: s for s in package["sections"]}
    assert [r["operation_id"] for r in sections["rights.operations"]["records"]] == [operation]
    assert sections["rights.transfers"]["records"][0]["intent_id"] == intent
    assert sections["rights.reprint_jobs"]["records"][0]["job_id"] == jid
    assert sections["rights.reprint_jobs"]["records"][0]["quantity"] == "9007199254740993"
    assert sections["rights.transfers"]["scope"]["contract_address"] is None
    assert sections["rights.reprint_jobs"]["scope"]["contract_address"] is None
    with pytest.raises(ReadError, match="not_found"):
        ExportService(db, replace(config, network="preview"), service.store).status(MEMBER, job["job_id"])


def test_claim_is_exclusive_and_crashed_attempts_are_bounded(db, setup):
    service, _, _, _ = setup
    job = request(service)
    with ThreadPoolExecutor(max_workers=3) as pool:
        claims = list(pool.map(lambda _: service.claim(), range(3)))
    assert sum(c is not None for c in claims) == 1
    for _ in range(2):
        change(db, job["job_id"], lease_until=PAST, next_attempt_at=PAST)
        assert service.claim() is not None
    change(db, job["job_id"], lease_until=PAST, next_attempt_at=PAST)
    assert service.claim() is None
    assert service.status(MEMBER, job["job_id"])["failure_code"] == "attempts_exhausted"


def test_storage_redirects_provider_errors_and_oversized_reads_fail_closed(setup):
    service, client, state, _ = setup
    for override in ((302, b"", {"Location": "http://127.0.0.1:1/credential-leak"}), (503, b"private-provider-secret", {})):
        state.override = override
        count = len(state.calls)
        r = client.get("/health")
        assert r.status_code == 503 and "private-provider-secret" not in r.text
        assert len(state.calls) == count + 1
    state.override = None
    key = service.store.key(str(uuid.uuid4()), str(uuid.uuid4()))
    state.objects[key] = ("1", b"x" * (MAX_PACKAGE + 1), {})
    with pytest.raises(StorageError):
        service.store.get(key, "1")


def test_total_package_bound_is_not_a_truncated_success(db, setup, monkeypatch):
    service, _, state, _ = setup
    monkeypatch.setattr("brandme_core.privacy_exports.service.MAX_PACKAGE", 128)
    job = request(service)
    assert service.run_once() == "retry_or_failed"
    assert service.status(MEMBER, job["job_id"])["failure_code"] == "export_too_large"
    assert not state.objects


def test_adc_refresh_transport_also_disables_proxies_netrc_and_redirects(monkeypatch):
    from google.auth.credentials import AnonymousCredentials
    import google.auth
    import requests
    monkeypatch.setattr(google.auth, "default", lambda **_kwargs: (AnonymousCredentials(), "test-project"))
    config = ExportConfig("sandbox", "test-project", "test", "test", "preprod", CONTRACT, "brandme-sandbox-exports-test", TOKEN)
    store = PrivateStore(config)
    try:
        assert store.session.trust_env is False and store.auth_session.trust_env is False
        calls = []
        def capture(_session, *args, **kwargs):
            calls.append((args, kwargs))
            return object()
        monkeypatch.setattr(requests.Session, "request", capture)
        store.auth_session.request("POST", "https://oauth2.googleapis.com/token", allow_redirects=True)
        assert calls[0][1]["allow_redirects"] is False
    finally:
        store.close()


def test_config_and_actual_cli_worker_api(db, setup):
    service, _, _, config = setup
    env = {**os.environ, "BRANDME_MODE": "development", "ENVIRONMENT": "development", "SPANNER_PROJECT_ID": config.project,
           "SPANNER_INSTANCE_ID": config.instance, "SPANNER_DATABASE_ID": config.database, "EXPORT_NETWORK": "preprod",
           "EXPORT_CONTRACT_ADDRESS": CONTRACT, "EXPORT_BUCKET": BUCKET, "PRIVACY_EXPORT_SERVICE_TOKEN": TOKEN,
           "EXPORT_STORAGE_EMULATOR_HOST": config.storage_emulator, "PYTHONPATH": str(ROOT)}
    assert TOKEN not in repr(ExportConfig.from_env(env))
    for changes in ({"EXPORT_NETWORK": "mainnet"}, {"ENVIRONMENT": "production"}, {"PRIVACY_EXPORT_SERVICE_TOKEN": "short"},
                    {"EXPORT_BUCKET": "public-bucket"}, {"EXPORT_STORAGE_EMULATOR_HOST": ""}, {"PRIVACY_SERVICE_TOKEN": TOKEN}):
        with pytest.raises(ValueError):
            ExportConfig.from_env({**env, **changes})
    with pytest.raises(ValueError):
        PrivateStore(replace(config, storage_emulator="evil.example:8080"))
    job = request(service)
    for args in (["--check"], ["--worker", "--once"]):
        result = subprocess.run([sys.executable, "-m", "brandme_core.privacy_exports", *args], env=env, cwd=ROOT, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert TOKEN.encode() not in result.stdout + result.stderr
    assert service.status(MEMBER, job["job_id"])["state"] == "ready"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    p = subprocess.Popen([sys.executable, "-m", "brandme_core.privacy_exports"], env={**env, "PORT": str(port)}, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=1) as http:
            for _ in range(100):
                try:
                    if http.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            r = http.get(f'/exports/{job["job_id"]}/download', headers=headers(**{"x-reauth-at": now()}))
            assert r.status_code == 200
    finally:
        p.terminate()
        out, err = p.communicate(timeout=10)
    assert TOKEN.encode() not in out + err and MEMBER.encode() not in out + err
