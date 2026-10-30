"""Account deletion leaves no outbox or replay row naming the member (founder ruling Q19).

Joint proof with the privacy orchestrator (``MyDataService.request_deletion`` and
``run_deletion``, brandme_core/domains/privacy). The consumer-domains seed
(tests/test_persona_lane_mydata.py ``seed``) writes real rows through the five
domain services, and the friend closes a decision the member and another friend
answered. Part of the outbox is delivered, one event is dead-lettered, one stays
leased and the rest are pending. ``MyDataService`` then deletes the account with
the consumer handlers and foundation's platform handler, and a trace over every
table and column proves that no OutboxEvents or IdempotencyRecords row still names
the member, whichever path the row was on. The member's own events are withdrawn
or deleted; other members' rows survive with the member unlinked, so the friend's
decision still credits the other respondent. Late writes are swept, old delivered
rows are purged and a restore from an older backup is cleaned again. Without the
platform handler the same trace finds the original leak (at least 21 outbox rows).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import uuid

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, param_types
import pytest

from brandme_core.domains.media.providers import SimulatedTryOnProvider
from brandme_core.domains.media.store import MemoryMediaStore
from brandme_core.domains.persona.kernel import member_principal
from brandme_core.domains.persona.lane import register_consumer_domains
from brandme_core.domains.privacy import deletion as pd
from brandme_core.domains.privacy.privacy import MyDataService
from brandme_core.domains.rewards.consumer import RewardsConsumer
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.events import EventEnvelope, write_events
from brandme_core.events.erasure import register_platform_privacy
from brandme_core.events.outbox import OutboxDispatcher, PermanentDeliveryError, shard_for
from brandme_core.events.retention import NIL_SUBJECT, SweepResult, purge_delivered, sweep_erased_subjects
# Helpers only, never test_* names (that would collect the lane's tests twice).
from test_persona_harness import count, insert_member, new_migrated_database
from test_persona_lane_mydata import WRITER, MemoryObjectStore, key, seed

from .conftest import requires_spanner

# The privacy lane's own ledger: member id + category + time, kept so deletions
# can be re-applied after a restore and racing jobs are refused (V009, V003).
RETAINED_LEDGER = frozenset({"DeletionJobs", "DeletionSteps", "DeletionTombstones", "ProcessingFreezes",
                             "PersonaTombstones", "RestoreRuns"})
# Out of Q9 scope: no handler erases the identity rows yet. Open founder question:
# docs/build/status/opus-foundation.md, round 4, founder flag F-identity (identity-table
# erasure). Until it is ruled they are expected survivors, listed here and never silently ignored.
IDENTITY_SURVIVORS = frozenset({"Members", "MemberSettings", "MemberIdentities", "ConsentGrants", "Sessions"})
# Independent of retention.py's SQL: any column containing the id at all.
NAMES = "(STRPOS(aggregate_id, @m) > 0 OR STRPOS(actor_ref, @m) > 0 OR STRPOS(TO_JSON_STRING(payload), @m) > 0)"
# The member's own events: their aggregate, or their actor and its delegations.
OWN = "(aggregate_id = @m OR actor_ref = CONCAT('member:', @m) OR STARTS_WITH(actor_ref, CONCAT('member:', @m, '/')))"
# relationship.accepted is the friend's event naming the member: delivered, then unlinked in place.
DELIVERED = ("wardrobe.item.created", "persona.updated", "reward.posted", "decision.opened", "relationship.accepted")


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def database():
    db = new_migrated_database()
    yield db
    try:
        db.drop()
    except Exception:
        pass


def traces(db, member_id):
    """Every column of every table, except the privacy ledger, that still contains the member id."""
    found = {}
    with db.snapshot(multi_use=True) as s:
        conds: dict[str, dict[str, str]] = {}
        for table, col, typ in s.execute_sql("SELECT table_name, column_name, spanner_type FROM INFORMATION_SCHEMA.COLUMNS "
                                             "WHERE table_schema = ''"):
            if typ.startswith("STRING"):
                conds.setdefault(table, {})[col] = f"STRPOS({col}, @m) > 0"
            elif typ.startswith("ARRAY<STRING"):
                conds.setdefault(table, {})[col] = f"EXISTS(SELECT 1 FROM UNNEST({col}) AS x WHERE STRPOS(x, @m) > 0)"
            elif typ == "JSON":
                conds.setdefault(table, {})[col] = f"STRPOS(TO_JSON_STRING({col}), @m) > 0"
        assert set(conds) >= {"OutboxEvents", "IdempotencyRecords", "Members", "WardrobeItems", *RETAINED_LEDGER}
        for table, by_col in conds.items():
            if table in RETAINED_LEDGER:
                continue
            counts = list(s.execute_sql(f"SELECT {', '.join(f'COUNTIF({c})' for c in by_col.values())} FROM {table}",
                                        params={"m": member_id}, param_types={"m": param_types.STRING}))[0]
            found.update({f"{table}.{col}": n for col, n in zip(by_col, counts) if n})
    return found


def leaked_tables(found):
    return {k.split(".")[0] for k in found} - IDENTITY_SURVIVORS


def outbox(db, where="TRUE", **params):
    with db.snapshot() as s:
        return {r[0]: r[1:] for r in s.execute_sql(
            f"SELECT event_id, event_type, status, last_error FROM OutboxEvents WHERE {where}", params=params,
            param_types={k: param_types.STRING for k in params})}


def table(db, name):
    with db.snapshot() as s:
        it = s.execute_sql(f"SELECT * FROM {name}")
        data = [list(r) for r in it]
        return [f.name for f in it.fields], data


def replace_rows(db, name, cols, data):
    db.run_in_transaction(lambda t: t.replace(name, columns=cols, values=data))


def raise_permanent(_ev):
    raise PermanentDeliveryError()


def dispatcher(db, deliver, types=None, **kw):
    return OutboxDispatcher(db, deliver, environment="development", event_types=types, base_backoff_seconds=0,
                            max_backoff_seconds=0, **kw)


def friend_decision(db, gone, friend, f_item):
    """The friend asks the member and a second friend; both answer and the friend closes it.

    Leaves the friend's pending decision.closed naming both respondents; the
    rewards consumer credits each eligible respondent (rewards/consumer.py:159-170).
    """
    other = member_principal(insert_member(db), WRITER)
    rel = RelationshipService(db)
    rel.accept(friend, rel.request(other, friend.member_id)["relationship_id"])
    decisions = DecisionService(db)
    d = decisions.create(friend, {"subject_type": "wardrobe_item", "subject_id": f_item, "prompt": "Scarf with the coat?",
                                  "recipient_ids": [gone.member_id, other.member_id], "duration_seconds": 300,
                                  "discussion_mode": "open"}, key())
    for respondent in (gone, other):
        decisions.respond(respondent, d["decision_id"], {"choice": "yes", "note": "Yes"})
    decisions.close(friend, d["decision_id"])
    return other


@requires_spanner
def test_account_deletion_leaves_no_outbox_or_replay_row_naming_the_member(database):
    db = database
    store, provider = MemoryMediaStore(), SimulatedTryOnProvider()
    gone, friend, f_item, *_ = seed(db, store, provider)
    other = friend_decision(db, gone, friend, f_item)
    m, f = gone.member_id, friend.member_id
    friend_only = set(outbox(db, f"{NAMES.replace('@m', '@f')} AND NOT {NAMES}", m=m, f=f))
    assert friend_only, "the friend needs outbox rows that do not name the member"
    (closed_id,) = outbox(db, "event_type = 'decision.closed' AND actor_ref = @a", a=f"member:{f}")

    # Delivered subset, one dead letter, one lease in flight, the rest pending.
    published = []
    assert dispatcher(db, published.append, DELIVERED).run_once().delivered == len(published) >= 6
    assert dispatcher(db, raise_permanent, ["share.created"]).run_once().dead == 1
    in_flight = dispatcher(db, published.append, ["outfit.version.created"], lease_seconds=300)
    (leased_id,) = outbox(db, "event_type = 'outfit.version.created'")
    leased = in_flight._claim(shard_for(leased_id))
    named = outbox(db, NAMES, m=m)
    own = set(outbox(db, OWN, m=m))
    others = {e: v for e, v in named.items() if e not in own}  # other members' rows that name the member
    by_status = {s: sum(1 for e, (_, st, _) in named.items() if st == s and e in own)
                 for s in ("delivered", "dead", "leased", "pending")}
    others_by_status = {s: sum(1 for _, st, _ in others.values() if st == s) for s in ("delivered", "pending")}
    assert len(named) >= 21 and own <= set(named) and all(by_status.values()), by_status
    assert all(others_by_status.values()) and closed_id in others, others_by_status
    assert count(db, "SELECT COUNT(*) FROM IdempotencyRecords WHERE STARTS_WITH(principal_ref, @p)", p=f"member:{m}") == 7
    assert count(db, "SELECT COUNT(*) FROM IdempotencyRecords WHERE STRPOS(TO_JSON_STRING(response_body), @m) > 0 "
                     "AND principal_ref = @p", m=m, p=f"member:{f}") == 2  # the friend's two decisions name the member
    backup_at = now()
    backup = {name: table(db, name) for name in ("OutboxEvents", "IdempotencyRecords")}
    with db.snapshot() as s:
        actor_before = {e: a for e, a in s.execute_sql("SELECT event_id, actor_ref FROM OutboxEvents")}

    reg = pd.PrivacyRegistry()
    register_consumer_domains(reg, database=db, media_store=store)
    assert register_platform_privacy(reg) is not None
    svc = MyDataService(db, MemoryObjectStore(), reg, environment="development")
    job = svc.request_deletion(m, now())
    receipt = svc.run_deletion(job)
    statuses = {k: r["status"] for k, r in receipt["categories"].items()}
    assert statuses == {c.key: "deleted" for c in reg.categories()}
    for category in ("platform.event_outbox", "platform.request_replay"):
        assert receipt["categories"][category]["rows_affected"] > 0, category
    assert receipt["categories"]["platform.event_outbox"]["rows_affected"] == len(named)
    with db.snapshot() as s:
        detail = list(s.execute_sql(
            "SELECT detail FROM DeletionSteps WHERE job_id = @j AND category = 'platform.event_outbox' AND step = 'delete_records'",
            params={"j": job}, param_types={"j": param_types.STRING}))[0][0]
    assert detail == (f"{len(own) - by_status['delivered']} undelivered withdrawn, {by_status['delivered']} delivered "
                      f"deleted, {len(others)} other events unlinked")

    # Zero rows name the member on either path; only the identity rows remain.
    found = traces(db, m)
    assert leaked_tables(found) == set(), found
    assert not any(k.startswith(("OutboxEvents.", "IdempotencyRecords.")) for k in found)
    assert "Members.member_id" in found  # the trace does reach foundation tables
    withdrawn = outbox(db, "last_error = 'subject_erased'")
    assert set(withdrawn) == {e for e in own if named[e][1] != "delivered"}
    assert all(st == "dead" for _, st, _ in withdrawn.values())
    # Other members' rows survive in place, delivered or not, with the member unlinked.
    with db.snapshot() as s:
        kept = {r[0]: r[1:] for r in s.execute_sql(
            "SELECT event_id, status, actor_ref, TO_JSON_STRING(payload) FROM OutboxEvents WHERE event_id IN UNNEST(@ids)",
            params={"ids": list(others)}, param_types={"ids": param_types.Array(param_types.STRING)})}
    assert set(kept) == set(others)
    for event_id, (status, actor, payload) in kept.items():
        assert (status, actor) == (others[event_id][1], actor_before[event_id]) and NIL_SUBJECT in payload, event_id

    # The in-flight delivery cannot finish; the privacy events are untouched and deliverable.
    assert in_flight._finish(leased, None) == "stale"
    privacy = outbox(db, "STARTS_WITH(event_type, 'privacy.deletion.')")
    assert sorted(t for t, _, _ in privacy.values()) == ["privacy.deletion.completed", "privacy.deletion.requested"]
    assert all(st == "pending" for _, st, _ in privacy.values())
    pending_friend = {e for e in friend_only if outbox(db)[e][1] == "pending"}
    pending_others = {e for e, (_, st, _) in others.items() if st == "pending"}
    later = []
    result = dispatcher(db, later.append).run_once()
    assert result.failed == result.dead == result.stale == 0
    # Everything still pending is delivered, unlinked rows included; no withdrawn row is ever claimed or published.
    assert {e.event_id for e in later} == set(privacy) | pending_friend | pending_others
    assert all(m not in json.dumps(e.to_wire()) for e in later)

    # The friend's decision still credits the other respondent; the nil member is skipped.
    (closed,) = [e for e in later if e.event_id == closed_id]
    assert sorted(closed.payload["eligible_respondent_ids"]) == sorted([NIL_SUBJECT, other.member_id])
    assert RewardsConsumer(db).handle(closed)["status"] == "processed"
    assert count(db, "SELECT COUNT(*) FROM RewardEntries WHERE member_id = @o AND rule_id = 'friend_decision_response' "
                     "AND state = 'posted' AND points = 10", o=other.member_id) == 1
    assert count(db, "SELECT COUNT(*) FROM RewardEntries WHERE member_id = @m OR member_id = @nil",
                 m=m, nil=NIL_SUBJECT) == 0

    # The friend's own records survive; their replay bodies are unlinked, not deleted.
    assert friend_only <= set(outbox(db))
    assert count(db, "SELECT COUNT(*) FROM WardrobeItems WHERE member_id = @f", f=f) == 1
    with db.snapshot() as s:
        bodies = [json.dumps(json.loads(b)) for (b,) in s.execute_sql(
            "SELECT TO_JSON_STRING(response_body) FROM IdempotencyRecords WHERE principal_ref = @p",
            params={"p": f"member:{f}"}, param_types={"p": param_types.STRING})]
    assert len(bodies) == 3 and sum(NIL_SUBJECT in b for b in bodies) == 2 and not any(m in b for b in bodies)

    # A late write by an unguarded writer (gateway session store) is swept.
    late = EventEnvelope(event_type="session.revoked", schema_version="1", aggregate_type="session",
                         aggregate_id=str(uuid.uuid4()), aggregate_version=1, environment="development",
                         actor_ref=f"member:{m}", correlation_id=str(uuid.uuid4()), privacy_class="restricted",
                         payload={"member_id": m, "reason": "sign_out"})
    db.run_in_transaction(lambda tx: write_events(tx, [late]))
    db.run_in_transaction(lambda tx: tx.insert(
        "IdempotencyRecords", ("principal_ref", "environment", "operation", "idempotency_key", "request_digest", "state",
                               "response_status", "response_body", "created_at", "expires_at"),
        [(f"member:{m}", "development", "late.op", "k-" + uuid.uuid4().hex, "0" * 64, "completed", 200,
          JsonObject({"member_id": m}), COMMIT_TIMESTAMP, now() + timedelta(days=30))]))
    assert leaked_tables(traces(db, m)) == {"OutboxEvents", "IdempotencyRecords"}
    assert sweep_erased_subjects(db, now()) == SweepResult(subjects=1, withdrawn=1, requests_deleted=1)
    assert leaked_tables(traces(db, m)) == set()

    # Seven days after delivery, delivered rows go; recent ones and live rows stay.
    delivered_friend = [e for e in friend_only if outbox(db)[e][1] == "delivered"]
    old, recent = delivered_friend[:2], set(outbox(db, "status = 'delivered'")) - set(delivered_friend[:2])
    erased_old = sorted(withdrawn)[:1]
    db.run_in_transaction(lambda tx: tx.execute_update(
        "UPDATE OutboxEvents SET next_attempt_at = TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 8 DAY), "
        "delivered_at = IF(status = 'delivered', TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 8 DAY), delivered_at) "
        "WHERE event_id IN UNNEST(@ids)", params={"ids": old + erased_old},
        param_types={"ids": param_types.Array(param_types.STRING)}))
    live = set(outbox(db, "status != 'delivered'")) - set(erased_old)
    assert old and recent
    assert purge_delivered(db, "development", now()) == len(old) + len(erased_old)
    remaining = set(outbox(db))
    assert not remaining & set(old + erased_old) and recent <= remaining and live <= remaining

    # A restore from the backup taken before deletion brings the rows back; re-applying the tombstones removes them.
    for name, (cols, data) in backup.items():
        replace_rows(db, name, cols, data)
    assert leaked_tables(traces(db, m)) == {"OutboxEvents", "IdempotencyRecords"}
    restored = svc.reapply_tombstones_after_restore("dev-backup-before-deletion", backup_at)
    assert restored["tombstones_applied"] == len(reg.categories()) and restored["rows_redeleted"] >= len(named)
    assert leaked_tables(traces(db, m)) == set()
    svc.assert_serving()


@requires_spanner
def test_without_the_platform_handler_the_trace_finds_the_leak(database):
    """Mutation check: the trace above is what catches the original Q9 leak."""
    store, provider = MemoryMediaStore(), SimulatedTryOnProvider()
    gone, *_ = seed(database, store, provider)
    reg = pd.PrivacyRegistry()
    register_consumer_domains(reg, database=database, media_store=store)
    svc = MyDataService(database, MemoryObjectStore(), reg, environment="development")
    receipt = svc.run_deletion(svc.request_deletion(gone.member_id, datetime.now(timezone.utc)))
    assert all(r["status"] == "deleted" for r in receipt["categories"].values())
    found = traces(database, gone.member_id)
    assert {"OutboxEvents", "IdempotencyRecords"} <= leaked_tables(found), found
    assert count(database, f"SELECT COUNT(*) FROM OutboxEvents WHERE {NAMES}", m=gone.member_id) >= 21
