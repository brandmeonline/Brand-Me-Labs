"""Apply V006/V007 to a Cloud Spanner emulator and probe key constraints.

Requires SPANNER_EMULATOR_REST (e.g. http://127.0.0.1:9020). Skipped — not passed — without it.
Migrations V001–V005 belong to opus-foundation; V006/V007 deliberately have no FKs into them,
so they are applied here to an empty database.
"""

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

REST = os.environ.get("SPANNER_EMULATOR_REST")
GRPC = os.environ.get("SPANNER_EMULATOR_GRPC", "127.0.0.1:9010")
pytestmark = pytest.mark.skipif(not REST, reason="SPANNER_EMULATOR_REST not set")
MIGRATIONS = Path(__file__).resolve().parents[1] / "brandme-data/spanner/migrations"
PROJECT, INSTANCE = "brandme-test", "commerce-lane"


def statements(path: Path):
    text = "\n".join(l for l in path.read_text().splitlines() if not l.strip().startswith("--"))
    return [s.strip().rstrip(";").strip() for s in re.split(r";\s*\n", text) if s.strip().rstrip(";").strip()]


def call(method, url, body=None):
    req = urllib.request.Request(REST + url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


@pytest.fixture(scope="module")
def db():
    call("POST", f"/v1/projects/{PROJECT}/instances", {
        "instanceId": INSTANCE, "instance": {"config": f"projects/{PROJECT}/instanceConfigs/emulator-config",
                                             "displayName": "commerce lane", "nodeCount": 1}})
    name = "c" + uuid.uuid4().hex[:20]
    stmts = statements(MIGRATIONS / "V006_providers.sql") + statements(MIGRATIONS / "V007_commerce.sql")
    status, body = call("POST", f"/v1/projects/{PROJECT}/instances/{INSTANCE}/databases",
                        {"createStatement": f"CREATE DATABASE `{name}`", "extraStatements": stmts})
    assert status == 200, body
    path = f"/v1/projects/{PROJECT}/instances/{INSTANCE}/databases/{name}"
    for _ in range(50):
        s, ddl = call("GET", path + "/ddl")
        if s == 200 and len(ddl.get("statements", [])) == len(stmts):
            break
    assert len(ddl["statements"]) == len(stmts), (len(ddl.get("statements", [])), len(stmts))
    return path, len(stmts)


def dml(path, sql):
    """Execute DML through the gRPC client so constraint errors are visible. Returns (ok, message)."""
    from google.api_core.exceptions import GoogleAPICallError
    from google.cloud import spanner
    os.environ.setdefault("SPANNER_EMULATOR_HOST", GRPC)
    parts = path.strip("/").split("/")  # v1/projects/P/instances/I/databases/D
    project, instance, database = parts[2], parts[4], parts[6]
    db_ = spanner.Client(project=project).instance(instance).database(database)
    try:
        db_.run_in_transaction(lambda tx: tx.execute_update(sql))
        return True, ""
    except GoogleAPICallError as exc:
        return False, str(exc)


def test_all_statements_applied(db):
    path, n = db
    assert n >= 30


def test_simulation_provider_rejected_in_production(db):
    path, _ = db
    s, body = dml(path, """INSERT INTO ProviderConnections (environment, provider_id, display_name, simulation,
        access_level, country_codes, disclosure, data_use, allowed_redirect_hosts, protocols, version, created_at,
        updated_at) VALUES ('production', 'demo_atelier', 'x', true, 'simulation', ['US'], 'x', JSON '{}', [],
        JSON '{}', 1, PENDING_COMMIT_TIMESTAMP(), PENDING_COMMIT_TIMESTAMP())""")
    assert not s and "ck_no_simulation_outside_dev" in body


def test_quote_total_arithmetic_enforced(db):
    path, _ = db
    s, body = dml(path, """INSERT INTO CheckoutQuotes (quote_id, member_id, environment, provider_id, merchant_id,
        payee_ref, cart_id, cart_revision, currency, subtotal_minor, tax_minor, shipping_minor, discount_minor,
        total_minor, delivery_ref, checkout_reference, terms, terms_hash, quote_hash, hash_domain_version,
        material_document, issued_at, expires_at) VALUES ('q1', 'm1', 'development', 'demo_atelier', 'mer', 'pay',
        'c1', 1, 'USD', 8900, 712, 0, 0, 1, 'd', 'ref', JSON '{}', 't', 'h', '1', JSON '{}',
        TIMESTAMP '2026-10-05T12:00:00Z', TIMESTAMP '2026-10-05T12:05:00Z')""")
    assert not s and "ck_quote_total" in body


def test_verified_capability_requires_evidence(db):
    path, _ = db
    s, _ = dml(path, """INSERT INTO ProviderConnections (environment, provider_id, display_name, simulation,
        access_level, country_codes, disclosure, data_use, allowed_redirect_hosts, protocols, version, created_at,
        updated_at) VALUES ('development', 'nordstrom_impact', 'n', false, 'link_only', ['US'], 'x', JSON '{}', [],
        JSON '{}', 1, PENDING_COMMIT_TIMESTAMP(), PENDING_COMMIT_TIMESTAMP())""")
    assert s, _
    s, body = dml(path, """INSERT INTO ProviderCapabilities (environment, provider_id, capability, state,
        reason_code, evidence_kind, updated_at) VALUES ('development', 'nordstrom_impact', 'catalog.feed',
        'verified', 'ok', 'host_reachability', PENDING_COMMIT_TIMESTAMP())""")
    assert not s and "ck_verified_has_evidence" in body


def test_provider_idempotency_key_unique(db):
    path, _ = db
    row = lambda op: f"""INSERT INTO PurchaseOperations (operation_id, member_id, client_id, quote_id, quote_hash,
        provider_id, state, provider_idempotency_key, attempts, version, created_at, updated_at) VALUES ('{op}',
        'm1', 'c', 'q', 'h', 'demo_atelier', 'submitting', 'bm-same-key', 1, 1, CURRENT_TIMESTAMP(),
        CURRENT_TIMESTAMP())"""
    assert dml(path, row("op-1"))[0]
    s, body = dml(path, row("op-2"))
    assert not s and "PurchaseOperationsByProviderKey" in body
