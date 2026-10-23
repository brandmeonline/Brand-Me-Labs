"""Bounded Pub/Sub REST publisher. Broker acknowledgement is not consumption.

The application event_id is stable across retries. Pub/Sub assigns a different
messageId to a repeated publish; subscribers deduplicate the application ID.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import re
from typing import Mapping
from urllib.parse import urlsplit

import requests

from .envelope import EventEnvelope, PRIVACY_CLASSES
from .outbox import PermanentDeliveryError

MAX_EVENT_BYTES = 256 * 1024
MAX_ACK_BYTES = 16 * 1024
TOPIC = re.compile(r"projects/[a-z][a-z0-9-]{4,61}[a-z0-9]/topics/[A-Za-z][A-Za-z0-9._~-]{2,254}\Z")


def emulator_endpoint(host: str, environment: str) -> str:
    if environment not in {"demo", "development"}:
        raise ValueError("Pub/Sub emulator forbidden in sandbox and production")
    parts = urlsplit("http://" + host)
    if parts.username or parts.password or parts.path or parts.query or parts.fragment or not parts.port:
        raise ValueError("invalid Pub/Sub emulator host")
    # Local test process or a private container-network service; never an
    # arbitrary public server receiving otherwise private event references.
    local = parts.hostname in {"localhost", "pubsub", "pubsub-emulator"}
    try:
        local = local or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        pass
    if not local:
        raise ValueError("Pub/Sub emulator must be local")
    return f"http://{host}/v1/"


class PubSubPublisher:
    def __init__(self, topics: Mapping[str, str], environment: str, *, emulator_host: str = "",
                 timeout_seconds: float = 5):
        if environment not in {"demo", "development", "sandbox", "production"}:
            raise ValueError("explicit event environment required")
        if set(topics) != set(PRIVACY_CLASSES) or len(set(topics.values())) != len(PRIVACY_CLASSES):
            raise ValueError("three distinct privacy-class topics required")
        if any(not TOPIC.fullmatch(t) or not t.split("/topics/")[1].startswith(f"brandme-{environment}-")
               for t in topics.values()):
            raise ValueError("topics must be canonical and scoped to the event environment")
        if not 0 < timeout_seconds <= 10:
            raise ValueError("invalid publisher deadline")
        self.topics, self.environment, self.timeout = dict(topics), environment, timeout_seconds
        self.emulated = bool(emulator_host)
        if self.emulated:
            self.endpoint = emulator_endpoint(emulator_host, environment)
            self.session = requests.Session()
        else:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/pubsub"])
            self.session = AuthorizedSession(credentials, refresh_timeout=timeout_seconds, max_refresh_attempts=0)
            self.endpoint = "https://pubsub.googleapis.com/v1/"
        self.session.trust_env = False  # no ambient proxy or .netrc credentials

    def _request(self, method: str, topic: str, suffix: str = "", body=None) -> dict:
        kwargs = {} if self.emulated else {"max_allowed_time": self.timeout}
        with self.session.request(method, self.endpoint + topic + suffix, json=body,
                                  timeout=self.timeout, allow_redirects=False, stream=True, **kwargs) as response:
            # Never include provider response bodies/URLs in an exception.
            if not 200 <= response.status_code < 300:
                raise RuntimeError("pubsub_request_unconfirmed")
            data = bytearray()
            for chunk in response.iter_content(2048):
                data.extend(chunk)
                if len(data) > MAX_ACK_BYTES:
                    raise RuntimeError("pubsub_response_invalid")
            try:
                value = json.loads(data)
            except (ValueError, UnicodeError):
                raise RuntimeError("pubsub_response_invalid") from None
            if not isinstance(value, dict):
                raise RuntimeError("pubsub_response_invalid")
            return value

    def check_topics(self) -> None:
        """Refuse an unprovisioned/misrouted target; never create cloud resources."""
        for topic in self.topics.values():
            if self._request("GET", topic).get("name") != topic:
                raise RuntimeError("pubsub_topic_mismatch")

    def __call__(self, event: EventEnvelope) -> None:
        if event.environment != self.environment or event.privacy_class not in self.topics:
            raise PermanentDeliveryError("event_route_invalid")
        event.validate()
        data = json.dumps(event.to_wire(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(data) > MAX_EVENT_BYTES:
            raise PermanentDeliveryError("event_too_large")
        result = self._request("POST", self.topics[event.privacy_class], ":publish", {
            "messages": [{"data": base64.b64encode(data).decode("ascii"), "attributes": {
                "event_id": event.event_id, "event_type": event.event_type,
                "schema_version": event.schema_version, "environment": event.environment,
                "privacy_class": event.privacy_class,
            }}],
        })
        ids = result.get("messageIds")
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not ids[0]:
            raise RuntimeError("pubsub_ack_invalid")

    def close(self) -> None:
        self.session.close()
