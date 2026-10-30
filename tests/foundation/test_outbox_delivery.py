"""Real Spanner lease races and a real Pub/Sub emulator process boundary."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, KeySet, param_types
from google.api_core.exceptions import InvalidArgument, NotFound
import pytest
import requests

from brandme_core.domains import events as domain_events
from brandme_core.events import EventEnvelope, first_delivery, write_events
from brandme_core.events.outbox import OutboxDispatcher, PermanentDeliveryError, shard_for
from brandme_core.events.pubsub import PubSubPublisher, emulator_endpoint
from brandme_core.events.worker import WorkerConfig, verify_schema
from .conftest import requires_spanner


def event(environment="development", event_type="member.created"):
    member = str(uuid.uuid4())
    return EventEnvelope(event_type=event_type, schema_version="1", aggregate_type="member",
                         aggregate_id=member, aggregate_version=1, environment=environment,
                         actor_ref="service:outbox-test", correlation_id=str(uuid.uuid4()),
                         privacy_class="member_private", payload={"member_id": member, "identity_provider": "test"})


@pytest.fixture
def outbox_db(migrated_database):
    with migrated_database.batch() as batch:
        batch.delete("OutboxEvents", KeySet(all_=True))
    yield migrated_database


def insert(db, *events):
    db.run_in_transaction(lambda tx: write_events(tx, events))


def read(db, ev):
    with db.snapshot() as snap:
        row = list(snap.read("OutboxEvents", ("status", "attempts", "lease_owner", "last_error"),
                             KeySet(keys=[[shard_for(ev.event_id), ev.event_id]])))[0]
        return dict(zip(("status", "attempts", "lease_owner", "last_error"), row))


def expire(db, ev):
    db.run_in_transaction(lambda tx: tx.execute_update("""UPDATE OutboxEvents
        SET lease_expires_at = TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 SECOND)
        WHERE shard = @shard AND event_id = @id""", params={"shard": shard_for(ev.event_id), "id": ev.event_id},
        param_types={"shard": param_types.INT64, "id": param_types.STRING}))


def dispatcher(db, deliver=lambda ev: None, **kw):
    return OutboxDispatcher(db, deliver, environment="development", base_backoff_seconds=0,
                            max_backoff_seconds=0, **kw)


@requires_spanner
def test_environment_isolation_and_fresh_lease_for_each_delivery(outbox_db):
    local, cloud = event(), event("production")
    insert(outbox_db, local, cloud)
    observed = []
    result = dispatcher(outbox_db, lambda ev: observed.append(ev.event_id)).run_once()
    assert result.delivered == 1 and observed == [local.event_id]
    assert read(outbox_db, cloud) == {"status": "pending", "attempts": 0, "lease_owner": None, "last_error": None}


@requires_spanner
def test_expired_same_owner_cannot_finish_replacement_lease(outbox_db):
    ev = event(); insert(outbox_db, ev)
    a, b = dispatcher(outbox_db, owner="same-replica"), dispatcher(outbox_db, owner="same-replica")
    old = a._claim(shard_for(ev.event_id))
    expire(outbox_db, ev)
    assert a._finish(old, None) == "stale"  # no replacement is needed to fence an expired lease
    new = b._claim(shard_for(ev.event_id))
    assert old["lease_token"] != new["lease_token"]
    assert a._finish(old, "delivery_unconfirmed") == "stale"
    assert b._finish(new, None) == "delivered"
    assert read(outbox_db, ev)["attempts"] == 2


@requires_spanner
def test_claims_are_exclusive_and_crash_attempts_are_bounded(outbox_db):
    ev = event(); insert(outbox_db, ev)
    workers = [dispatcher(outbox_db, max_attempts=2) for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        claims = list(pool.map(lambda worker: worker._claim(shard_for(ev.event_id)), workers))
    assert sum(c is not None for c in claims) == 1
    expire(outbox_db, ev)
    assert workers[0]._claim(shard_for(ev.event_id))["attempts"] == 2
    expire(outbox_db, ev)
    delivered = []
    result = dispatcher(outbox_db, lambda e: delivered.append(e), max_attempts=2).run_once()
    assert result.dead == 1 and not delivered
    assert read(outbox_db, ev)["last_error"] == "delivery_attempts_exhausted"


@requires_spanner
def test_retry_redacts_errors_and_counts_only_committed_outcomes(outbox_db):
    ev = event(); insert(outbox_db, ev)
    def fail(_):
        raise ConnectionError("https://provider/?token=NEVER_PERSIST_THIS private payload")
    result = dispatcher(outbox_db, fail, max_attempts=2).run_once()
    assert result.failed == 1 and result.delivered == result.dead == 0
    row = read(outbox_db, ev)
    assert row["attempts"] == 1 and row["last_error"] == "delivery_unconfirmed"
    assert dispatcher(outbox_db, fail, max_attempts=2).run_once().dead == 1


@requires_spanner
def test_bad_persisted_payload_is_dead_lettered_without_blocking_good_event(outbox_db):
    bad, good = event(), event(); insert(outbox_db, bad, good)
    with outbox_db.batch() as b:
        b.update("OutboxEvents", ("shard", "event_id", "payload"),
                 [[shard_for(bad.event_id), bad.event_id, JsonObject({"secret": "DO_NOT_LOG"})]])
    delivered = []
    result = dispatcher(outbox_db, lambda ev: delivered.append(ev.event_id)).run_once()
    assert result.dead == 1 and result.delivered == 1 and delivered == [good.event_id]
    assert read(outbox_db, bad)["last_error"] == "invalid_event"


@requires_spanner
def test_batch_is_bounded_and_does_not_prelease_waiting_rows(outbox_db):
    events = [event() for _ in range(5)]; insert(outbox_db, *events)
    def deliver(ev):
        # Only the event about to be delivered is leased, however long delivery takes.
        with outbox_db.snapshot() as snap:
            assert list(snap.execute_sql("SELECT COUNT(*) FROM OutboxEvents WHERE status = 'leased'"))[0][0] == 1
    result = dispatcher(outbox_db, deliver, batch_size=2).run_once()
    assert result.delivered == 2
    assert sum(read(outbox_db, e)["attempts"] == 0 for e in events) == 3


@requires_spanner
def test_allowlist_leaves_unowned_event_pending_and_stop_claims_nothing(outbox_db):
    ev = event(); insert(outbox_db, ev)
    d = dispatcher(outbox_db, event_types=["privacy.deletion.requested"])
    assert d.run_once().delivered == 0 and read(outbox_db, ev)["attempts"] == 0
    assert dispatcher(outbox_db).run_once(should_stop=lambda: True).delivered == 0
    assert read(outbox_db, ev)["attempts"] == 0


def config_env():
    return {"BRANDME_MODE": "development", "ENVIRONMENT": "development",
            "SPANNER_PROJECT_ID": "test-project", "SPANNER_INSTANCE_ID": "brandme-instance",
            "SPANNER_DATABASE_ID": "brandme-db", "SPANNER_EMULATOR_HOST": "127.0.0.1:9010",
            "PUBSUB_EMULATOR_HOST": "127.0.0.1:8085"}


@pytest.mark.parametrize("change", [
    {"ENVIRONMENT": "production"}, {"BRANDME_MODE": "production", "ENVIRONMENT": "production"},
    {"BRANDME_MODE": "sandbox", "ENVIRONMENT": "sandbox"}, {"PUBSUB_EMULATOR_HOST": ""},
    {"SPANNER_PROJECT_ID": ""}, {"OUTBOX_EVENT_TYPES": "unregistered.event"},
    {"PUBSUB_EMULATOR_HOST": "example.org:8085"}, {"PUBSUB_EMULATOR_HOST": "user:secret@localhost:8085"},
])
def test_worker_rejects_unsafe_configuration(change):
    with pytest.raises(ValueError):
        WorkerConfig.from_env({**config_env(), **change})


def topics(suffix=""):
    return {c: f"projects/test-project/topics/brandme-development-{c.replace('_', '-')}{suffix}"
            for c in ("public", "member_private", "restricted")}


def test_publisher_rejects_cross_environment_and_mixed_privacy_topics():
    mapping = topics()
    with pytest.raises(ValueError):
        PubSubPublisher(mapping, "production", emulator_host="127.0.0.1:8085")
    with pytest.raises(ValueError):
        PubSubPublisher(dict.fromkeys(mapping, mapping["public"]), "development", emulator_host="127.0.0.1:8085")


@pytest.mark.parametrize("status,body,redirect", [
    (200, b'{"messageIds":[]}', False),
    (200, b'{"messageIds":[null]}', False),
    (200, b'{"messageIds":["one","two"]}', False),
    (200, b'not-json', False),
    (200, b' ' * (16 * 1024 + 1), False),
    (403, b'provider-token=DO_NOT_PERSIST private data', False),
    (302, b'provider-token=DO_NOT_PERSIST', True),
])
def test_transport_rejects_invalid_ack_and_redirect_without_leaking_body(status, body, redirect):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(status)
            if redirect: self.send_header('Location', '/must-not-follow')
            self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    publisher = PubSubPublisher(topics(), 'development', emulator_host=f'127.0.0.1:{server.server_port}')
    try:
        with pytest.raises(RuntimeError) as error:
            publisher(event())
        assert 'DO_NOT_PERSIST' not in str(error.value) and 'http' not in str(error.value)
        assert len(calls) == 1
    finally:
        publisher.close(); server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_transport_stops_slow_response_body_and_rejects_cross_environment_before_http():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers['Content-Length']))
            body = b'{"messageIds":["123456789"]}'
            self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
            try:
                for byte in body:
                    self.wfile.write(bytes([byte])); self.wfile.flush(); time.sleep(.03)
            except (BrokenPipeError, ConnectionResetError): pass
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    publisher = PubSubPublisher(topics(), 'development', emulator_host=f'127.0.0.1:{server.server_port}', timeout_seconds=.15)
    try:
        with pytest.raises(PermanentDeliveryError): publisher(event('production'))
        assert not calls
        started = time.monotonic()
        with pytest.raises(RuntimeError, match='pubsub_response_timeout'): publisher(event())
        assert time.monotonic() - started < 1
    finally:
        publisher.close(); server.shutdown(); server.server_close(); thread.join(timeout=2)


@requires_spanner
def test_inbox_receipt_and_effect_roll_back_together(outbox_db):
    ev = event(); consumer = 'rollback-' + uuid.uuid4().hex[:8]
    def fail(tx):
        assert first_delivery(tx, consumer, ev)
        tx.insert('AuditEntries', ('audit_id', 'occurred_at', 'environment', 'actor_ref', 'action'),
                  [[ev.event_id, COMMIT_TIMESTAMP, 'development', 'service:test-consumer', 'event.applied']])
        raise ValueError('business invariant refused effect')
    with pytest.raises(ValueError): outbox_db.run_in_transaction(fail)
    with outbox_db.snapshot(multi_use=True) as snap:
        assert not list(snap.read('InboxReceipts', ('event_id',), KeySet(keys=[[consumer, ev.event_id]])))
        assert not list(snap.read('AuditEntries', ('audit_id',), KeySet(keys=[[ev.event_id]])))
    assert outbox_db.run_in_transaction(lambda tx: first_delivery(tx, consumer, ev))


@requires_spanner
def test_startup_rejects_missing_or_incomplete_schema(runner, empty_database, tmp_path):
    with pytest.raises((InvalidArgument, NotFound)): verify_schema(empty_database)
    runner.migrate_up(empty_database, log=lambda *_: None)
    verify_schema(empty_database)
    with empty_database.batch() as batch:
        batch.update('SchemaMigrations', ('version', 'state'), [[13, 'applying']])
    with pytest.raises(RuntimeError, match='outbox_schema_unavailable'): verify_schema(empty_database)


@pytest.fixture(scope="module")
def pubsub_server(tmp_path_factory):
    binary = os.environ.get("PUBSUB_EMULATOR_BIN")
    if not binary:
        pytest.skip("PUBSUB_EMULATOR_BIN required; CI fetches and runs the pinned Google emulator")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    log = (tmp_path_factory.mktemp("pubsub") / "server.log").open("w")
    server = subprocess.Popen([str(Path(binary).resolve()), "--host=127.0.0.1", f"--port={port}"], stdout=log, stderr=log)
    try:
        for _ in range(200):
            if server.poll() is not None:
                pytest.fail("Pub/Sub emulator exited at startup")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=.1).close(); break
            except OSError:
                time.sleep(.05)
        else:
            pytest.fail("Pub/Sub emulator did not become ready")
        yield f"127.0.0.1:{port}"
    finally:
        server.terminate(); server.wait(timeout=10); log.close()


def provision(host, mapping):
    subscriptions = {}
    for privacy, topic in mapping.items():
        assert requests.put(f"http://{host}/v1/{topic}", json={"messageRetentionDuration": "86400s"}, timeout=5).status_code == 200
        sub = topic.replace("/topics/", "/subscriptions/") + "-test"
        assert requests.put(f"http://{host}/v1/{sub}", json={"topic": topic}, timeout=5).status_code == 200
        subscriptions[privacy] = sub
    return subscriptions


def pull(host, sub):
    response = requests.post(f"http://{host}/v1/{sub}:pull", json={"maxMessages": 10, "returnImmediately": True}, timeout=5)
    response.raise_for_status()
    return response.json().get("receivedMessages", [])


@requires_spanner
def test_real_pubsub_lost_ack_retries_stable_id_and_inbox_effect_once(outbox_db, pubsub_server):
    mapping = topics("-" + uuid.uuid4().hex[:8]); subs = provision(pubsub_server, mapping)
    ev = event(); insert(outbox_db, ev)
    publisher = PubSubPublisher(mapping, "development", emulator_host=pubsub_server)
    publisher.check_topics()
    first = True
    def lost_ack(e):
        nonlocal first
        publisher(e)
        if first:
            first = False
            raise ConnectionError("remote success, local acknowledgement lost")
    d = dispatcher(outbox_db, lost_ack)
    try:
        assert d.run_once().failed == 1
        assert d.run_once().delivered == 1
        messages = []
        for _ in range(30):
            messages.extend(pull(pubsub_server, subs["member_private"]))
            if len(messages) >= 2: break
            time.sleep(.05)
        assert len(messages) == 2
        assert len({m["message"]["messageId"] for m in messages}) == 2
        for m in messages:
            wire = json.loads(base64.b64decode(m["message"]["data"]))
            assert wire == ev.to_wire()
            assert m["message"]["attributes"]["event_id"] == ev.event_id
        # A real database effect and receipt share one transaction.
        consumer = "outbox-integration-" + uuid.uuid4().hex[:8]
        def apply(tx):
            if not first_delivery(tx, consumer, ev):
                return False
            tx.insert("AuditEntries", ("audit_id", "occurred_at", "environment", "actor_ref", "action"),
                      [[ev.event_id, COMMIT_TIMESTAMP, "development", "service:test-consumer", "event.applied"]])
            return True
        applied = [outbox_db.run_in_transaction(apply) for _ in messages]
        assert applied == [True, False]
        with outbox_db.snapshot() as snap:
            assert len(list(snap.read("AuditEntries", ("audit_id",), KeySet(keys=[[ev.event_id]])))) == 1
        assert not pull(pubsub_server, subs["public"]) and not pull(pubsub_server, subs["restricted"])
    finally:
        publisher.close()


@requires_spanner
def test_real_worker_process_restarts_delivers_privacy_event_and_stops(outbox_db, pubsub_server, tmp_path):
    mapping = topics("-" + uuid.uuid4().hex[:8]); subs = provision(pubsub_server, mapping)
    ev = EventEnvelope(event_type="privacy.deletion.requested", schema_version="1", aggregate_type="deletion_job",
        aggregate_id=str(uuid.uuid4()), aggregate_version=1, environment="development", actor_ref="service:privacy",
        correlation_id=str(uuid.uuid4()), privacy_class="restricted", payload={"job_id": str(uuid.uuid4()), "scope": "account"})
    insert(outbox_db, ev)
    # Simulate a dead predecessor after claiming; a fresh process must recover the expired lease.
    dispatcher(outbox_db)._claim(shard_for(ev.event_id)); expire(outbox_db, ev)
    env = {**os.environ, **config_env(), "SPANNER_DATABASE_ID": outbox_db.database_id,
           "SPANNER_EMULATOR_HOST": os.environ["SPANNER_EMULATOR_HOST"], "PUBSUB_EMULATOR_HOST": pubsub_server,
           **{"OUTBOX_PUBSUB_TOPIC_" + c.upper(): t for c, t in mapping.items()}}
    logfile = tmp_path / "worker.log"
    with logfile.open("w") as log:
        child = subprocess.Popen([sys.executable, "-m", "brandme_core.events.worker"], env=env, stdout=log, stderr=log)
        try:
            for _ in range(150):
                if child.poll() is not None: pytest.fail(logfile.read_text())
                if read(outbox_db, ev)["status"] == "delivered": break
                time.sleep(.1)
            else: pytest.fail("worker did not deliver after restart: " + logfile.read_text())
            child.terminate(); assert child.wait(timeout=10) == 0
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=5)
    messages = pull(pubsub_server, subs["restricted"])
    assert len(messages) == 1 and json.loads(base64.b64decode(messages[0]["message"]["data"])) == ev.to_wire()
    logs = logfile.read_text()
    assert '"status": "ready"' in logs and ev.event_id not in logs and ev.aggregate_id not in logs
    assert read(outbox_db, ev)["attempts"] == 2


@requires_spanner
def test_worker_refuses_unprovisioned_topic_before_claiming(outbox_db, pubsub_server):
    ev = event(); insert(outbox_db, ev)
    mapping = topics('-missing-' + uuid.uuid4().hex[:8])
    env = {**os.environ, **config_env(), 'SPANNER_DATABASE_ID': outbox_db.database_id,
           'SPANNER_EMULATOR_HOST': os.environ['SPANNER_EMULATOR_HOST'], 'PUBSUB_EMULATOR_HOST': pubsub_server,
           **{'OUTBOX_PUBSUB_TOPIC_' + c.upper(): t for c, t in mapping.items()}}
    result = subprocess.run([sys.executable, '-m', 'brandme_core.events.worker', '--once'],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2 and 'startup_refused' in result.stdout
    assert 'http' not in result.stdout + result.stderr and ev.event_id not in result.stdout + result.stderr
    assert read(outbox_db, ev)['status'] == 'pending' and read(outbox_db, ev)['attempts'] == 0


def test_publisher_refuses_topics_without_retention(pubsub_server):
    mapping = topics('-no-retention-' + uuid.uuid4().hex[:8])
    for topic in mapping.values():
        assert requests.put(f'http://{pubsub_server}/v1/{topic}', json={}, timeout=5).status_code == 200
    publisher = PubSubPublisher(mapping, 'development', emulator_host=pubsub_server)
    try:
        with pytest.raises(RuntimeError, match='pubsub_topic_retention_required'): publisher.check_topics()
    finally: publisher.close()
