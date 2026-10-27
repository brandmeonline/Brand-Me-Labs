"""Outbox retention and subject erasure on a real Spanner emulator (founder ruling Q19)."""
from datetime import datetime, timedelta, timezone
import json
import os
import re
import signal
import subprocess
import sys
import uuid

from google.api_core.exceptions import InvalidArgument, NotFound
from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, KeySet
import pytest

from brandme_core.domains.base import CommandContext, Principal, run_idempotent_command
from brandme_core.domains.media.store import MemoryMediaStore
from brandme_core.domains.persona.lane import register_consumer_domains
from brandme_core.domains.privacy import deletion as pd
from brandme_core.domains.privacy.privacy import MyDataService
from brandme_core.events import EventEnvelope, registry, write_events
from brandme_core.events import erasure, retention
from brandme_core.events.catalogs import load_catalogs
from brandme_core.events.outbox import OutboxDispatcher, json_payload, shard_for
from brandme_core.events.retention import (
    NIL_SUBJECT, RetentionConfig, SweepResult, erase_subject_events, erase_subject_requests, matchable,
    purge_delivered, subject_keys, sweep_erased_subjects, unlinked, verify_schema,
)
from .conftest import requires_spanner
# A helper only, never a test_* name (that would collect that module's tests twice).
from .test_outbox_lane_catalogs import example

COLUMNS = ("shard", "event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version",
           "occurred_at", "environment", "actor_ref", "correlation_id", "causation_id", "privacy_class", "payload",
           "status", "attempts", "next_attempt_at", "lease_owner", "lease_expires_at", "delivered_at", "last_error",
           "created_at")
DAY = timedelta(days=1)
MEMBER_NIL = f"member:{NIL_SUBJECT}"


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


@pytest.fixture
def db(migrated_database):
    with migrated_database.batch() as batch:
        # DeletionJobs cascades to DeletionSteps (V009).
        for table in ("OutboxEvents", "IdempotencyRecords", "DeletionTombstones", "DeletionJobs", "ProcessingFreezes",
                      "RestoreRuns"):
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


def job(db, subject, scope="account", categories=("platform.event_outbox",)):
    """A DeletionJobs row (V009) as request_deletion writes it; returns its id."""
    job_id = uid()
    db.run_in_transaction(lambda tx: tx.insert(
        "DeletionJobs", ("job_id", "subject_ref", "scope", "categories", "state", "reauth_at", "requested_at", "version"),
        [(job_id, subject, scope, list(categories), "completed", now(), now(), 2)]))
    return job_id


def tombstone(db, subject, category, created_at=COMMIT_TIMESTAMP, record_keys=(), scope="account", job_id=None):
    """A tombstone and, unless ``job_id`` is given, the deletion job it belongs to."""
    job_id = job_id or job(db, subject, scope, [category])
    db.run_in_transaction(lambda tx: tx.insert(
        "DeletionTombstones", ("subject_ref", "category", "tombstone_id", "deletion_job_id", "record_keys", "created_at"),
        [(subject, category, uid(), job_id, list(record_keys), created_at)]))


class Store:
    """Object store for MyDataService; these tests never export a package."""

    def put(self, key, data, content_type):
        raise AssertionError("no export expected")

    def delete(self, key):
        pass


def service(db, *, consumer_domains=False):
    reg = pd.PrivacyRegistry()
    if consumer_domains:
        register_consumer_domains(reg, database=db, media_store=MemoryMediaStore())
    assert erasure.register_platform_privacy(reg) is erasure.PLATFORM_PRIVACY_HANDLER
    return MyDataService(db, Store(), reg, environment="development")


# --- subject keys --------------------------------------------------------------


def test_subject_keys_cover_actor_and_bare_forms_and_refuse_unsafe_refs():
    m = uid()
    assert subject_keys(m) == subject_keys(f"member:{m}") == (m, f"member:{m}")
    assert subject_keys("m9") == ("m9",) and matchable("m9") and matchable(m)
    for bad in ("", "a b", 'a"b', "a\\b", "oidc|subject-123", "x" * 129, None, 9):
        assert not matchable(bad)
        with pytest.raises(ValueError):
            subject_keys(bad)
    for erase, nothing in ((erase_subject_events, (0, 0, 0)), (erase_subject_requests, (0, 0))):
        with pytest.raises(TypeError):
            erase(None, "m9")  # one string is not a list of subjects
        assert erase(None, []) == nothing


def test_unlinking_rewrites_whole_string_values_only():
    a, b, c = uid(), uid(), uid()
    nil = {a: NIL_SUBJECT, f"member:{a}": MEMBER_NIL, b: NIL_SUBJECT}
    body = {"by": {a: "yes", b: "pass"}, "ids": [c, a, b], "owner": f"member:{a}", "note": f'say "{a}', "n": 2,
            "nested": [{"id": a}, None, True]}
    assert unlinked(body, nil) == ({"by": {a: "yes", b: "pass"}, "ids": [c, NIL_SUBJECT], "owner": MEMBER_NIL,
                                    "note": f'say "{a}', "n": 2, "nested": [{"id": NIL_SUBJECT}, None, True]}, True)
    # A list keeps one nil member, also next to one erased earlier, so unique ids stay unique.
    assert unlinked([NIL_SUBJECT, c, a], nil) == ([NIL_SUBJECT, c], True)
    assert unlinked({"by": {a: 1}, "ids": [c]}, nil) == ({"by": {a: 1}, "ids": [c]}, False)


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
def test_erasure_withdraws_and_deletes_own_events_and_unlinks_everyone_elses(db):
    s, other, x = uid(), uid(), uid()
    lease = now() + timedelta(seconds=300)
    withdrawn = [  # the subject's own events, by actor (and its delegations) or by aggregate
        put(db, actor=f"member:{s}", payload={"member_id": s}, causation=uid()),
        put(db, status="leased", actor=f"member:{s}", lease=lease),
        put(db, status="dead", aggregate=s, last_error="message_rejected"),
    ]
    deleted = [put(db, status="delivered", delivered=now(), aggregate=s),
               put(db, status="delivered", delivered=now(), actor=f"member:{s}/delegation:{uid()}")]
    # Other members' and services' events that name the subject keep their row and status, in every status.
    unlinked_to = {
        put(db, payload={"member_a": other, "member_b": s}, actor=f"member:{other}"):
            {"member_a": other, "member_b": NIL_SUBJECT},
        put(db, status="leased", lease=lease, payload={"owner": f"member:{s}"}, actor=f"member:{other}"):
            {"owner": MEMBER_NIL},
        put(db, status="delivered", delivered=now(), payload={"ids": [x, s]}): {"ids": [x, NIL_SUBJECT]},
        put(db, status="dead", last_error="delivery_attempts_exhausted", actor="service:rewards",
            payload={"member_id": s}): {"member_id": NIL_SUBJECT},
    }
    untouched = [put(db, payload={"member_id": other}, actor=f"member:{other}"),
                 put(db, status="delivered", delivered=now(), aggregate=other),
                 put(db, payload={"tally": {s: 1}}, actor=f"member:{other}")]  # an object key is never rewritten
    before = rows(db)
    started = now() - timedelta(seconds=5)
    assert erase_subject_events(db, [s]) == (len(withdrawn), len(deleted), len(unlinked_to))
    after = rows(db)
    assert set(after) == set(withdrawn) | set(unlinked_to) | set(untouched)
    for event_id in withdrawn:
        r = after[event_id]
        assert (r["status"], r["last_error"], r["payload"], r["actor_ref"]) == ("dead", "subject_erased", {}, "service:privacy")
        assert r["aggregate_id"] == r["correlation_id"] == event_id and r["causation_id"] is None
        assert r["lease_owner"] is None and r["lease_expires_at"] is None and r["next_attempt_at"] >= started
        assert r["event_type"] == before[event_id]["event_type"] and r["occurred_at"] == before[event_id]["occurred_at"]
    for event_id, payload in unlinked_to.items():
        assert after[event_id] == {**before[event_id], "payload": payload}  # status, lease and references unchanged
    assert all(after[e] == before[e] for e in untouched)
    assert erase_subject_events(db, [s]) == (0, 0, 0)
    assert erase_subject_events(db, [f"member:{s}"]) == (0, 0, 0)


@requires_spanner
def test_short_refs_match_whole_json_values_never_substrings(db):
    withdrawn = [put(db, actor="member:m9/delegation:d1"), put(db, aggregate="m9")]
    named = put(db, payload={"recipient_ids": ["m1", "m9"]})
    m99 = [put(db, payload={"member_id": "m99"}), put(db, payload={"note": "am9x", "m": "m9 ", "q": '"m9'}),
           put(db, payload={"votes": {"m9": "yes"}}), put(db, actor="member:m99/delegation:d1"),
           put(db, actor="member:m9x"), put(db, aggregate="m99")]
    assert erase_subject_events(db, ["m9"]) == (2, 0, 1)
    after = rows(db)
    assert all(after[e]["last_error"] == "subject_erased" for e in withdrawn)
    assert after[named]["status"] == "pending" and after[named]["payload"] == {"recipient_ids": ["m1", NIL_SUBJECT]}
    assert all(after[e]["status"] == "pending" and after[e]["last_error"] is None for e in m99)
    assert after[m99[2]]["payload"] == {"votes": {"m9": "yes"}}


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
    assert erase_subject_events(db, [m]) == (1, 0, 0)
    # The copy already claimed still names the member: a delivery in flight may reach the broker (README discloses it).
    assert m in json.dumps(json_payload(claimed["payload"]))
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
def test_unlinking_never_collapses_object_keys_naming_two_erased_subjects(db):
    """probe_dupkeys: text REPLACE + PARSE_JSON turned both keys into the nil member and kept one."""
    a, b, other = uid(), uid(), f"member:{uid()}"
    votes = {"votes": {a: "yes", b: "pass"}}
    replay(db, other, votes, "decisions.results")
    replay(db, other, {"voters": [a, b], "note": f'"{a}'}, "decisions.voters")
    event = put(db, actor=other, payload={"tally": {a: 1, b: 2}, "ids": [b]})
    assert erase_subject_requests(db, [a, b]) == (0, 1)
    assert dict((op, json.loads(body)) for _, op, body in replays(db)) == {
        "decisions.results": votes, "decisions.voters": {"voters": [NIL_SUBJECT], "note": f'"{a}'}}
    assert erase_subject_events(db, [a, b]) == (0, 0, 1)
    assert rows(db)[event]["payload"] == {"tally": {a: 1, b: 2}, "ids": [NIL_SUBJECT]}


@requires_spanner
def test_erasure_batches_more_than_one_hundred_subjects(db):
    many = [uid() for _ in range(150)]  # 300 keys: three batches per table
    own = [put(db, aggregate=m) for m in many[::30]]
    named = put(db, actor=f"member:{uid()}", payload={"ids": many[:3]})
    for m in many[::50]:
        replay(db, f"member:{m}", {"ok": True})
    other = f"member:{uid()}"
    replay(db, other, {"recipients": many[:3]})
    withdrawn, deleted, changed = erase_subject_events(db, many)
    # A body naming subjects from several batches is unlinked (and counted) once per batch.
    assert (withdrawn, deleted) == (len(own), 0) and 1 <= changed <= 3
    assert rows(db)[named]["payload"] == {"ids": [NIL_SUBJECT]}  # one nil member per list
    deleted, changed = erase_subject_requests(db, many)
    assert deleted == 3 and 1 <= changed <= 3
    assert replays(db) == [(other, "op", json.dumps({"recipients": [NIL_SUBJECT]}))]
    assert erase_subject_events(db, many) == (0, 0, 0) and erase_subject_requests(db, many) == (0, 0)


@requires_spanner
def test_sweep_reerases_only_recent_account_deletions_of_platform_categories(db):
    swept, narrowed, other_category, expired, category_only, orphan = (uid() for _ in range(6))
    tombstone(db, swept, "platform.event_outbox")
    tombstone(db, swept, "platform.request_replay")
    tombstone(db, narrowed, "platform.event_outbox", record_keys=("k1",))
    tombstone(db, other_category, "wardrobe.items")
    tombstone(db, expired, "platform.request_replay", created_at=now() - 31 * DAY)
    for category in erasure.CATEGORIES:
        tombstone(db, category_only, category, scope="category")  # an active member's category-only request
    tombstone(db, orphan, "platform.event_outbox", job_id=uid())  # no deletion job: scope unknown, never swept
    tombstone(db, "oidc|subject-123", "platform.event_outbox")  # refused at deletion; skipped, never raises
    late = [put(db, actor=f"member:{swept}", payload={"member_id": swept}),
            put(db, status="delivered", delivered=now(), actor=f"member:{swept}"),
            put(db, actor=f"member:{category_only}", payload={"member_id": swept})]
    kept = [put(db, actor=f"member:{m}", payload={"member_id": m})
            for m in (narrowed, other_category, expired, category_only, orphan)]
    for m in (swept, expired, category_only, orphan):
        replay(db, f"member:{m}", {"ok": True})
    assert sweep_erased_subjects(db, now()) == SweepResult(
        subjects=1, withdrawn=1, deleted=1, unlinked=1, requests_deleted=1, requests_unlinked=0)
    after = rows(db)
    assert set(after) == {late[0], late[2], *kept} and after[late[0]]["last_error"] == "subject_erased"
    assert after[late[2]]["payload"] == {"member_id": NIL_SUBJECT}
    assert all(after[e]["status"] == "pending" and after[e]["last_error"] is None for e in kept)
    assert sorted(p for p, _, _ in replays(db)) == sorted(f"member:{m}" for m in (expired, category_only, orphan))
    assert sweep_erased_subjects(db, now()) == SweepResult(subjects=1)


# --- privacy handler -----------------------------------------------------------


@requires_spanner
def test_other_members_events_survive_a_respondents_erasure_and_stay_valid(db):
    """probe_collateral: erasing one respondent withdrew the creator's decision.closed, so nobody was credited."""
    load_catalogs()  # registers decision.closed (consumer-domains catalog)
    creator, gone, also_gone, r2 = (uid() for _ in range(4))
    ids = sorted([gone, also_gone, r2])
    ev = EventEnvelope(event_type="decision.closed", schema_version="1", aggregate_type="decision", aggregate_id=uid(),
                       aggregate_version=3, environment="development", actor_ref=f"member:{creator}",
                       correlation_id=uid(), privacy_class="member_private",
                       payload={"decision_id": uid(), "creator_id": creator, "close_reason": "expired",
                                "eligible_respondent_ids": ids, "repeat_request": False, "zero_replies": False})
    db.run_in_transaction(lambda tx: write_events(tx, [ev]))
    assert erase_subject_events(db, [gone]) == (0, 0, 1)
    assert rows(db)[ev.event_id]["payload"]["eligible_respondent_ids"] == [NIL_SUBJECT if x == gone else x for x in ids]
    # A second respondent's erasure keeps the uniqueItems list valid: one nil member, r2 kept in place.
    assert erase_subject_events(db, [also_gone]) == (0, 0, 1)
    r = rows(db)[ev.event_id]
    assert (r["status"], r["actor_ref"], r["last_error"]) == ("pending", f"member:{creator}", None)
    assert sorted(r["payload"]["eligible_respondent_ids"]) == sorted([NIL_SUBJECT, r2])
    published = []
    result = OutboxDispatcher(db, published.append, environment="development", base_backoff_seconds=0,
                              max_backoff_seconds=0).run_once()
    assert (result.delivered, result.dead) == (1, 0) and [e.event_id for e in published] == [ev.event_id]
    assert gone not in json.dumps(published[0].to_wire()) and r2 in published[0].payload["eligible_respondent_ids"]


MEMBER_FIELD = re.compile(r"member|^(owner|creator|requester|recipient|blocker|blocked|proposer|author|"
                          r"respondent|eligible_respondent)_ids?$")


def fields(schema):
    for name, sub in schema.get("properties", {}).items():
        yield name, sub
        yield from fields(sub)
        yield from fields(sub.get("items", {}))


def uuid_typed(schema):
    schema = schema.get("items", schema)
    return schema.get("format") == "uuid" or any(b.get("format") == "uuid" for b in schema.get("anyOf", []))


def named(schema, s):
    """A valid instance naming ``s`` at every member-id position (every format-uuid value), all properties set."""
    if "anyOf" in schema:
        branch = next((b for b in schema["anyOf"] if b.get("format") == "uuid"), None)
        return named(branch, s) if branch else example(schema, "named")
    if schema.get("type") == "object":
        return {k: named(sub, s) for k, sub in schema["properties"].items()}
    if schema.get("type") == "array" and schema["items"].get("format") == "uuid":
        return [s, uid()][:schema.get("maxItems", 2)]
    if schema.get("format") == "uuid":
        return s
    return example(schema, "named")


@requires_spanner
def test_unlinked_payloads_still_satisfy_every_registered_contract(db):
    """Nil member ids pass format uuid and every closed schema, so unlinked events are still delivered."""
    load_catalogs()
    # Every member-id field is format uuid, so naming s at every uuid position covers each of them.
    loose = [f"{t.event_type}.{name}" for t in registry.types() for name, sub in fields(t.payload_schema)
             if MEMBER_FIELD.search(name) and not uuid_typed(sub)]
    assert not loose
    s, other = uid(), uid()
    contracts = [t for t in registry.types() if s in json.dumps(named(t.payload_schema, s))]
    events = [EventEnvelope(event_type=t.event_type, schema_version=t.schema_version, aggregate_type="unlink_probe",
                            aggregate_id=uid(), aggregate_version=1, environment="development",
                            actor_ref=f"member:{other}", correlation_id=uid(), privacy_class=t.privacy_class,
                            payload=named(t.payload_schema, s)) for t in contracts]
    db.run_in_transaction(lambda tx: write_events(tx, events))  # validates every payload naming s
    types = {e.event_type for e in events}
    assert len(events) >= 50, sorted(types)
    assert {"decision.closed", "relationship.accepted", "outfit.proposal.accepted", "member.blocked",
            "decision.responded", "commerce.order.observed"} <= types, sorted(types)
    assert erase_subject_events(db, [s]) == (0, 0, len(events))
    after = rows(db)
    for e in events:
        assert after[e.event_id]["payload"] == json.loads(json.dumps(e.payload).replace(s, NIL_SUBJECT)), e.event_type
    published = []
    result = OutboxDispatcher(db, published.append, environment="development", batch_size=100,
                              base_backoff_seconds=0, max_backoff_seconds=0).run_once()
    # The dispatcher re-validates each claimed row against its registered contract (outbox.py:201-204).
    assert (result.delivered, result.dead, result.failed) == (len(events), 0, 0)
    assert all(s not in json.dumps(e.to_wire()) for e in published)


@requires_spanner
def test_platform_handler_exports_metadata_only_and_refuses_what_it_cannot_erase(db):
    m, friend, odd = uid(), uid(), "oidc|subject-123"
    put(db, actor=f"member:{m}", payload={"member_id": m, "title": "Linen shirt"})
    put(db, actor=f"member:{friend}", payload={"reported_id": m})  # someone else's event about the member
    replay(db, f"member:{m}", {"title": "Linen shirt"})
    handler = erasure.PLATFORM_PRIVACY_HANDLER
    ctx = pd.SubjectContext(subject_ref=m, job_id=job(db, m), requested_at=now())
    odd_ctx = pd.SubjectContext(subject_ref=odd, job_id=job(db, odd), requested_at=now())
    with db.snapshot(multi_use=True) as snap:
        events = handler.export(snap, ctx, "platform.event_outbox")
        requests = handler.export(snap, ctx, "platform.request_replay")
        assert handler.export(snap, odd_ctx, "platform.event_outbox").records == []  # exact matches; never raises
    assert [sorted(r) for r in events.records] == [["event_type", "occurred_at", "status"]] and events.notes
    assert [sorted(r) for r in requests.records] == [["created_at", "expires_at", "operation"]]
    assert "Linen shirt" not in json.dumps(events.records + requests.records) and friend not in json.dumps(events.records)
    refused = [
        (erasure.RECORD_LEVEL_REFUSED, pd.SubjectContext(subject_ref=m, job_id=ctx.job_id, requested_at=now(),
                                                         record_keys=("one",))),
        (erasure.ACCOUNT_SCOPE_REFUSED, pd.SubjectContext(
            subject_ref=m, job_id=job(db, m, "category", erasure.CATEGORIES), requested_at=now())),
        (erasure.ACCOUNT_SCOPE_REFUSED, pd.SubjectContext(subject_ref=m, job_id=uid(), requested_at=now())),  # no job
        (erasure.UNMATCHABLE_REFUSED, odd_ctx),
    ]
    before = (rows(db), replays(db))
    for reason, narrowed in refused:
        for key in erasure.CATEGORIES:
            out = handler.delete_outside_txn(db, narrowed, key)
            assert (out.rows_affected, out.done, out.exception) == (0, True, reason)
    assert (rows(db), replays(db)) == before  # a refused request touches nothing
    with pytest.raises(RuntimeError):
        handler.delete(None, ctx, "platform.event_outbox")
    out = handler.delete_outside_txn(db, ctx, "platform.event_outbox")
    assert (out.rows_affected, out.done, out.exception) == (2, True, None)
    assert out.detail == "1 undelivered withdrawn, 0 delivered deleted, 1 other events unlinked"
    assert handler.purge_derived(ctx, "platform.event_outbox").detail == erasure.BROKER_COPIES


@requires_spanner
def test_foundation_catalog_callbacks_erase_only_for_an_account_deletion(db):
    """The bridge's callbacks get only a member id and cannot report a refusal: a no-op unless the account is deleted."""
    from brandme_core.domains import data_categories

    m = uid()
    event = put(db, actor=f"member:{m}", payload={"member_id": m})
    replay(db, f"member:{m}", {"ok": True})
    job(db, m, "category", erasure.CATEGORIES)
    platform = [c for c in data_categories() if c.domain == "platform"]
    for c in platform:
        c.delete(db, m)
        c.delete(db, "oidc|subject-123")  # never raises
    assert rows(db)[event]["status"] == "pending" and len(replays(db)) == 1
    job(db, m, "account")
    for c in platform:
        c.delete(db, m)
    assert rows(db)[event]["last_error"] == "subject_erased" and replays(db) == []


def principal(member_id):
    return Principal(member_id=member_id, subject="s", session_id=None, client_id=None, scopes=frozenset(),
                     assurance_level="aal1", environment="development")


@requires_spanner
def test_category_scoped_platform_deletion_is_refused_and_never_swept(db):
    """probe_scope and probe_replay: a category-only request kept erasing an active member for 30 days."""
    m = uid()
    svc = service(db)
    executed = []
    privacy_class = registry.get("member.updated", "1").privacy_class

    def command(tx, ctx):
        executed.append(1)
        ctx.emit("member.updated", "1", "member", m, len(executed) + 1,
                 {"member_id": m, "changed_fields": ["display_name"]}, privacy_class)
        return {"member_id": m}

    def replayed(key):
        return run_idempotent_command(db, CommandContext(principal(m), "development"), "members.update", key,
                                      {"n": 1}, command)[1]

    earlier, later = "k-earlier-" + uuid.uuid4().hex, "k-later-" + uuid.uuid4().hex
    assert replayed(earlier) is False  # an in-window record and a pending event from before the requests
    receipts = [svc.run_deletion(svc.request_deletion(m, now(), categories=[c])) for c in erasure.CATEGORIES]
    for category, receipt in zip(erasure.CATEGORIES, receipts):
        r = receipt["categories"][category]
        assert (r["status"], r["reason"], r["rows_affected"]) == ("exception", erasure.ACCOUNT_SCOPE_REFUSED, 0)
        assert receipt["processing"].startswith("Category processing may resume")
    with db.snapshot() as snap:
        assert [s for (s,) in snap.execute_sql("SELECT state FROM DeletionJobs")] == ["completed_with_exceptions"] * 2
    # The member keeps using the app: a new command, with its event and replay record.
    assert replayed(earlier) is True and replayed(later) is False
    assert sweep_erased_subjects(db, now()) == SweepResult()
    assert replayed(earlier) is True and replayed(later) is True and len(executed) == 2  # never run twice

    def own():
        return sorted(r["status"] for r in rows(db).values() if r["actor_ref"] == f"member:{m}")

    assert own() == ["pending", "pending"] and len(replays(db)) == 2
    # A restore re-applies the refused tombstones as no-ops and serves again.
    restored = svc.reapply_tombstones_after_restore("dev-backup-before-requests", now() - DAY)
    assert (restored["tombstones_applied"], restored["rows_redeleted"]) == (2, 0)
    svc.assert_serving()
    assert own() == ["pending", "pending"] and len(replays(db)) == 2 and replayed(later) is True


@requires_spanner
def test_unmatchable_subject_ref_is_refused_without_blocking_the_job(db):
    """probe_ref: the platform step raised, so the job stayed running and later categories were never deleted."""
    svc = service(db, consumer_domains=True)
    job_id = svc.request_deletion("oidc|subject-123", now())
    receipt = svc.run_deletion(job_id)
    statuses = {k: (r["status"], r.get("reason")) for k, r in receipt["categories"].items()}
    platform = {k: v for k, v in statuses.items() if k.startswith("platform.")}
    assert platform == {c: ("exception", erasure.UNMATCHABLE_REFUSED) for c in erasure.CATEGORIES}
    rest = {k: s for k, (s, _) in statuses.items() if k not in platform}
    assert any(k > "platform." for k in rest) and set(rest.values()) == {"deleted"}, rest
    with db.snapshot() as snap:
        assert list(snap.execute_sql("SELECT state FROM DeletionJobs")) == [["completed_with_exceptions"]]
    assert svc.run_deletion(job_id) == receipt
    assert sweep_erased_subjects(db, now()) == SweepResult()
    restored = svc.reapply_tombstones_after_restore("dev-backup-before-deletion", now() - DAY)
    assert restored["tombstones_applied"] == len(statuses)
    svc.assert_serving()


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
    late = put(db, actor=f"member:{member}", payload={"member_id": member})
    once = cli("--once", env=env)
    assert once.returncode == 0, once.stdout + once.stderr
    record = json.loads(once.stdout.splitlines()[-1])
    assert record == {"status": "retention", "purged": 1, "subjects": 1, "withdrawn": 1, "deleted": 0, "unlinked": 0,
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
