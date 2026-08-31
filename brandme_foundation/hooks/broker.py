"""Event broker for the 30 lifecycle hooks.

The webhook receiver and other services publish events to topic names from
hooks/topics.yaml; subscribers register callbacks.

Two backends implement the same interface:

  * `InProcessBroker` — the default, in-process reference implementation.
    Producers and subscribers share one Python process.
  * `PubSubBroker` — the A5 go-live swap: live Cloud Pub/Sub, so events
    published in one process (e.g. the webhook receiver) reach subscribers
    in another (e.g. an agent worker). Selected only by explicit opt-in.

`make_broker()` picks between them. Every event carries `owner_id` so the
broker can refuse to dispatch events that lack it (`TenantRequiredOnEvent`);
subscribers receive the full HookEvent payload. See ADR 0017.
"""

from __future__ import annotations

import os
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast

from brandme_foundation.hooks import topic_names
from brandme_foundation.hooks.events import HookEvent

Subscriber = Callable[[HookEvent], None]


class TopicNotConfigured(RuntimeError):
    pass


class TenantRequiredOnEvent(RuntimeError):
    pass


class InProcessBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._known_topics: set[str] = set(topic_names())
        self._delivered: list[HookEvent] = []  # test introspection

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        if topic not in self._known_topics:
            raise TopicNotConfigured(
                f"topic {topic!r} not in hooks/topics.yaml")
        self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Subscriber) -> None:
        callbacks = self._subscribers.get(topic, [])
        if callback in callbacks:
            callbacks.remove(callback)

    def close(self) -> None:
        self._subscribers.clear()

    def publish(self, topic: str, owner_id: str,
                payload: dict[str, Any]) -> HookEvent:
        if topic not in self._known_topics:
            raise TopicNotConfigured(
                f"topic {topic!r} not in hooks/topics.yaml")
        if not owner_id:
            raise TenantRequiredOnEvent(
                f"event on {topic!r} missing owner_id")
        event = HookEvent(
            event_id=str(uuid.uuid4()),
            topic=topic,
            owner_id=owner_id,
            payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
        self._delivered.append(event)
        for cb in self._subscribers.get(topic, []):
            cb(event)
        return event

    @property
    def delivered(self) -> list[HookEvent]:
        return list(self._delivered)

    def subscriber_count(self, topic: str) -> int:
        """Live callbacks registered on `topic` in this process — real
        introspection for the ops surface (no invented telemetry)."""
        return len(self._subscribers.get(topic, []))


class PubSubBroker:
    """Live Cloud Pub/Sub broker — the A5 go-live swap for InProcessBroker.

    Same interface as InProcessBroker (`subscribe`/`publish`, matching
    signatures). google-cloud-pubsub is lazy-imported in ``__init__`` (mirrors
    ``LiteLLMClient``) so the package stays optional in dev; constructing this
    without the package installed or without ``PUBSUB_PROJECT`` raises
    immediately. Misconfiguration is loud — this broker never silently degrades
    to in-process, because that would drop events crossing process boundaries.

    Topic mapping: the logical topic names in hooks/topics.yaml map 1:1 to
    Pub/Sub topics under ``PUBSUB_PROJECT``, optionally namespaced by
    ``PUBSUB_TOPIC_PREFIX``. e.g. ``on_listing_published`` ->
    ``projects/<project>/topics/<prefix>on_listing_published``. Each subscriber
    binds a subscription named ``<prefix><topic>-sub``.

    Topics-must-exist: the 30 topics (and their subscriptions) are provisioned
    by infra per runbook A5. This broker asserts the *logical* name is known
    (``TopicNotConfigured``) and, by default, lets a missing GCP topic surface
    as a loud ``google.api_core`` NotFound rather than creating it silently.
    Set ``PUBSUB_AUTOCREATE=1`` to have the broker create-if-missing at
    publish/subscribe time (intended for non-prod bring-up only).
    """

    def __init__(self, project: str | None = None,
                 topic_prefix: str | None = None) -> None:
        project = project or os.getenv("PUBSUB_PROJECT")
        if not project:
            raise RuntimeError(
                "PubSubBroker requires PUBSUB_PROJECT (env or constructor arg)")
        try:
            cloud = cast(Any, __import__("google.cloud", fromlist=["pubsub_v1"]))
            pubsub_v1 = cloud.pubsub_v1
        except ImportError as e:
            raise RuntimeError(
                "google-cloud-pubsub not installed. "
                "`pip install google-cloud-pubsub` or use InProcessBroker"
            ) from e
        self._pubsub = pubsub_v1
        self._project = project
        self._prefix = (topic_prefix if topic_prefix is not None
                        else os.getenv("PUBSUB_TOPIC_PREFIX", ""))
        self._autocreate = os.getenv("PUBSUB_AUTOCREATE") == "1"
        self._known_topics: set[str] = set(topic_names())
        self._publisher = pubsub_v1.PublisherClient()
        self._subscriber = pubsub_v1.SubscriberClient()
        # Streaming-pull futures are kept alive for the process lifetime.
        self._futures: list[Any] = []
        self._subscriptions: dict[tuple[str, Subscriber], Any] = {}

    # -- topic/subscription path helpers ---------------------------------

    def _topic_id(self, topic: str) -> str:
        return f"{self._prefix}{topic}"

    def _topic_path(self, topic: str) -> str:
        return cast(str, self._publisher.topic_path(self._project, self._topic_id(topic)))

    def _subscription_path(self, topic: str) -> str:
        return cast(
            str,
            self._subscriber.subscription_path(
                self._project, f"{self._topic_id(topic)}-sub"
            ),
        )

    def _ensure_topic(self, topic_path: str) -> None:
        from google.api_core.exceptions import (
            AlreadyExists,
        )
        try:
            self._publisher.create_topic(request={"name": topic_path})
        except AlreadyExists:
            pass

    def _ensure_subscription(self, sub_path: str, topic_path: str) -> None:
        from google.api_core.exceptions import (
            AlreadyExists,
        )
        try:
            self._subscriber.create_subscription(
                request={"name": sub_path, "topic": topic_path})
        except AlreadyExists:
            pass

    # -- interface (matches InProcessBroker) -----------------------------

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        if topic not in self._known_topics:
            raise TopicNotConfigured(
                f"topic {topic!r} not in hooks/topics.yaml")
        topic_path = self._topic_path(topic)
        sub_path = self._subscription_path(topic)
        if self._autocreate:
            self._ensure_topic(topic_path)
            self._ensure_subscription(sub_path, topic_path)

        def _dispatch(message: Any) -> None:
            try:
                event = HookEvent.model_validate_json(message.data)
                # The tenant envelope is non-negotiable even on the inbound path:
                # an event that reached us without owner_id is malformed.
                if not event.owner_id:
                    raise TenantRequiredOnEvent(
                        f"event on {topic!r} missing owner_id"
                    )
                callback(event)
            except Exception:
                message.nack()
                raise
            message.ack()

        future = self._subscriber.subscribe(sub_path, callback=_dispatch)
        self._futures.append(future)
        self._subscriptions[(topic, callback)] = future

    def unsubscribe(self, topic: str, callback: Subscriber) -> None:
        future = self._subscriptions.pop((topic, callback), None)
        if future is not None:
            future.cancel()
            if future in self._futures:
                self._futures.remove(future)

    def close(self) -> None:
        for future in list(self._futures):
            future.cancel()
        self._futures.clear()
        self._subscriptions.clear()
        self._publisher.stop()
        self._subscriber.close()

    def publish(self, topic: str, owner_id: str,
                payload: dict[str, Any]) -> HookEvent:
        if topic not in self._known_topics:
            raise TopicNotConfigured(
                f"topic {topic!r} not in hooks/topics.yaml")
        if not owner_id:
            raise TenantRequiredOnEvent(
                f"event on {topic!r} missing owner_id")
        event = HookEvent(
            event_id=str(uuid.uuid4()),
            topic=topic,
            owner_id=owner_id,
            payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
        topic_path = self._topic_path(topic)
        if self._autocreate:
            self._ensure_topic(topic_path)
        data = event.model_dump_json().encode("utf-8")
        # owner_id rides in message attributes so subscribers — and Pub/Sub
        # subscription filters — can key on the tenant without deserializing.
        future = self._publisher.publish(
            topic_path,
            data,
            owner_id=owner_id,
            topic=topic,
            event_id=event.event_id,
        )
        # Block until the publish is acked so a broker/topic failure is loud
        # at the call site rather than swallowed by a background thread.
        future.result()
        return event


# Either backend satisfies the broker interface; call sites accept both.
Broker = InProcessBroker | PubSubBroker


def make_broker() -> Broker:
    """Select the event broker backend — loud on misconfiguration.

    ``BROKER_BACKEND=pubsub`` (plus ``PUBSUB_PROJECT``) selects the live
    Cloud Pub/Sub broker. If that is set but ``PUBSUB_PROJECT`` is missing,
    google-cloud-pubsub can't import, or the client can't be constructed, this
    RAISES — it never silently returns an InProcessBroker. A silent fallback
    in production would mean events published in one process never reach
    subscribers in another: silent event loss (the same silent-fallback class
    the A1 litellm and psycopg2 fixes closed).

    Unset (or ``inprocess``) → the default ``InProcessBroker``, unchanged. Any
    other value is a misconfiguration and raises rather than guessing.
    """
    backend = os.getenv("BROKER_BACKEND", "").strip().lower()
    if backend == "pubsub":
        if not os.getenv("PUBSUB_PROJECT"):
            raise RuntimeError(
                "BROKER_BACKEND=pubsub requires PUBSUB_PROJECT to be set")
        return PubSubBroker()
    if backend in ("", "inprocess", "in_process"):
        return InProcessBroker()
    raise RuntimeError(
        f"unknown BROKER_BACKEND {backend!r}; expected 'pubsub' or 'inprocess'")
