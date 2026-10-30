"""Domain event registration helpers and the identity/platform event types.

Each domain registers its event types (exact payload schema + privacy class)
at import time. ``write_events`` rejects anything unregistered.
"""
from __future__ import annotations

from typing import Any, Mapping

from brandme_core.events import registry

UUID = {"type": "string", "format": "uuid"}


def closed(properties: Mapping[str, Any], required: tuple[str, ...]) -> dict:
    """Build a closed object schema (additionalProperties: false)."""
    return {"type": "object", "additionalProperties": False, "properties": dict(properties), "required": list(required)}


def register(event_type: str, schema_version: str, payload_schema: Mapping[str, Any], privacy_class: str):
    return registry.register(event_type, schema_version, payload_schema, privacy_class)


# Identity / platform events owned by the foundation lane.
MEMBER_CREATED = register(
    "member.created", "1",
    closed({"member_id": UUID, "identity_provider": {"type": "string", "maxLength": 40}}, ("member_id", "identity_provider")),
    "member_private",
)
MEMBER_UPDATED = register(
    "member.updated", "1",
    closed({"member_id": UUID, "changed_fields": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 16}},
           ("member_id", "changed_fields")),
    "member_private",
)
CONSENT_REVOKED = register(
    "consent.revoked", "1",
    closed({"member_id": UUID, "consent_id": UUID, "purpose": {"type": "string", "maxLength": 64}},
           ("member_id", "consent_id", "purpose")),
    "member_private",
)
SESSION_REVOKED = register(
    "session.revoked", "1",
    closed({"member_id": UUID, "reason": {"type": "string", "enum": ["sign_out", "account_switch", "security", "deletion"]}},
           ("member_id", "reason")),
    "restricted",
)

# Rights/My Data integration contracts. References only: no wallet secrets,
# witness values, recipient details, deletion receipts or exported records.
HEX32 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
NETWORK = {"type": "string", "enum": ["undeployed", "preview", "preprod"]}
COUNTER = {"type": "string", "pattern": "^(0|[1-9][0-9]*)$"}
TX_ID = {"type": "string", "minLength": 1, "maxLength": 256}

OWNERSHIP_TRANSFER_REQUESTED = register(
    "ownership.transfer.requested", "1",
    closed({"intent_id": UUID, "network": NETWORK, "entitlement_id": HEX32},
           ("intent_id", "network", "entitlement_id")), "member_private",
)
CHAIN_OPERATION_OBSERVED = register(
    "chain.operation.observed", "1",
    closed({"operation_id": UUID, "network": NETWORK, "tx_id": TX_ID,
            "block_height": COUNTER, "block_hash": TX_ID,
            "state": {"enum": ["Observed", "Finalized"]}},
           ("operation_id", "network", "tx_id", "block_height", "block_hash", "state")), "restricted",
)
LICENSE_ISSUED = register(
    "license.issued", "1", closed({"license_id": UUID, "network": NETWORK, "entitlement_id": HEX32},
                                  ("license_id", "network", "entitlement_id")), "member_private",
)
REPRINT_ATTESTED = register(
    "reprint.attested", "1", closed({"job_id": UUID, "network": NETWORK, "child_entitlement_id": HEX32,
                                     "unit_index": {"type": "integer", "minimum": 0}},
                                    ("job_id", "network", "child_entitlement_id", "unit_index")), "member_private",
)
RIGHTS_ENTITLEMENT_PROJECTED = register(
    "rights.entitlement.projected", "1",
    closed({"network": NETWORK, "contract_address": HEX32, "entitlement_id": HEX32,
            "epoch": COUNTER, "tx_id": TX_ID, "block_height": COUNTER, "block_hash": TX_ID},
           ("network", "contract_address", "entitlement_id", "epoch", "tx_id", "block_height", "block_hash")), "restricted",
)
PRIVACY_DELETION_REQUESTED = register(
    "privacy.deletion.requested", "1",
    closed({"job_id": UUID, "scope": {"enum": ["account", "category"]}}, ("job_id", "scope")), "restricted",
)
PRIVACY_DELETION_COMPLETED = register(
    "privacy.deletion.completed", "1",
    closed({"job_id": UUID, "state": {"enum": ["completed", "completed_with_exceptions"]}},
           ("job_id", "state")), "restricted",
)
