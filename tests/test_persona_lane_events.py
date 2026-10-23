"""Lane event ingress and outbox delivery.

Part 1 (runs wherever Spanner is up): the ingress refuses every malformed,
foreign-environment, wrong-privacy-class or off-contract message, using real
lane events read back from the outbox.

Part 2 (needs the foundation outbox worker from PR #47 and a real Pub/Sub
emulator via PUBSUB_EMULATOR_BIN): lane events published by the lane worker
reach the lane subscriber and are applied exactly once; an order observation
reaches the wardrobe; foreign-environment messages are never acknowledged.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.ingress import IngressRejected, LaneSubscriber, PubSubPull, check, decode, run_once
from brandme_core.domains.persona.kernel import FixedClock, member_principal
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.events import EventEnvelope
from test_persona_harness import INSTANCE, MEMBER_SCOPES, PROJECT, count, insert_member, new_migrated_database, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def key():
    return "k-" + uuid.uuid4().hex


def outbox_events(db, aggregate_or_member, *types):
    with db.snapshot() as s:
        rows = s.execute_sql(
            "SELECT event_id, event_type, schema_version, aggregate_type, aggregate_id, aggregate_version, environment, actor_ref, "
            "correlation_id, causation_id, privacy_class, payload, occurred_at FROM OutboxEvents "
            "WHERE event_type IN UNNEST(@t) AND (aggregate_id=@m OR JSON_VALUE(payload, '$.member_id')=@m) ORDER BY occurred_at",
            params={"t": list(types), "m": aggregate_or_member},
            param_types={"t": param_types.Array(param_types.STRING), "m": param_types.STRING})
        cols = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version", "environment", "actor_ref",
                "correlation_id", "causation_id", "privacy_class", "payload", "occurred_at")
        return [EventEnvelope.from_row(dict(zip(cols, r))) for r in rows]


def wire(event, **body_changes):
    body = {**event.to_wire(), **body_changes}
    attrs = {k: body[k] for k in ("event_id", "event_type", "schema_version", "environment", "privacy_class")}
    return json.dumps(body).encode(), attrs


def order_event(member_id, *, delivered=1, version=1, environment="development", order_id=None):
    order_id = order_id or str(uuid.uuid4())
    return EventEnvelope(
        event_type="commerce.order.observed", schema_version="1", aggregate_type="Order", aggregate_id=order_id, aggregate_version=version,
        environment=environment, actor_ref="service:commerce-observer", correlation_id=str(uuid.uuid4()), privacy_class="member_private",
        payload={"order_id": order_id, "operation_id": str(uuid.uuid4()), "member_id": member_id, "provider_id": "retailer-dev",
                 "order_status": "accepted", "payment_status": "captured", "fulfillment_status": "fulfilled", "wardrobe_effect": "arrived",
                 "lines": [{"variant_id": None, "source_variant_ref": "sku-dev-1", "ordered": 1, "shipped": 1, "delivered": delivered,
                            "returned": 0, "exchanged_from_ref": None}],
                 "acquisition_evidence": ["order:dev"]})


# ------------------------------------------------------------------ part 1


@pytest.fixture
def item_event(spanner_db):  # noqa: F811 (harness fixture)
    me = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    WardrobeService(spanner_db).create_items(me, {"source": "manual", "title": "Tee", "category": "top"}, key())
    (event,) = outbox_events(spanner_db, me.member_id, "wardrobe.item.created")
    return event


def rejected(data, attrs, environment="development"):
    with pytest.raises(IngressRejected) as e:
        check(decode(data, attrs), environment=environment)
    return e.value.code


def test_published_lane_event_round_trips(item_event):
    data, attrs = wire(item_event)
    got = decode(data, attrs)
    check(got, environment="development")
    assert got.to_wire() == item_event.to_wire()


def test_ingress_rejections(item_event):
    data, attrs = wire(item_event)
    assert rejected(b"{not json", attrs) == "message_not_json"
    assert rejected(b" " * (256 * 1024 + 1), attrs) == "message_too_large"
    assert rejected(*wire(item_event, extra="x")) == "envelope_shape"
    assert rejected(data, {**attrs, "event_type": "wardrobe.item.updated"}) == "attributes_mismatch"
    assert rejected(data, {k: v for k, v in attrs.items() if k != "privacy_class"}) == "attributes_mismatch"
    non_canonical = item_event.to_wire()["occurred_at"].replace("Z", "+00:00")
    assert rejected(*wire(item_event, occurred_at=non_canonical)) == "envelope_shape"
    assert rejected(data, attrs, environment="sandbox") == "environment_mismatch"
    assert rejected(*wire(item_event, privacy_class="public")) == "privacy_class_mismatch"
    assert rejected(*wire(item_event, payload={**item_event.payload, "email": "a@b.c"})) == "contract_invalid"
    assert rejected(*wire(item_event, event_type="wardrobe.item.unknown")) == "unsupported_contract"


def test_order_observation_checked_against_consumer_copy():
    ev = order_event(str(uuid.uuid4()))
    check(decode(*wire(ev)), environment="development")
    drifted = order_event(ev.payload["member_id"])
    drifted.payload["gift_message"] = "hi"
    assert rejected(*wire(drifted)) == "contract_invalid"


def test_subscriber_ignores_other_domains_and_never_acks_rejections(spanner_db, item_event):  # noqa: F811
    sub = LaneSubscriber(spanner_db, environment="development")
    assert sub.handle_message(b"{}", {"event_type": "member.created"}).ack is True
    data, attrs = wire(item_event, environment="sandbox")
    out = sub.handle_message(data, attrs)
    assert (out.ack, out.code) == (False, "environment_mismatch")
    first = sub.handle_message(*wire(item_event))
    assert first.ack and first.code == "processed"
    again = sub.handle_message(*wire(item_event))
    assert again.ack and again.code == "duplicate_delivery"


# ------------------------------------------------------------------ part 2

HAS_WORKER = importlib.util.find_spec("brandme_core.events.worker") is not None
pubsub_flow = pytest.mark.skipif(not HAS_WORKER or not os.environ.get("PUBSUB_EMULATOR_BIN"),
                                 reason="foundation outbox worker (PR #47) or PUBSUB_EMULATOR_BIN missing; Pub/Sub flow NOT RUN")


@pytest.fixture(scope="module")
def pubsub(tmp_path_factory):
    if not HAS_WORKER or not os.environ.get("PUBSUB_EMULATOR_BIN"):
        pytest.skip("Pub/Sub flow NOT RUN")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = (tmp_path_factory.mktemp("pubsub") / "server.log").open("w")
    server = subprocess.Popen([str(Path(os.environ["PUBSUB_EMULATOR_BIN"]).resolve()), "--host=127.0.0.1", f"--port={port}"],
                              stdout=log, stderr=log)
    try:
        for _ in range(300):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=.1).close()
                break
            except OSError:
                time.sleep(.05)
        else:
            pytest.fail("Pub/Sub emulator did not start")
        yield f"127.0.0.1:{port}"
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()


@pytest.fixture(scope="module")
def flow_db():
    database = new_migrated_database()  # the worker scans the whole outbox
    yield database
    try:
        database.drop()
    except Exception:
        pass


def provision(host):
    import requests

    suffix = uuid.uuid4().hex[:6]
    topics = {c: f"projects/{PROJECT}/topics/brandme-development-{c.replace('_', '-')}-{suffix}" for c in ("public", "member_private", "restricted")}
    for t in topics.values():
        assert requests.put(f"http://{host}/v1/{t}", json={"messageRetentionDuration": "86400s"}, timeout=5).status_code == 200
    sub = f"projects/{PROJECT}/subscriptions/brandme-development-consumer-lane-{suffix}"
    assert requests.put(f"http://{host}/v1/{sub}", json={"topic": topics["member_private"], "ackDeadlineSeconds": 10}, timeout=5).status_code == 200
    return topics, sub


def publish_raw(host, topic, event):
    import requests

    data, attrs = wire(event)
    r = requests.post(f"http://{host}/v1/{topic}:publish", json={"messages": [{"data": base64.b64encode(data).decode(), "attributes": attrs}]},
                      timeout=5)
    assert r.status_code == 200


def process_env(db, host, topics, sub):
    return {**os.environ, "BRANDME_MODE": "development", "ENVIRONMENT": "development", "SPANNER_PROJECT_ID": PROJECT,
            "SPANNER_INSTANCE_ID": INSTANCE, "SPANNER_DATABASE_ID": db.database_id, "PUBSUB_EMULATOR_HOST": host,
            "LANE_PUBSUB_SUBSCRIPTION": sub, **{"OUTBOX_PUBSUB_TOPIC_" + c.upper(): t for c, t in topics.items()}}


def run_module(module, env, *args):
    return subprocess.run([sys.executable, "-m", module, *args], env=env, capture_output=True, text=True, timeout=120,
                          cwd=Path(__file__).resolve().parents[1])


def status_of(db, event_types):
    with db.snapshot() as s:
        return sorted({r[0] for r in s.execute_sql("SELECT status FROM OutboxEvents WHERE event_type IN UNNEST(@t)",
                                                     params={"t": list(event_types)}, param_types={"t": param_types.Array(param_types.STRING)})})


def drain(transport, subscriber, rounds=40):
    total = {}
    idle = 0
    while idle < 3 and rounds:
        rounds -= 1
        counts = run_once(transport, subscriber)
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
        idle = idle + 1 if not counts else 0
        time.sleep(.1)
    return total


def ledger(db, member_id):
    with db.snapshot() as s:
        return sorted((r[0], r[1]) for r in s.execute_sql("SELECT rule_id, points FROM RewardEntries WHERE member_id=@m AND state='posted'",
                                                          params={"m": member_id}, param_types={"m": param_types.STRING}))


@pubsub_flow
def test_lane_events_flow_through_pubsub_exactly_once(flow_db, pubsub):
    from brandme_core.events.pubsub import PubSubPublisher

    db = flow_db
    topics, sub = provision(pubsub)
    env = process_env(db, pubsub, topics, sub)
    me = member_principal(insert_member(db), MEMBER_SCOPES)
    PersonaService(db, clock=FixedClock(NOW)).patch(me, '"0"', {"changes": [{"axis": "expression", "value": 70, "locked": False}],
                                                               "client_revision": "r1"})
    item = WardrobeService(db).create_items(me, {"source": "manual", "title": "Tee", "category": "top"}, key())["items"][0]["id"]
    OutfitService(db).create_outfit(me, {"title": "Monday", "item_refs": [item]}, key())
    lane_types = ("persona.updated", "wardrobe.item.created", "outfit.version.created")

    # The foundation worker alone leaves lane contracts pending: they are not in its catalog.
    foundation = run_module("brandme_core.events.worker", env, "--once")
    assert foundation.returncode == 0, foundation.stdout + foundation.stderr
    assert status_of(db, lane_types) == ["pending"]
    # The lane worker loads the lane catalog and publishes them.
    for _ in range(5):
        lane = run_module("brandme_core.domains.persona.outbox_worker", env, "--once")
        assert lane.returncode == 0, lane.stdout + lane.stderr
        if status_of(db, lane_types) == ["delivered"]:
            break
    assert status_of(db, lane_types) == ["delivered"]
    ready = json.loads(lane.stdout.splitlines()[0])
    assert ready["status"] == "ready" and ready["event_contracts"] > json.loads(foundation.stdout.splitlines()[0])["event_contracts"]
    assert me.member_id not in lane.stdout + lane.stderr

    transport = PubSubPull(sub, "development", emulator_host=pubsub)
    subscriber = LaneSubscriber(db, environment="development")
    try:
        counts = drain(transport, subscriber)
        assert counts.get("processed", 0) >= 3 and not {k for k in counts if k not in ("processed", "not_subscribed")}, counts
        assert ledger(db, me.member_id) == [("first_owned_item", 25), ("meaningful_style_setup", 100)]

        # A republished event (lost broker ack) gets a new message id and changes nothing.
        (item_ev,) = outbox_events(db, me.member_id, "wardrobe.item.created")
        publisher = PubSubPublisher(topics, "development", emulator_host=pubsub)
        try:
            publisher(item_ev)
        finally:
            publisher.close()
        assert drain(transport, subscriber).get("duplicate_delivery") == 1
        assert ledger(db, me.member_id) == [("first_owned_item", 25), ("meaningful_style_setup", 100)]

        # A foreign-environment message is never acknowledged and never applied.
        foreign = order_event(me.member_id, environment="sandbox")
        publish_raw(pubsub, topics["member_private"], foreign)
        assert drain(transport, subscriber, rounds=5).get("environment_mismatch", 0) >= 1
        assert count(db, "SELECT COUNT(*) FROM WardrobeOrderLinks WHERE member_id=@m", m=me.member_id) == 0
    finally:
        transport.close()


@pubsub_flow
def test_order_observation_reaches_wardrobe_through_the_subscriber_process(flow_db, pubsub):
    db = flow_db
    topics, sub = provision(pubsub)
    env = process_env(db, pubsub, topics, sub)
    me = member_principal(insert_member(db), MEMBER_SCOPES)
    before = count(db, "SELECT COUNT(*) FROM WardrobeItems WHERE member_id=@m", m=me.member_id)
    order = order_event(me.member_id)
    publish_raw(pubsub, topics["member_private"], order)
    publish_raw(pubsub, topics["member_private"], order)  # duplicate delivery
    applied = {}
    for _ in range(10):
        run = run_module("brandme_core.domains.persona.ingress", env, "--once")
        assert run.returncode == 0, run.stdout + run.stderr
        for line in run.stdout.splitlines()[1:]:
            for k, v in json.loads(line).items():
                if k != "status":
                    applied[k] = applied.get(k, 0) + v
        if applied.get("applied", 0) + applied.get("duplicate_delivery", 0) >= 2:
            break
    assert applied == {"applied": 1, "duplicate_delivery": 1}, applied
    assert count(db, "SELECT COUNT(*) FROM WardrobeItems WHERE member_id=@m", m=me.member_id) == before + 1
    assert me.member_id not in run.stdout + run.stderr
