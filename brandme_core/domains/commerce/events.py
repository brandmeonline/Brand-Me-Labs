"""Commerce event types, registered with the foundation event registry (ch.03 §5).

Every payload is a closed schema with references only: no addresses, payment
data or provider response bodies. ``write_events`` / ``EventEnvelope.validate``
reject anything unregistered or out of shape.
"""

from __future__ import annotations

from brandme_core.domains.events import UUID, closed, register

_REF = {"type": "string", "minLength": 1, "maxLength": 256}
_SHORT = {"type": "string", "minLength": 1, "maxLength": 80}
_HASH = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
_QTY = {"type": "integer", "minimum": 0, "maximum": 99}

DELEGATION_CREATED = register(
    "commerce.delegation.created", "1",
    closed({"delegation_id": UUID, "mode": {"enum": ["research", "prepare", "buy_within_rules"]},
            "client_id": _REF}, ("delegation_id", "mode", "client_id")),
    "member_private")

DELEGATION_REVOKED = register(
    "commerce.delegation.revoked", "1",
    closed({"delegation_id": UUID}, ("delegation_id",)), "member_private")

QUOTE_READY = register(
    "commerce.quote.ready", "1",
    closed({"quote_id": UUID, "quote_hash": _HASH, "cart_id": UUID}, ("quote_id", "quote_hash", "cart_id")),
    "member_private")

PURCHASE_APPROVAL_REQUESTED = register(
    "commerce.purchase.approval_requested", "1",
    closed({"operation_id": UUID, "quote_id": UUID}, ("operation_id", "quote_id")), "member_private")

PURCHASE_AUTHORIZED = register(
    "commerce.purchase.authorized", "1",
    closed({"operation_id": UUID, "approval_id": UUID, "quote_hash": _HASH,
            "protocol": {"enum": ["ap2/0.2"]}, "protocol_payload_hash": _HASH},
           ("operation_id", "approval_id", "quote_hash")),
    "member_private")

_ORDER_LINE = closed({
    "variant_id": {"anyOf": [UUID, {"type": "null"}]}, "source_variant_ref": _REF,
    "ordered": {"type": "integer", "minimum": 1, "maximum": 99}, "shipped": _QTY, "delivered": _QTY,
    "returned": _QTY, "exchanged_from_ref": {"anyOf": [_REF, {"type": "null"}]},
}, ("variant_id", "source_variant_ref", "ordered", "shipped", "delivered", "returned", "exchanged_from_ref"))

ORDER_OBSERVED = register(
    "commerce.order.observed", "1",
    closed({
        "order_id": UUID, "operation_id": UUID, "member_id": UUID, "provider_id": _SHORT,
        "order_status": {"enum": ["accepted", "rejected", "cancelled"]},
        "payment_status": {"enum": ["unknown", "authorized", "captured", "partially_refunded", "refunded", "failed"]},
        "fulfillment_status": {"enum": ["unfulfilled", "partially_fulfilled", "fulfilled"]},
        # exchanged: an original line was returned and a replacement line (exchanged_from_ref) added.
        "wardrobe_effect": {"enum": ["incoming", "arrived", "returned", "exchanged", "updated"]},
        "lines": {"type": "array", "minItems": 1, "maxItems": 100, "items": _ORDER_LINE},
        "acquisition_evidence": {"type": "array", "maxItems": 50, "items": _REF},
    }, ("order_id", "operation_id", "member_id", "provider_id", "order_status", "payment_status",
        "fulfillment_status", "wardrobe_effect", "lines", "acquisition_evidence")),
    "member_private")
