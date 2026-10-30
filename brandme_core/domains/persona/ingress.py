"""
Pub/Sub ingress for this lane's event consumers (dev form).

The foundation outbox worker publishes ``EventEnvelope.to_wire()`` JSON with
attributes ``event_id``, ``event_type``, ``schema_version``, ``environment`` and
``privacy_class``. Delivery is at least once and says nothing about consumer
effects, so for every message this module:

1. decodes the closed envelope and requires the attributes to match the body;
2. accepts only the configured environment and the privacy class registered
   for the contract, and validates the payload against that contract;
3. hands the envelope to the lane consumer, which applies its effect with
   ``first_delivery`` in the same transaction, rechecks privacy freezes there
   and ignores stale aggregate versions;
4. acknowledges only after that commit.

A rejected message is never acknowledged, so the subscription's dead-letter
policy keeps it for investigation. Logs carry fixed codes, never payloads,
member ids or event ids.

``commerce.order.observed`` is emitted by the commerce lane but is not in a
registered catalog yet. Until it is, it is validated against
``CONSUMER_COPIES``: a closed copy of its payload as emitted on ``main`` at
5174ec2. Drift fails closed (dead letter), never applied silently. The
registered contract wins once it exists.

Run: ``python -m brandme_core.domains.persona.ingress [--once]`` with
``BRANDME_MODE``/``ENVIRONMENT`` equal, ``SPANNER_PROJECT_ID``,
``SPANNER_INSTANCE_ID``, ``SPANNER_DATABASE_ID``, ``LANE_PUBSUB_SUBSCRIPTION``
(``projects/P/subscriptions/brandme-ENV-...`` on the member_private topic) and,
in demo/development only, both emulator hosts.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import os
import re
import signal
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from brandme_core.events import EventEnvelope, EventRegistry, EventValidationError, registry

MAX_EVENT_BYTES = 256 * 1024
MAX_PULL_BYTES = 4 * 1024 * 1024
WIRE_KEYS = frozenset({"event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version", "occurred_at",
                       "environment", "actor_ref", "correlation_id", "causation_id", "privacy_class", "payload"})
ATTRIBUTE_KEYS = ("event_id", "event_type", "schema_version", "environment", "privacy_class")
SUBSCRIPTION = re.compile(r"projects/[a-z][a-z0-9-]{4,61}[a-z0-9]/subscriptions/[A-Za-z][A-Za-z0-9._~-]{2,254}\Z")

_STR = {"type": "string", "minLength": 1, "maxLength": 256}
_QTY = {"type": "integer", "minimum": 0, "maximum": 1000}
ORDER_OBSERVED_V1 = {
    "type": "object",
    "additionalProperties": False,
    "required": ["order_id", "operation_id", "member_id", "provider_id", "order_status", "payment_status", "fulfillment_status",
                 "wardrobe_effect", "lines", "acquisition_evidence"],
    "properties": {
        "order_id": _STR, "operation_id": _STR, "member_id": {"type": "string", "format": "uuid"}, "provider_id": _STR,
        "order_status": _STR, "payment_status": _STR, "fulfillment_status": _STR, "wardrobe_effect": _STR,
        "lines": {"type": "array", "maxItems": 100, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["variant_id", "source_variant_ref", "ordered", "shipped", "delivered", "returned", "exchanged_from_ref"],
            "properties": {"variant_id": {"type": ["string", "null"], "maxLength": 256}, "source_variant_ref": _STR, "ordered": _QTY,
                           "shipped": _QTY, "delivered": _QTY, "returned": _QTY,
                           "exchanged_from_ref": {"type": ["string", "null"], "maxLength": 256}}}},
        "acquisition_evidence": {"type": "array", "maxItems": 50, "items": _STR},
    },
}
CONSUMER_COPIES = EventRegistry()
CONSUMER_COPIES.register("commerce.order.observed", "1", ORDER_OBSERVED_V1, "member_private")


class IngressRejected(Exception):
    """A message that must not be applied. ``code`` is safe to log."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def decode(data: bytes, attributes: Mapping[str, str]) -> EventEnvelope:
    """Wire JSON + attributes → envelope. Structural checks only; see ``check``."""
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_EVENT_BYTES:
        raise IngressRejected("message_too_large")
    try:
        wire = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise IngressRejected("message_not_json") from None
    if not isinstance(wire, dict) or set(wire) != WIRE_KEYS or not isinstance(wire["payload"], dict):
        raise IngressRejected("envelope_shape")
    if any(attributes.get(k) != wire.get(k) for k in ATTRIBUTE_KEYS):
        raise IngressRejected("attributes_mismatch")
    version, occurred = wire["aggregate_version"], wire["occurred_at"]
    if not isinstance(version, str) or not version.isdigit() or not isinstance(occurred, str):
        raise IngressRejected("envelope_shape")
    try:
        occurred_at = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
    except ValueError:
        raise IngressRejected("envelope_shape") from None
    if occurred_at.tzinfo is None:
        raise IngressRejected("envelope_shape")
    event = EventEnvelope(
        event_id=wire["event_id"], event_type=wire["event_type"], schema_version=wire["schema_version"],
        aggregate_type=wire["aggregate_type"], aggregate_id=wire["aggregate_id"], aggregate_version=int(version),
        environment=wire["environment"], actor_ref=wire["actor_ref"], correlation_id=wire["correlation_id"],
        causation_id=wire["causation_id"], privacy_class=wire["privacy_class"], payload=wire["payload"], occurred_at=occurred_at,
    )
    if event.to_wire() != wire:  # canonical form only (UTC "Z" time, decimal version), as the publisher writes it
        raise IngressRejected("envelope_shape")
    return event


def check(event: EventEnvelope, *, environment: str) -> None:
    """Environment, registered privacy class, closed envelope and payload."""
    if event.environment != environment:
        raise IngressRejected("environment_mismatch")
    for contracts in (registry, CONSUMER_COPIES):
        try:
            expected = contracts.get(event.event_type, event.schema_version)
        except EventValidationError:
            continue
        if event.privacy_class != expected.privacy_class:
            raise IngressRejected("privacy_class_mismatch")
        try:
            event.validate(contracts)
        except EventValidationError:
            raise IngressRejected("contract_invalid") from None
        return
    raise IngressRejected("unsupported_contract")


@dataclass(frozen=True)
class Outcome:
    ack: bool
    code: str


class LaneSubscriber:
    """Routes this lane's subscribed contracts to their consumers. A contract may
    have several consumers (rewards and the persona card both follow
    ``persona.updated``); each is idempotent, so a redelivery after a partial
    failure repeats nothing."""

    def __init__(self, database: Any, *, environment: str, rewards: Any = None, wardrobe: Any = None, cards: Any = None):
        if environment not in ("demo", "development", "sandbox", "production"):
            raise ValueError("explicit Brand.Me environment required")
        from brandme_core.domains.persona.card import TRIGGERS, PersonaCardConsumer
        from brandme_core.domains.persona.lane import load_domains
        from brandme_core.domains.rewards.consumer import HANDLED, RewardsConsumer
        from brandme_core.domains.social.houses import catalog_variant_lookup
        from brandme_core.domains.wardrobe.service import WardrobeService

        load_domains()
        self.environment = environment
        rewards = rewards or RewardsConsumer(database)
        wardrobe = wardrobe or WardrobeService(database, catalog_lookup=catalog_variant_lookup(database))
        cards = cards or PersonaCardConsumer(database)
        self.routes: Dict[str, List[Callable[[EventEnvelope], Mapping[str, Any]]]] = {t: [rewards.handle] for t in HANDLED}
        self.routes["commerce.order.observed"] = [wardrobe.apply_order_observation]
        for t in TRIGGERS:
            self.routes.setdefault(t, []).append(cards.handle)

    def handle_message(self, data: bytes, attributes: Mapping[str, str]) -> Outcome:
        if attributes.get("event_type") not in self.routes:
            return Outcome(True, "not_subscribed")  # other domains' contracts on the shared topic
        try:
            event = decode(data, attributes)
            check(event, environment=self.environment)
        except IngressRejected as rejected:
            return Outcome(False, rejected.code)
        from brandme_core.domains.persona.kernel import ValidationFailed

        statuses = []
        try:
            for handler in self.routes[event.event_type]:
                statuses.append(str(handler(event).get("status", "processed")))
        except ValidationFailed:
            return Outcome(False, "payload_rejected")
        except Exception:
            return Outcome(False, "apply_failed")  # retried; each consumer's inbox makes the retry safe
        return Outcome(True, statuses[0])  # the contract's primary consumer; a side consumer's failure still retries


def emulator_base(host: str, environment: str) -> str:
    if environment not in ("demo", "development"):
        raise ValueError("Pub/Sub emulator forbidden in sandbox and production")
    parts = urlsplit("http://" + host)
    if parts.username or parts.password or parts.path or parts.query or parts.fragment or not parts.port:
        raise ValueError("invalid Pub/Sub emulator host")
    local = parts.hostname in ("localhost", "pubsub", "pubsub-emulator")
    try:
        local = local or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        pass
    if not local:
        raise ValueError("Pub/Sub emulator must be local")
    return f"http://{host}/v1/"


class PubSubPull:
    """Minimal synchronous pull client (REST). Emulator in demo/development,
    Application Default Credentials otherwise. No redirects, no ambient proxy."""

    def __init__(self, subscription: str, environment: str, *, emulator_host: str = "", timeout_seconds: float = 5):
        import requests

        if not SUBSCRIPTION.fullmatch(subscription) or not subscription.split("/subscriptions/")[1].startswith(f"brandme-{environment}-"):
            raise ValueError("subscription must be canonical and scoped to the environment")
        self.subscription, self.timeout = subscription, timeout_seconds
        if emulator_host:
            self.base = emulator_base(emulator_host, environment)
            self.session = requests.Session()
        else:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/pubsub"])
            self.base = "https://pubsub.googleapis.com/v1/"
            self.session = AuthorizedSession(credentials)
        self.session.trust_env = False

    def _post(self, verb: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        r = self.session.post(f"{self.base}{self.subscription}:{verb}", json=body, timeout=self.timeout, allow_redirects=False, stream=True)
        try:
            raw = r.raw.read(MAX_PULL_BYTES + 1, decode_content=True)
        finally:
            r.close()
        if r.status_code != 200 or len(raw) > MAX_PULL_BYTES:
            raise RuntimeError("pubsub_request_failed")
        return json.loads(raw or b"{}")

    def pull(self, max_messages: int) -> List[Tuple[str, bytes, Dict[str, str]]]:
        out = []
        for m in self._post("pull", {"maxMessages": max_messages, "returnImmediately": True}).get("receivedMessages", []):
            msg = m.get("message", {})
            try:
                data = base64.b64decode(msg.get("data", ""), validate=True)
            except (binascii.Error, ValueError):
                data = b""
            out.append((m["ackId"], data, dict(msg.get("attributes") or {})))
        return out

    def ack(self, ack_ids: List[str]) -> None:
        if ack_ids:
            self._post("acknowledge", {"ackIds": ack_ids})

    def nack(self, ack_ids: List[str]) -> None:
        if ack_ids:
            self._post("modifyAckDeadline", {"ackIds": ack_ids, "ackDeadlineSeconds": 0})

    def close(self) -> None:
        self.session.close()


def run_once(transport: Any, subscriber: LaneSubscriber, *, max_messages: int = 10) -> Dict[str, int]:
    """Pull one batch, apply each message, ack after commit, nack the rest."""
    counts: Dict[str, int] = {}
    acks, nacks = [], []
    for ack_id, data, attributes in transport.pull(max_messages):
        outcome = subscriber.handle_message(data, attributes)
        (acks if outcome.ack else nacks).append(ack_id)
        counts[outcome.code] = counts.get(outcome.code, 0) + 1
    transport.ack(acks)
    transport.nack(nacks)
    return counts


def _config(env: Mapping[str, str]) -> Dict[str, str]:
    environment = env.get("ENVIRONMENT", "")
    if environment not in ("demo", "development", "sandbox", "production") or env.get("BRANDME_MODE") != environment:
        raise ValueError("BRANDME_MODE and ENVIRONMENT must agree")
    strict = environment in ("sandbox", "production")
    if strict and (env.get("SPANNER_EMULATOR_HOST") or env.get("PUBSUB_EMULATOR_HOST")):
        raise ValueError("emulators forbidden in sandbox and production")
    if not strict and not (env.get("SPANNER_EMULATOR_HOST") and env.get("PUBSUB_EMULATOR_HOST")):
        raise ValueError("demo/development requires both emulators")
    keys = ("SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID", "LANE_PUBSUB_SUBSCRIPTION")
    if any(not env.get(k, "").strip() for k in keys):
        raise ValueError("explicit Spanner and subscription configuration required")
    return {"environment": environment, "emulator": env.get("PUBSUB_EMULATOR_HOST", ""), **{k: env[k] for k in keys}}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Consumer-domains lane Pub/Sub subscriber")
    parser.add_argument("--once", action="store_true", help="process one batch and exit")
    args = parser.parse_args(argv)
    try:
        cfg = _config(os.environ)
        from google.cloud import spanner

        db = spanner.Client(project=cfg["SPANNER_PROJECT_ID"]).instance(cfg["SPANNER_INSTANCE_ID"]).database(cfg["SPANNER_DATABASE_ID"])
        transport = PubSubPull(cfg["LANE_PUBSUB_SUBSCRIPTION"], cfg["environment"], emulator_host=cfg["emulator"])
        subscriber = LaneSubscriber(db, environment=cfg["environment"])
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    print(json.dumps({"status": "ready", "environment": cfg["environment"], "contracts": len(subscriber.routes)}), flush=True)
    try:
        while not stop.is_set():
            try:
                counts = run_once(transport, subscriber)
            except Exception:
                print('{"status":"pull_unavailable"}', flush=True)
                if args.once:
                    return 1
                stop.wait(5)
                continue
            if counts or args.once:
                print(json.dumps({"status": "applied", **counts}, sort_keys=True), flush=True)
            if args.once:
                return 0
            if not counts:
                stop.wait(2)
        return 0
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
