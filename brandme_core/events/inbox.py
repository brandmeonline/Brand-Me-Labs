"""Consumer-side dedupe for at-least-once delivery.

A consumer calls ``first_delivery`` inside the same read/write transaction as
its state change. If the receipt already exists the consumer skips the effect;
because the receipt and the effect commit atomically, a redelivered event can
never apply twice.
"""
from __future__ import annotations

from .envelope import EventEnvelope


def first_delivery(transaction, consumer: str, event: EventEnvelope) -> bool:
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, KeySet

    existing = list(transaction.read("InboxReceipts", columns=("event_id",),
                                     keyset=KeySet(keys=[[consumer, event.event_id]])))
    if existing:
        return False
    transaction.insert(
        "InboxReceipts",
        columns=("consumer", "event_id", "event_type", "received_at"),
        values=[(consumer, event.event_id, event.event_type, COMMIT_TIMESTAMP)],
    )
    return True
