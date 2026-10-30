"""Real Spanner + HTTP tests for the runnable rights/My Data read boundary."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from google.cloud import spanner
from jsonschema import Draft202012Validator, FormatChecker

from brandme_core.read_api.app import create_app
from brandme_core.read_api.config import ReadConfig
from brandme_core.read_api.reads import BoundedSnapshot, JSON_LIMIT, ReadError, verify_schema

ROOT = Path(__file__).resolve().parents[1]
MEMBER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
ASSET = "33333333-3333-4333-8333-333333333333"
JOB = "44444444-4444-4444-8444-444444444444"
RIGHTS = "rights-test-service-token-32-characters"
PRIVACY = "privacy-test-service-token-32-characters"
CONTRACT = "ab" * 32
NOW = datetime.now(timezone.utc) - timedelta(days=1)


def _contract(name, value):
    schemas = json.loads((ROOT / "packages/contracts/src/read-schemas.json").read_text())
    Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": {"schemas": schemas}},
                         format_checker=FormatChecker()).validate(value)


def _env(db=None):
    return {"BRANDME_MODE": "development", "ENVIRONMENT": "development",
            "SPANNER_EMULATOR_HOST": os.environ.get("SPANNER_EMULATOR_HOST", "127.0.0.1:9010"),
            "SPANNER_PROJECT_ID": "test-project", "SPANNER_INSTANCE_ID": "read-api-tests",
            "SPANNER_DATABASE_ID": db.database_id if db else "read-api",
            "READ_API_NETWORK": "preprod", "READ_API_CONTRACT_ADDRESS": CONTRACT,
            "RIGHTS_SERVICE_TOKEN": RIGHTS, "PRIVACY_SERVICE_TOKEN": PRIVACY}


@pytest.fixture(scope="module")
def database():
    host, _, port = _env()["SPANNER_EMULATOR_HOST"].partition(":")
    try:
        socket.create_connection((host, int(port)), timeout=1).close()
    except OSError:
        pytest.skip("Spanner emulator not running")
    client = spanner.Client(project="test-project")
    inst = client.instance("read-api-tests", configuration_name="projects/test-project/instanceConfigs/emulator-config", node_count=1)
    if not inst.exists():
        inst.create().result(60)
    db = inst.database("read-" + uuid.uuid4().hex[:16])
    db.create().result(60)
    spec = importlib.util.spec_from_file_location("read_api_migrations", ROOT / "brandme-data/spanner/migrations/runner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.migrate_up(db, log=lambda *_: None)
    yield db
    db.drop()


@pytest.fixture
def db(database):
    with database.batch() as batch:
        for table in ("PassportClaims", "RightsEntitlements", "ReprintJobs", "DeletionJobs", "ProcessingFreezes", "DeletionTombstones", "RestoreRuns"):
            batch.delete(table, spanner.KeySet(all_=True))
    return database


@pytest.fixture
def client(db):
    with TestClient(create_app(db, ReadConfig.from_env(_env(db)))) as c:
        yield c


def _headers(subject=MEMBER, token=RIGHTS):
    return {"Authorization": f"Bearer {token}", **({"X-Subject-Ref": subject} if subject else {})}


def _entitlement(db, eid=1, *, subject=MEMBER, network="preprod", contract=CONTRACT, asset=ASSET, status="active"):
    with db.batch() as batch:
        batch.insert("RightsEntitlements", columns=("network", "contract_address", "entitlement_id", "asset_id", "issuer_id",
                     "epoch", "status", "transferable", "reprintable", "controller_subject_ref", "last_tx_id", "last_block_height",
                     "finalized_at", "updated_at", "projection_version"),
                     values=[(network, contract, f"{eid:064x}", asset, "cd" * 32, 9007199254740993, status, True, True,
                              subject, "tx-public", 9007199254740994, NOW, NOW, 1)])


def _claim(db, *, visibility="public", environment="development", network="preprod", value=None, expires=None, revoked=None):
    cid = str(uuid.uuid4())
    with db.batch() as batch:
        batch.insert("PassportClaims", columns=("asset_id", "claim_id", "facet", "claim_type", "assurance", "source", "environment",
                     "network", "evidence_ref", "visibility", "value_json", "observed_at", "expires_at", "revoked_at"),
                     values=[(ASSET, cid, "ownership", "entitlement_controlled", "midnight_control_proof", "issuer",
                              environment, network, "tx:public", visibility, json.dumps(value), NOW, expires, revoked)])
    return cid


def _deletion(db, *, subject=MEMBER, state="requested", scope="category", receipt=None):
    with db.batch() as batch:
        batch.insert("DeletionJobs", columns=("job_id", "subject_ref", "scope", "categories", "state", "reauth_at",
                     "requested_at", "completed_at", "receipt_json", "version"),
                     values=[(JOB, subject, scope, ["rights.control_links"], state, NOW, NOW,
                              NOW if state.startswith("completed") else None, json.dumps(receipt) if receipt else None, 1)])


@pytest.mark.parametrize("changes", [
    {"RIGHTS_SERVICE_TOKEN": "short"}, {"PRIVACY_SERVICE_TOKEN": RIGHTS}, {"PRIVACY_SERVICE_TOKEN": ""},
    {"RIGHTS_SERVICE_TOKEN": "x" * 31 + "\n"}, {"READ_API_NETWORK": "mainnet"}, {"READ_API_CONTRACT_ADDRESS": ""},
    {"BRANDME_MODE": "sandbox", "ENVIRONMENT": "sandbox"}, {"ENVIRONMENT": "production"},
    {"SPANNER_EMULATOR_HOST": ""}, {"SPANNER_PROJECT_ID": ""}, {"PORT": "65536"},
])
def test_unsafe_configuration_refused(changes):
    with pytest.raises(ValueError):
        ReadConfig.from_env({**_env(), **changes})


def test_credentials_are_not_represented_and_strict_mode_uses_real_spanner():
    config = ReadConfig.from_env({**_env(), "BRANDME_MODE": "sandbox", "ENVIRONMENT": "sandbox", "SPANNER_EMULATOR_HOST": ""})
    assert RIGHTS not in repr(config) and PRIVACY not in repr(config)


@pytest.mark.parametrize("path", ["/rights/entitlements", f"/rights/assets/{ASSET}/passport", "/privacy/inventory", f"/privacy/deletion/{JOB}"])
def test_service_authentication_cannot_be_replaced_with_subject(client, path):
    for headers in ({}, {"X-Subject-Ref": MEMBER}, _headers(token="wrong")):
        r = client.get(path, headers=headers)
        assert r.status_code == 401 and r.headers["cache-control"] == "no-store"


def test_credentials_subjects_and_duplicate_headers_fail_closed(client):
    assert client.get("/privacy/inventory", headers=_headers()).status_code == 401
    assert client.get("/rights/entitlements", headers=_headers(token=PRIVACY)).status_code == 401
    assert client.get("/privacy/inventory", headers=_headers(None, PRIVACY)).status_code == 401
    assert client.get("/privacy/inventory", headers=_headers("victim", PRIVACY)).status_code == 400
    for extra in [("authorization", f"Bearer {RIGHTS}"), ("x-subject-ref", OTHER)]:
        headers = list(_headers().items()) + [extra]
        assert client.get("/rights/entitlements", headers=headers).status_code in (400, 401)


def test_entitlements_are_scoped_and_pagination_is_lossless(db, client):
    for eid in (1, 2, 3):
        _entitlement(db, eid)
    _entitlement(db, 4, subject=OTHER)
    _entitlement(db, 5, network="preview")
    _entitlement(db, 6, contract="ef" * 32)
    page1 = client.get("/rights/entitlements?limit=2", headers=_headers()).json()
    _contract("RightsEntitlementsRead", page1)
    assert page1["network"] == "preprod" and page1["contract_address"] == CONTRACT
    assert [i["entitlement_id"] for i in page1["items"]] == [f"{i:064x}" for i in (1, 2)]
    assert page1["items"][0]["epoch"] == "9007199254740993"
    page2 = client.get(f'/rights/entitlements?limit=2&cursor={page1["next_cursor"]}', headers=_headers()).json()
    assert [i["entitlement_id"] for i in page2["items"]] == [f"{3:064x}"] and page2["next_cursor"] is None
    assert "controller_subject_ref" not in str(page1)


@pytest.mark.parametrize("query", ["limit=101", "limit=0", "limit=-1", "limit=1e2", "limit=1&limit=2", "cursor='OR 1=1", "viewer=owner", "subject_ref=victim"])
def test_pagination_input_cannot_override_access(client, query):
    assert client.get(f"/rights/assets/{ASSET}/passport?{query}", headers=_headers()).status_code == 400
    assert client.get(f"/rights/entitlements?{query}", headers=_headers()).status_code == 400


def test_passport_uses_verified_relation_environment_and_claim_visibility(db, client):
    _entitlement(db)
    public = _claim(db, value={"kind": "public"})
    owner = _claim(db, visibility="owner", value={"kind": "owner"})
    _claim(db, visibility="private", value={"secret": "supplier-only"})
    _claim(db, environment="production", value={"secret": "other-environment"})
    _claim(db, network="preview", value={"secret": "other-network"})
    _claim(db, visibility="owner", network=None, value={"secret": "unbound-owner"})
    path = f"/rights/assets/{ASSET}/passport"
    for subject in (None, OTHER):
        r = client.get(path, headers=_headers(subject))
        assert r.status_code == 200
        _contract("PassportClaimsRead", r.json())
        assert r.json()["viewer"] == "public" and [s["claim_id"] for s in r.json()["statements"]] == [public]
    r = client.get(path + "?limit=1", headers=_headers()).json()
    assert r["viewer"] == "owner" and r["next_cursor"]
    r2 = client.get(path + f'?cursor={r["next_cursor"]}&limit=1', headers=_headers()).json()
    assert {s["claim_id"] for s in r["statements"] + r2["statements"]} == {public, owner}
    assert "supplier-only" not in str(r) + str(r2) and r2["next_cursor"] is None


@pytest.mark.parametrize("barrier", ["restriction", "deletion", "account_completed", "tombstone", "ambiguous_contract", "revoked"])
def test_owner_visibility_cannot_outlive_barriers_or_ambiguous_control(db, client, barrier):
    _entitlement(db, status="revoked" if barrier == "revoked" else "active")
    _claim(db, visibility="owner", value={"secret": "owner-only"})
    if barrier == "ambiguous_contract":
        _entitlement(db, 2, contract="ef" * 32, subject=OTHER)
    elif barrier == "deletion":
        _deletion(db, state="failed")
    elif barrier == "account_completed":
        _deletion(db, state="completed", scope="account")
    elif barrier == "restriction":
        with db.batch() as b:
            b.insert("ProcessingFreezes", ["subject_ref", "category", "reason", "created_at"], [[MEMBER, "*", "restriction", NOW]])
    elif barrier == "tombstone":
        with db.batch() as b:
            b.insert("DeletionTombstones", ["subject_ref", "category", "tombstone_id", "deletion_job_id", "created_at"],
                     [[MEMBER, "rights.control_links", str(uuid.uuid4()), JOB, NOW + timedelta(seconds=1)]])
    r = client.get(f"/rights/assets/{ASSET}/passport", headers=_headers())
    assert r.status_code == 200 and r.json()["viewer"] == "public" and r.json()["statements"] == []


def test_passport_preserves_expired_revoked_and_network_meaning(db, client):
    _claim(db, expires=NOW - timedelta(seconds=1))
    _claim(db, revoked=NOW, expires=NOW - timedelta(seconds=1))
    r = client.get(f"/rights/assets/{ASSET}/passport", headers=_headers(None)).json()
    assert {s["state"] for s in r["statements"]} == {"expired", "revoked"}
    assert all(s["test_network"] and "physical possession" in s["what_this_means"] for s in r["statements"])


@pytest.mark.parametrize("value", [None, ["list", 1], "string", True, 12.5])
def test_passport_preserves_json_values_without_driver_coercion(db, client, value):
    _claim(db, value=value)
    r = client.get(f"/rights/assets/{ASSET}/passport", headers=_headers(None))
    assert r.status_code == 200 and r.json()["statements"][0]["value"] == value


def test_large_claims_and_aggregate_responses_are_refused(db, client):
    _claim(db, value={"large": "x" * (JSON_LIMIT + 1)})
    path = f"/rights/assets/{ASSET}/passport"
    r = client.get(path, headers=_headers(None))
    assert r.status_code == 503 and len(r.content) < 100
    with db.batch() as b:
        b.delete("PassportClaims", spanner.KeySet(all_=True))
    for _ in range(10):
        _claim(db, value={"large": "x" * (JSON_LIMIT - 100)})
    assert client.get(path, headers=_headers(None)).status_code == 503
    assert client.get(path + "?limit=1", headers=_headers(None)).status_code == 200


def test_reprint_status_checks_member_and_network_and_excludes_private_quote(db, client):
    from brandme_core.domains.rights.reprint import ReprintService
    job = ReprintService(db).create(network="preprod", allowance_id="aa" * 32, entitlement_id="bb" * 32,
                                   manufacturer_id="cc" * 32, member_subject_ref=MEMBER, quantity=1, job_commitment="dd" * 32)
    with db.batch() as b:
        b.update("ReprintJobs", ["job_id", "quote_json"], [[job, json.dumps({"internal_token": "private"})]])
    path = f"/rights/reprint-jobs/{job}"
    r = client.get(path, headers=_headers())
    assert r.status_code == 200 and r.json()["quantity"] == "1" and r.json()["state"] == "eligibility_check"
    _contract("ReprintJobRead", r.json())
    assert "private" not in r.text and "member_subject_ref" not in r.text
    missing = client.get(f"/rights/reprint-jobs/{JOB}", headers=_headers())
    other = client.get(path, headers=_headers(OTHER))
    assert missing.status_code == other.status_code == 404 and missing.json() == other.json()
    with db.batch() as b:
        b.update("ReprintJobs", ["job_id", "network"], [[job, "preview"]])
    assert client.get(path, headers=_headers()).status_code == 404


def test_inventory_is_explicitly_partial_and_commands_do_not_create_jobs(db, client):
    headers = _headers(token=PRIVACY)
    r = client.get("/privacy/inventory", headers=headers)
    assert r.status_code == 200 and len(r.json()["categories"]) == 5
    _contract("MyDataInventoryRead", r.json())
    assert r.json()["coverage"] == {"domains": ["rights"], "full_account": False}
    assert r.json()["capabilities"] == {"export": "unavailable", "deletion": "unavailable"}
    for path in ("/privacy/exports", "/privacy/deletion"):
        assert client.post(path, headers=headers, json={"confirm": True}).status_code == 503
    assert client.post(f"/rights/assets/{ASSET}/transfers", headers=_headers(), json={}).status_code == 503
    with db.snapshot(multi_use=True) as s:
        assert list(s.execute_sql("SELECT COUNT(*) FROM DeletionJobs"))[0][0] == 0
        assert list(s.execute_sql("SELECT COUNT(*) FROM ExportJobs"))[0][0] == 0


def test_deletion_status_is_owner_scoped_and_never_relays_handler_secrets(db, client):
    _deletion(db, state="completed_with_exceptions", receipt={"subject_ref": MEMBER, "provider_token": "secret", "categories": {
        "rights.control_links": {"status": "exception", "rows_affected": 1, "derived_purged": 0, "reason": "secret-provider-url"}}})
    path = f"/privacy/deletion/{JOB}"
    r = client.get(path, headers=_headers(token=PRIVACY))
    assert r.status_code == 200 and r.json()["state"] == "completed_with_exceptions"
    _contract("DeletionStatusRead", r.json())
    assert r.json()["outcomes"]["rights.control_links"] == {"status": "exception", "rows_affected": "1", "derived_purged": "0"}
    assert "secret" not in r.text and MEMBER not in r.text
    assert client.get(path, headers=_headers(OTHER, PRIVACY)).status_code == 404


def test_oversized_receipt_is_not_returned(db, client):
    _deletion(db, receipt={"categories": {}, "secret": "x" * JSON_LIMIT})
    r = client.get(f"/privacy/deletion/{JOB}", headers=_headers(token=PRIVACY))
    assert r.status_code == 503 and len(r.content) < 100


@pytest.mark.parametrize("state", ["restoring", "failed", "unknown"])
def test_restore_barrier_covers_every_read_and_health(db, client, state):
    with db.batch() as b:
        b.insert("RestoreRuns", ["restore_id", "backup_ref", "backup_taken_at", "state", "started_at"],
                 [[str(uuid.uuid4()), "private-backup", NOW, state, NOW]])
    for path in ("/health", "/rights/entitlements", f"/rights/reprint-jobs/{JOB}", f"/rights/assets/{ASSET}/passport", "/privacy/inventory", f"/privacy/deletion/{JOB}"):
        r = client.get(path, headers=_headers(token=PRIVACY if path.startswith("/privacy") else RIGHTS))
        assert r.status_code == 503 and "private-backup" not in r.text


def test_schema_preflight_checks_actual_migration_coverage(db):
    verify_schema(db)
    with db.batch() as b:
        b.update("SchemaMigrations", ["version", "state"], [[13, "failed"]])
    try:
        with pytest.raises(ReadError, match="schema_unavailable"):
            verify_schema(db)
    finally:
        with db.batch() as b:
            b.update("SchemaMigrations", ["version", "state"], [[13, "applied"]])


def test_provider_failure_is_redacted_and_query_retries_are_bounded():
    class BrokenDatabase:
        def snapshot(self, **_):
            raise RuntimeError(f"sensitive provider failure {PRIVACY}")
    with TestClient(create_app(BrokenDatabase(), ReadConfig.from_env(_env()))) as client:
        r = client.get("/privacy/inventory", headers=_headers(token=PRIVACY))
        assert r.status_code == 503 and "sensitive" not in r.text and PRIVACY not in r.text

    class Query:
        def execute_sql(self, sql, **kw):
            assert kw["retry"] is None and 0 < kw["timeout"] <= 2
            return []
    snap = BoundedSnapshot(Query())
    assert snap.query("SELECT 1") == []
    snap.deadline = 0
    with pytest.raises(ReadError):
        snap.query("SELECT 1")


def test_runnable_process_preflight_http_and_clean_failure(db):
    _entitlement(db)
    env = {**os.environ, **_env(db), "PYTHONPATH": str(ROOT)}
    check = subprocess.run([sys.executable, "-m", "brandme_core.read_api", "--check"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert check.returncode == 0 and json.loads(check.stdout)["read_only"]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "brandme_core.read_api"], cwd=ROOT, env={**env, "PORT": str(port)},
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1, trust_env=False)
                if response.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None:
                pytest.fail("read API process exited before readiness")
            time.sleep(.1)
        else:
            pytest.fail("read API process not ready")
        r = httpx.get(f"http://127.0.0.1:{port}/rights/entitlements", headers=_headers(), timeout=5, trust_env=False)
        assert r.status_code == 200 and len(r.json()["items"]) == 1
        assert httpx.get(f"http://127.0.0.1:{port}/privacy/inventory", headers=_headers(), timeout=5, trust_env=False).status_code == 401
    finally:
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
        assert RIGHTS not in stdout + stderr and PRIVACY not in stdout + stderr and MEMBER not in stdout + stderr
    refused = subprocess.run([sys.executable, "-m", "brandme_core.read_api", "--check"], cwd=ROOT,
                             env={**env, "RIGHTS_SERVICE_TOKEN": "secret-invalid"}, capture_output=True, text=True, timeout=10)
    assert refused.returncode == 2 and refused.stdout.strip() == '{"status":"startup_refused"}'
    assert "secret-invalid" not in refused.stdout + refused.stderr
