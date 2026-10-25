"""Outbox retention and subject erasure on a real Spanner emulator (founder ruling Q19)."""
from datetime import datetime, timedelta, timezone
import json
import os
import signal
import subprocess
import sys
import uuid

from google.api_core.exceptions import InvalidArgument, NotFound
from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, KeySet
import pytest

from brandme_core.domains.privacy import deletion as pd
from brandme_core.events import EventEnvelope, write_events
from brandme_core.events import erasure, retention
from brandme_core.events.outbox import OutboxDispatcher, json_payload, shard_for
from brandme_core.events.retention import (
    NIL_SUBJECT, RetentionConfig, SweepResult, erase_subject_events, erase_subject_requests, purge_delivered,
    subject_keys, sweep_erased_subjects, verify_schema,
)
from .conftest import requires_spanner

COLUMNS = ("shard", "event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version",
           "occurred_at", "environment", "actor_ref", "correlation_id", "causation_id", "privacy_class", "payload",
           "status", "attempts", "next_attempt_at", "lease_owner", "lease_expires_at", "delivered_at", "last_error",
           "created_at")
DAY = timedelta(days=1)


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


@pytest.fixture
def db(migrated_database):
    with migrated_database.batch() as batch:
        for table in ("OutboxEvents", "IdempotencyRecords", "DeletionTombstones"):
            batch.delete(table, KeySet(all_=True))
    yield migrated_database


def event_id_in(shard=None):
    while True:
        event_id = uid()
        if shard is None or shard_for(event_id) == shard:
            return event_id


def put(db, *, status="pending", payload=None, actor="service:test", aggregate=None, environment="development",
        next_attempt=None, delivered=None, lease=None, last_error=None, shard=None, causation=None):
    """One raw outbox row, so tests control every column the purge and erasure read."""
    event_id = event_id_in(shard)
    t = now()
    values = (shard_for(event_id), event_id, "member.created", "1", "member", aggregate or uid(), 1, t, environment,
              actor, uid(), causation, "member_private", JsonObject(payload or {"member_id": uid()}), status,
              1 if status != "pending" else 0, next_attempt or t, lease and "owner:token", lease, delivered,
              last_error, COMMIT_TIMESTAMP)
    db.run_in_transaction(lambda tx: tx.insert("OutboxEvents", COLUMNS, [values]))
    return event_id


def rows(db):
    with db.snapshot() as snap:
        out = {}
        for r in snap.execute_sql(f"SELECT {', '.join(COLUMNS)} FROM OutboxEvents"):
            d = dict(zip(COLUMNS, r))
            d["payload"] = json_payload(d["payload"])
            out[d["event_id"]] = d
        return out


def replay(db, principal, body, operation="op"):
    def tx(t):
        t.insert("IdempotencyRecords", ("principal_ref", "environment", "operation", "idempotency_key", "request_digest",
                                        "state", "response_status", "response_body", "created_at", "expires_at"),
                 [(principal, "development", operation, "k-" + uuid.uuid4().hex, "0" * 64, "completed", 200,
                   JsonObject(body), COMMIT_TIMESTAMP, now() + 30 * DAY)])
    db.run_in_transaction(tx)


def replays(db):
    with db.snapshot() as snap:
        return sorted((p, op, json.dumps(json_payload(b), sort_keys=True)) for p, op, b in snap.execute_sql(
            "SELECT principal_ref, operation, response_body FROM IdempotencyRecords"))


def tombstone(db, subject, category, created_at=COMMIT_TIMESTAMP, record_keys=()):
    db.run_in_transaction(lambda tx: tx.insert(
        "DeletionTombstones", ("subject_ref", "category", "tombstone_id", "deletion_job_id", "record_keys", "created_at"),
        [(subject, category, uid(), uid(), list(record_keys), created_at)]))


# --- subject keys --------------------------------------------------------------


def test_subject_keys_cover_actor_and_bare_forms_and_refuse_unsafe_refs():
    m = uid()
    assert subject_keys(m) == subject_keys(f"member:{m}") == (m, f"member:{m}")
    assert subject_keys("m9") == ("m9",)
    for bad in ("", "a b", 'a"b', "a\\b", "x" * 129, None, 9):
        with pytest.raises(ValueError):
            subject_keys(bad)
    for erase in (erase_subject_events, erase_subject_requests):
        with pytest.raises(TypeError):
            erase(None, "m9")  # one string is not a list of subjects
        assert erase(None, []) == (0, 0)


# --- age purge -----------------------------------------------------------------


@requires_spanner
def test_purge_deletes_only_delivered_and_erased_rows_older_than_seven_days(db):
    old, recent = now() - 8 * DAY, now() - 6 * DAY
    # Five old delivered rows in one shard, purged in batches of two.
    purged = [put(db, status="delivered", next_attempt=old, delivered=old, shard=3) for _ in range(5)]
    purged.append(put(db, status="dead", last_error="subject_erased", next_attempt=old, payload={}))
    kept = [
        put(db, status="delivered", next_attempt=recent, delivered=recent),
        put(db, status="delivered", next_attempt=old, delivered=now() - DAY),  # long backoff, delivered recently
        put(db, status="delivered", next_attempt=old, delivered=old, environment="production"),
        put(db, status="pending", next_attempt=old),
        put(db, status="leased", next_attempt=old, lease=old),
        put(db, status="dead", last_error="invalid_event", next_attempt=old),
        put(db, status="dead", last_error="delivery_attempts_exhausted", next_attempt=old),
        put(db, status="dead", last_error="subject_erased", next_attempt=recent, payload={}),
    ]
    assert purge_delivered(db, "development", now(), batch_size=2) == len(purged)
    assert set(rows(db)) == set(kept)
    assert purge_delivered(db, "development", now()) == 0


def test_purge_refuses_unbounded_or_ambiguous_arguments():
    with pytest.raises(ValueError):
        purge_delivered(None, "prod", now())
    with pytest.raises(ValueError):
        purge_delivered(None, "development", datetime.now())
    with pytest.raises(ValueError):
        purge_delivered(None, "development", now(), older_than=timedelta(hours=1))
    with pytest.raises(ValueError):
        purge_delivered(None, "development", now(), batch_size=5000)


# --- subject erasure -----------------------------------------------------------


@requires_spanner
def test_erasure_withdraws_undelivered_deletes_delivered_and_leaves_others(db):
    s, other = uid(), uid()
    withdrawn = [
        put(db, payload={"member_id": s}, causation=uid()),
        put(db, status="leased", actor=f"member:{s}", lease=now() + 300 * timedelta(seconds=1)),
        put(db, status="dead", aggregate=s, last_error="message_rejected"),
        put(db, payload={"member_a": other, "member_b": s}, actor=f"member:{other}"),  # names both: withdrawn
    ]
    deleted = [put(db, status="delivered", delivered=now(), payload={"ids": [uid(), s]}),
               put(db, status="delivered", delivered=now(), actor=f"member:{s}/delegation:{uid()}")]
    untouched = [put(db, payload={"member_id": other}, actor=f"member:{other}"),
                 put(db, status="delivered", delivered=now(), aggregate=other)]
    before = rows(db)
    started = now() - timedelta(seconds=5)
    assert erase_subject_events(db, [s]) == (len(withdrawn), len(deleted))
    after = rows(db)
    assert set(after) == set(withdrawn) | set(untouched)
    for event_id in withdrawn:
        r = after[event_id]
        assert (r["status"], r["last_error"], r["payload"], r["actor_ref"]) == ("dead", "subject_erased", {}, "service:privacy")
        assert r["aggregate_id"] == r["correlation_id"] == event_id and r["causation_id"] is None
        assert r["lease_owner"] is None and r["lease_expires_at"] is None and r["next_attempt_at"] >= started
        assert r["event_type"] == before[event_id]["event_type"] and r["occurred_at"] == before[event_id]["occurred_at"]
    assert all(after[e] == before[e] for e in untouched)
    assert erase_subject_events(db, [s]) == (0, 0)
    assert erase_subject_events(db, [f"member:{s}"]) == (0, 0)


@requires_spanner
def test_short_refs_match_whole_json_tokens_never_substrings(db):
    m9 = [put(db, payload={"recipient_ids": ["m1", "m9"]}), put(db, actor="member:m9/delegation:d1"), put(db, aggregate="m9")]
    m99 = [put(db, payload={"member_id": "m99"}), put(db, payload={"note": "am9x", "m": "m9 "}),
           put(db, actor="member:m99/delegation:d1"), put(db, actor="member:m9x"), put(db, aggregate="m99")]
    assert erase_subject_events(db, ["m9"]) == (3, 0)
    after = rows(db)
    assert all(after[e]["last_error"] == "subject_erased" for e in m9)
    assert all(after[e]["status"] == "pending" and after[e]["last_error"] is None for e in m99)


@requires_spanner
def test_withdrawn_leased_row_finishes_stale_and_is_never_claimed_or_published(db):
    m = uid()
    ev = EventEnvelope(event_type="member.created", schema_version="1", aggregate_type="member", aggregate_id=m,
                       aggregate_version=1, environment="development", actor_ref=f"member:{m}", correlation_id=uid(),
                       privacy_class="member_private", payload={"member_id": m, "identity_provider": "test"})
    db.run_in_transaction(lambda tx: write_events(tx, [ev]))
    published = []
    dispatcher = OutboxDispatcher(db, published.append, environment="development", base_backoff_seconds=0,
                                  max_backoff_seconds=0)
    claimed = dispatcher._claim(shard_for(ev.event_id))
    assert claimed["event_id"] == ev.event_id
    assert erase_subject_events(db, [m]) == (1, 0)
    assert dispatcher._finish(claimed, None) == "stale"  # the in-flight delivery cannot mark it delivered
    assert dispatcher.run_once().delivered == 0 and published == []
    assert dispatcher._claim(shard_for(ev.event_id)) is None
    r = rows(db)[ev.event_id]
    assert (r["status"], r["last_error"], r["payload"]) == ("dead", "subject_erased", {})


@requires_spanner
def test_request_erasure_covers_delegations_and_unlinks_other_principals(db):
    s, other = uid(), uid()
    for principal in (f"member:{s}", f"member:{s}", f"member:{s}/delegation:{uid()}"):
        replay(db, principal, {"item": {"title": "Linen shirt", "member_id": s}})
    replay(db, f"member:{other}", {"recipient_ids": [s, "x"], "nested": {"owner": s}, "count": 2}, "decisions.create")
    replay(db, f"member:{other}", {"title": "Scarf"}, "wardrobe.items.create")
    replay(db, f"member:{s}x", {"ok": True})  # another principal whose ref merely starts with s
    assert erase_subject_requests(db, [s]) == (3, 1)
    assert replays(db) == sorted([
        (f"member:{other}", "decisions.create",
         json.dumps({"count": 2, "nested": {"owner": NIL_SUBJECT}, "recipient_ids": [NIL_SUBJECT, "x"]}, sort_keys=True)),
        (f"member:{other}", "wardrobe.items.create", json.dumps({"title": "Scarf"})),
        (f"member:{s}x", "op", json.dumps({"ok": True})),
    ])
    assert erase_subject_requests(db, [f"member:{s}"]) == (0, 0)


@requires_spanner
def test_erasure_batches_more_than_one_hundred_subjects(db):
    many = [uid() for _ in range(150)]  # 300 keys: three statements per table
    events = [put(db, payload={"member_id": m}) for m in many[::30]]
    for m in many[::50]:
        replay(db, f"member:{m}", {"ok": True})
    other = f"member:{uid()}"
    replay(db, other, {"recipients": many[:3]})
    assert erase_subject_events(db, many) == (len(events), 0)
    deleted, unlinked = erase_subject_requests(db, many)
    # A body naming subjects from several statements is counted once per statement.
    assert deleted == 3 and 1 <= unlinked <= 3
    assert replays(db) == [(other, "op", json.dumps({"recipients": [NIL_SUBJECT] * 3}))]
    assert erase_subject_events(db, many) == (0, 0) and erase_subject_requests(db, many) == (0, 0)


@requires_spanner
def test_sweep_reerases_only_recent_whole_category_platform_tombstones(db):
    swept, narrowed, other_category, expired = uid(), uid(), uid(), uid()
    tombstone(db, swept, "platform.event_outbox")
    tombstone(db, swept, "platform.request_replay")
    tombstone(db, narrowed, "platform.event_outbox", record_keys=("k1",))
    tombstone(db, other_category, "wardrobe.items")
    tombstone(db, expired, "platform.request_replay", created_at=now() - 31 * DAY)
    late = [put(db, payload={"member_id": swept}), put(db, status="delivered", delivered=now(), actor=f"member:{swept}")]
    kept = [put(db, payload={"member_id": m}) for m in (narrowed, other_category, expired)]
    replay(db, f"member:{swept}", {"ok": True})
    replay(db, f"member:{expired}", {"ok": True})
    assert sweep_erased_subjects(db, now()) == SweepResult(1, 1, 1, 1, 0)
    after = rows(db)
    assert set(after) == {late[0], *kept} and after[late[0]]["last_error"] == "subject_erased"
    assert all(after[e]["status"] == "pending" for e in kept)
    assert [p for p, _, _ in replays(db)] == [f"member:{expired}"]
    assert sweep_erased_subjects(db, now()) == SweepResult(1, 0, 0, 0, 0)


# --- privacy handler -----------------------------------------------------------


@requires_spanner
def test_platform_handler_exports_metadata_only_and_refuses_record_level_requests(db):
    m, friend = uid(), uid()
    put(db, actor=f"member:{m}", payload={"member_id": m, "title": "Linen shirt"})
    put(db, actor=f"member:{friend}", payload={"reported_id": m})  # someone else's event about the member
    replay(db, f"member:{m}", {"title": "Linen shirt"})
    handler = erasure.PLATFORM_PRIVACY_HANDLER
    ctx = pd.SubjectContext(subject_ref=m, job_id=uid(), requested_at=now())
    with db.snapshot(multi_use=True) as snap:
        events = handler.export(snap, ctx, "platform.event_outbox")
        requests = handler.export(snap, ctx, "platform.request_replay")
    assert [sorted(r) for r in events.records] == [["event_type", "occurred_at", "status"]] and events.notes
    assert [sorted(r) for r in requests.records] == [["created_at", "expires_at", "operation"]]
    assert "Linen shirt" not in json.dumps(events.records + requests.records) and friend not in json.dumps(events.records)
    narrowed = pd.SubjectContext(subject_ref=m, job_id=uid(), requested_at=now(), record_keys=("one",))
    for key in erasure.CATEGORIES:
        out = handler.delete_outside_txn(db, narrowed, key)
        assert (out.rows_affected, out.done, out.exception) == (0, True, erasure.RECORD_LEVEL_REFUSED)
    assert len(rows(db)) == 2 and len(replays(db)) == 1  # a refused request touches nothing
    with pytest.raises(RuntimeError):
        handler.delete(None, ctx, "platform.event_outbox")
    out = handler.delete_outside_txn(db, ctx, "platform.event_outbox")
    assert (out.rows_affected, out.done, out.exception) == (2, True, None)
    assert handler.purge_derived(ctx, "platform.event_outbox").detail == erasure.BROKER_COPIES


def test_registration_is_idempotent_and_lists_both_catalogs():
    from brandme_core.domains import data_categories

    reg = pd.PrivacyRegistry()
    assert erasure.register_platform_privacy(reg) is erasure.PLATFORM_PRIVACY_HANDLER
    assert erasure.register_platform_privacy(reg) is erasure.PLATFORM_PRIVACY_HANDLER
    assert [c.key for c in reg.categories()] == ["platform.event_outbox", "platform.request_replay"]
    assert all(c.on_delete is pd.OnDelete.ERASE and c.retention for c in reg.categories())
    # Registered at import into the default registry and the foundation catalog.
    assert {c.key for c in pd.registry.categories() if c.domain == "platform"} == set(erasure.CATEGORIES)
    assert {c.name for c in data_categories() if c.domain == "platform"} == set(erasure.CATEGORIES)

    class StandIn(erasure.PlatformPrivacyHandler):
        pass

    owned = pd.PrivacyRegistry()
    owned.register(StandIn())
    assert erasure.register_platform_privacy(owned) is None


# --- process -------------------------------------------------------------------


def config_env(**change):
    return {"BRANDME_MODE": "development", "ENVIRONMENT": "development", "SPANNER_PROJECT_ID": "test-project",
            "SPANNER_INSTANCE_ID": "brandme-instance", "SPANNER_DATABASE_ID": "brandme-db",
            "SPANNER_EMULATOR_HOST": "127.0.0.1:9010", **change}


@pytest.mark.parametrize("change", [
    {"ENVIRONMENT": "production"}, {"ENVIRONMENT": ""}, {"SPANNER_EMULATOR_HOST": ""}, {"SPANNER_DATABASE_ID": " "},
    {"BRANDME_MODE": "sandbox", "ENVIRONMENT": "sandbox"},
    {"BRANDME_MODE": "production", "ENVIRONMENT": "production", "ENABLE_STUB_MODE": "true", "SPANNER_EMULATOR_HOST": ""},
])
def test_config_rejects_unsafe_environment(change):
    with pytest.raises(ValueError):
        RetentionConfig.from_env(config_env(**change))


def test_config_accepts_strict_mode_without_emulator():
    cfg = RetentionConfig.from_env(config_env(BRANDME_MODE="sandbox", ENVIRONMENT="sandbox", SPANNER_EMULATOR_HOST=""))
    assert (cfg.environment, cfg.database) == ("sandbox", "brandme-db")


def cli(*args, env, timeout=60):
    return subprocess.run([sys.executable, "-m", "brandme_core.events.retention", *args], env={"PATH": "", **env},
                          capture_output=True, text=True, timeout=timeout)


@pytest.mark.parametrize("env,code", [
    ({"BRANDME_MODE": "sandbox", "ENVIRONMENT": "sandbox"}, 2),
    ({"BRANDME_MODE": "production", "ENVIRONMENT": "production", **{k: "x" for k in (
        "SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID")}, "SPANNER_EMULATOR_HOST": "127.0.0.1:9010"}, 2),
    ({"BRANDME_MODE": "development", "ENVIRONMENT": "development"}, 2),
    ({"BRANDME_MODE": "sandbox"}, 3),
    ({"BRANDME_MODE": "production", "ENVIRONMENT": "production", "MIDNIGHT_FALLBACK_MODE": "true"}, 3),
])
def test_cli_refuses_with_constant_records(env, code):
    out = cli("--check", env=env)
    assert out.returncode == code, out.stderr
    if code == 2:
        assert out.stdout == '{"status":"startup_refused"}\n' and "Traceback" not in out.stderr
    else:
        assert out.stdout == "" and "REFUSED" in out.stderr and "events_retention" in out.stderr


def test_cli_help_needs_no_configuration():
    out = cli("--help", env={})
    assert out.returncode == 0 and "--once" in out.stdout and "--check" in out.stdout


@requires_spanner
def test_schema_check_refuses_unmigrated_database(empty_database):
    with pytest.raises((InvalidArgument, NotFound)):
        verify_schema(empty_database)


@requires_spanner
def test_cli_once_check_and_loop_against_emulator(db):
    old = now() - 8 * DAY
    stale = put(db, status="delivered", next_attempt=old, delivered=old)
    member = uid()
    env = config_env(SPANNER_DATABASE_ID=db.database_id, SPANNER_EMULATOR_HOST=os.environ["SPANNER_EMULATOR_HOST"])
    check = cli("--check", env=env)
    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout) == {"status": "ready", "environment": "development",
                                        "delivered_retention_days": 7, "sweep_window_days": 30}
    tombstone(db, member, "platform.event_outbox")
    late = put(db, payload={"member_id": member})
    once = cli("--once", env=env)
    assert once.returncode == 0, once.stdout + once.stderr
    record = json.loads(once.stdout.splitlines()[-1])
    assert record == {"status": "retention", "purged": 1, "subjects": 1, "withdrawn": 1, "deleted": 0,
                      "requests_deleted": 0, "requests_unlinked": 0}
    assert stale not in rows(db) and rows(db)[late]["last_error"] == "subject_erased"
    assert stale not in once.stdout + once.stderr and member not in once.stdout + once.stderr  # counts only
    child = subprocess.Popen([sys.executable, "-m", "brandme_core.events.retention"], env={"PATH": "", **env},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert json.loads(child.stdout.readline())["status"] == "ready"
        assert json.loads(child.stdout.readline())["status"] == "retention"
        child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=15) == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_audited_process_is_registered():
    from brandme_core.config import AUDITED_PROCESSES, Mode, enforce_boot_guard

    assert "events_retention" in AUDITED_PROCESSES
    assert enforce_boot_guard("events_retention", env={"BRANDME_MODE": "production",
                                                        "ENVIRONMENT": "production"}) is Mode.PRODUCTION
    assert retention.CATEGORIES == tuple(erasure.CATEGORIES)
