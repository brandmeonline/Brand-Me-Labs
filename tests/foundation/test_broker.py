"""Broker backend selection + the live Pub/Sub seam (go-live A5).

The live broker cannot be exercised against real Cloud Pub/Sub here (no GCP
project/credentials), so every Pub/Sub test mocks the google-cloud-pubsub
client and asserts at the seam: the factory picks the right backend loudly,
the interface matches InProcessBroker, the tenant envelope is preserved, and
the streaming-pull dispatch decodes back into a HookEvent. See ADR 0017.
"""

from __future__ import annotations

import builtins
import inspect
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from brandme_foundation.hooks.broker import (
    InProcessBroker,
    PubSubBroker,
    TenantRequiredOnEvent,
    make_broker,
)
from brandme_foundation.hooks.events import HookEvent


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _mock_pubsub_clients(monkeypatch):
    """Patch PublisherClient/SubscriberClient so PubSubBroker constructs and
    operates with zero network access. Returns the (publisher, subscriber)
    mocks so tests can assert on calls."""
    pubsub_v1 = pytest.importorskip("google.cloud.pubsub_v1")

    publisher = mock.Mock(name="PublisherClient")
    publisher.topic_path.side_effect = (
        lambda proj, tid: f"projects/{proj}/topics/{tid}")
    published_future = mock.Mock(name="publish_future")
    published_future.result.return_value = "message-id-1"
    publisher.publish.return_value = published_future

    subscriber = mock.Mock(name="SubscriberClient")
    subscriber.subscription_path.side_effect = (
        lambda proj, sid: f"projects/{proj}/subscriptions/{sid}")

    monkeypatch.setattr(pubsub_v1, "PublisherClient", lambda *a, **k: publisher)
    monkeypatch.setattr(pubsub_v1, "SubscriberClient", lambda *a, **k: subscriber)
    return publisher, subscriber


def _make_pubsub_broker(monkeypatch):
    publisher, subscriber = _mock_pubsub_clients(monkeypatch)
    monkeypatch.setenv("PUBSUB_PROJECT", "test-project")
    monkeypatch.delenv("PUBSUB_TOPIC_PREFIX", raising=False)
    monkeypatch.delenv("PUBSUB_AUTOCREATE", raising=False)
    return PubSubBroker(), publisher, subscriber


def _event(owner_id: str = "r1", topic: str = "on_ownership_transferred") -> HookEvent:
    return HookEvent(
        event_id="e1",
        topic=topic,
        owner_id=owner_id,
        payload={"k": "v"},
        occurred_at=datetime.now(timezone.utc),
    )


# ----------------------------------------------------------------------
# Factory selection — loud on misconfiguration
# ----------------------------------------------------------------------


def test_factory_default_is_inprocess(monkeypatch) -> None:
    monkeypatch.delenv("BROKER_BACKEND", raising=False)
    assert isinstance(make_broker(), InProcessBroker)


def test_factory_explicit_inprocess(monkeypatch) -> None:
    monkeypatch.setenv("BROKER_BACKEND", "inprocess")
    assert isinstance(make_broker(), InProcessBroker)


def test_factory_selects_pubsub_when_configured(monkeypatch) -> None:
    """BROKER_BACKEND=pubsub + package importable + PUBSUB_PROJECT -> the live
    broker. Clients are mocked so no real Pub/Sub connection is made."""
    _mock_pubsub_clients(monkeypatch)
    monkeypatch.setenv("BROKER_BACKEND", "pubsub")
    monkeypatch.setenv("PUBSUB_PROJECT", "test-project")
    assert isinstance(make_broker(), PubSubBroker)


def test_factory_pubsub_requires_project(monkeypatch) -> None:
    monkeypatch.setenv("BROKER_BACKEND", "pubsub")
    monkeypatch.delenv("PUBSUB_PROJECT", raising=False)
    with pytest.raises(RuntimeError, match="PUBSUB_PROJECT"):
        make_broker()


def test_factory_pubsub_raises_when_package_absent(monkeypatch) -> None:
    """Set-but-absent must RAISE, never silently return InProcessBroker — a
    silent fallback in production is silent cross-process event loss."""
    monkeypatch.setenv("BROKER_BACKEND", "pubsub")
    monkeypatch.setenv("PUBSUB_PROJECT", "test-project")

    real_import = builtins.__import__

    def _no_pubsub(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "google.cloud" and "pubsub_v1" in (fromlist or ()):
            raise ImportError("simulated: google-cloud-pubsub not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _no_pubsub)
    with pytest.raises(RuntimeError, match="google-cloud-pubsub not installed"):
        make_broker()


def test_factory_unknown_backend_raises(monkeypatch) -> None:
    monkeypatch.setenv("BROKER_BACKEND", "kafka")
    with pytest.raises(RuntimeError, match="unknown BROKER_BACKEND"):
        make_broker()


# ----------------------------------------------------------------------
# Dependency-declaration guard (Vercel installs ONLY from requirements.txt)
# ----------------------------------------------------------------------


def test_pubsub_dep_declared_in_requirements() -> None:
    """Silent-fallback guard, carried over from Lux: the live broker imports
    google.cloud.pubsub. If the dep is not pinned where the runtime installs
    from, `make_broker()` degrades to in-process and every cross-process event
    vanishes without an error. Pin it so that trap can't reappear."""
    reqs = (
        Path(__file__).resolve().parents[2] / "brandme_foundation" / "requirements.txt"
    ).read_text().lower()
    assert "google-cloud-pubsub" in reqs, (
        "google-cloud-pubsub missing from brandme_foundation/requirements.txt")


# ----------------------------------------------------------------------
# Interface conformance — PubSubBroker is a drop-in for InProcessBroker
# ----------------------------------------------------------------------


@pytest.mark.parametrize("method", ["subscribe", "publish"])
def test_pubsub_matches_inprocess_signature(method) -> None:
    assert hasattr(PubSubBroker, method)
    sig_pubsub = inspect.signature(getattr(PubSubBroker, method))
    sig_inproc = inspect.signature(getattr(InProcessBroker, method))
    assert list(sig_pubsub.parameters) == list(sig_inproc.parameters)


# ----------------------------------------------------------------------
# Tenant envelope + publish seam
# ----------------------------------------------------------------------


def test_pubsub_publish_requires_owner_id(monkeypatch) -> None:
    broker, _publisher, _subscriber = _make_pubsub_broker(monkeypatch)
    with pytest.raises(TenantRequiredOnEvent):
        broker.publish(topic="on_ownership_transferred", owner_id="", payload={})


def test_pubsub_publish_puts_tenant_in_attributes(monkeypatch) -> None:
    """owner_id must ride in Pub/Sub message attributes (the tenant envelope
    is non-negotiable), the event body serializes as JSON, and publish blocks
    on the ack so a broker/topic failure is loud."""
    broker, publisher, _subscriber = _make_pubsub_broker(monkeypatch)
    event = broker.publish(
        topic="on_ownership_transferred", owner_id="r-42", payload={"x": 1})

    assert isinstance(event, HookEvent)
    assert event.owner_id == "r-42"

    args, kwargs = publisher.publish.call_args
    # topic path resolved under the project
    assert args[0] == "projects/test-project/topics/on_ownership_transferred"
    # tenant + routing metadata travel as attributes
    assert kwargs["owner_id"] == "r-42"
    assert kwargs["topic"] == "on_ownership_transferred"
    assert kwargs["event_id"] == event.event_id
    # payload body is the JSON-serialized HookEvent
    assert b"r-42" in args[1]
    # publish blocked on the ack
    publisher.publish.return_value.result.assert_called_once()


def test_pubsub_publish_rejects_unknown_topic(monkeypatch) -> None:
    from brandme_foundation.hooks.broker import TopicNotConfigured

    broker, _publisher, _subscriber = _make_pubsub_broker(monkeypatch)
    with pytest.raises(TopicNotConfigured):
        broker.publish(topic="on_not_a_real_topic", owner_id="r1", payload={})


def test_pubsub_topic_prefix_is_applied(monkeypatch) -> None:
    _mock_pubsub_clients(monkeypatch)
    monkeypatch.setenv("PUBSUB_PROJECT", "test-project")
    monkeypatch.setenv("PUBSUB_TOPIC_PREFIX", "prod-")
    broker = PubSubBroker()
    broker.publish(topic="on_ownership_transferred", owner_id="r1", payload={})
    args, _kwargs = broker._publisher.publish.call_args
    assert args[0] == "projects/test-project/topics/prod-on_ownership_transferred"


# ----------------------------------------------------------------------
# Streaming-pull subscribe dispatch
# ----------------------------------------------------------------------


def test_pubsub_subscribe_dispatches_decoded_event(monkeypatch) -> None:
    broker, _publisher, subscriber = _make_pubsub_broker(monkeypatch)
    received: list[HookEvent] = []
    broker.subscribe("on_ownership_transferred", received.append)

    # a streaming-pull subscriber was registered with an internal dispatcher
    assert subscriber.subscribe.call_count == 1
    sub_args, sub_kwargs = subscriber.subscribe.call_args
    assert sub_args[0] == "projects/test-project/subscriptions/on_ownership_transferred-sub"
    dispatch = sub_kwargs["callback"]

    ev = _event(owner_id="r-7")
    message = mock.Mock()
    message.data = ev.model_dump_json().encode("utf-8")
    dispatch(message)

    assert len(received) == 1
    assert received[0].owner_id == "r-7"
    message.ack.assert_called_once()
    message.nack.assert_not_called()


def test_pubsub_subscribe_refuses_untenanted_message(monkeypatch) -> None:
    """The tenant envelope is enforced inbound too: a message that arrives
    without owner_id is nacked and raises rather than reaching the callback."""
    broker, _publisher, subscriber = _make_pubsub_broker(monkeypatch)
    broker.subscribe("on_ownership_transferred", lambda e: None)
    dispatch = subscriber.subscribe.call_args.kwargs["callback"]

    ev = _event(owner_id="")  # empty tenant is malformed
    message = mock.Mock()
    message.data = ev.model_dump_json().encode("utf-8")
    with pytest.raises(TenantRequiredOnEvent):
        dispatch(message)
    message.nack.assert_called_once()
    message.ack.assert_not_called()


def test_pubsub_subscribe_nacks_consumer_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker, _publisher, subscriber = _make_pubsub_broker(  # type: ignore[no-untyped-call]
        monkeypatch
    )

    def fail(_event: HookEvent) -> None:
        raise RuntimeError("consumer failed")

    broker.subscribe("on_ownership_transferred", fail)
    dispatch = subscriber.subscribe.call_args.kwargs["callback"]
    message = mock.Mock()
    message.data = _event(owner_id="r-7").model_dump_json().encode("utf-8")
    with pytest.raises(RuntimeError, match="consumer failed"):
        dispatch(message)
    message.nack.assert_called_once()
    message.ack.assert_not_called()


def test_pubsub_subscribe_rejects_unknown_topic(monkeypatch) -> None:
    from brandme_foundation.hooks.broker import TopicNotConfigured

    broker, _publisher, _subscriber = _make_pubsub_broker(monkeypatch)
    with pytest.raises(TopicNotConfigured):
        broker.subscribe("on_not_a_real_topic", lambda e: None)


# ----------------------------------------------------------------------
# Call-site wiring — the three factories route through make_broker()
# ----------------------------------------------------------------------


# NOTE: Lux's `test_call_sites_default_to_inprocess` is omitted — it constructs
# Lux's gateway and webhook-receiver apps. Reinstate it against Brand.Me's own
# services once they adopt make_broker() (docs/audit/LUX_LIFT_AND_SHIFT.md, Wave 2).
