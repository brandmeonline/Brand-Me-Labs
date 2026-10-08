"""Event envelope, transactional outbox and inbox dedupe (opus-foundation lane).

Delivery adapters (NATS locally; Cloud Tasks / Pub/Sub in cloud) plug into
``OutboxDispatcher(deliver=...)``. One environment selects one adapter per
event type; there is never a second event authority.
"""
from .envelope import (
    EventEnvelope,
    EventRegistry,
    EventType,
    EventValidationError,
    FORBIDDEN_PAYLOAD_KEYS,
    PRIVACY_CLASSES,
    registry,
)
from .inbox import first_delivery
from .outbox import DispatchResult, OutboxDispatcher, SHARDS, shard_for, write_events

__all__ = [
    "EventEnvelope", "EventRegistry", "EventType", "EventValidationError", "FORBIDDEN_PAYLOAD_KEYS",
    "PRIVACY_CLASSES", "registry", "first_delivery", "DispatchResult", "OutboxDispatcher", "SHARDS",
    "shard_for", "write_events",
]
