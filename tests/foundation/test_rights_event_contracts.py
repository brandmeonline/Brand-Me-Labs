"""Closed rights/privacy event contracts reject secrets, unknown fields and Mainnet evidence."""
import uuid

import pytest

from brandme_core.events import EventEnvelope, EventValidationError, registry
import brandme_core.domains.events  # noqa: F401

ID = str(uuid.uuid4())
HEX = "ab" * 32
CASES = [
    ("ownership.transfer.requested", {"intent_id": ID, "network": "preprod", "entitlement_id": HEX}),
    ("chain.operation.observed", {"operation_id": ID, "network": "preprod", "tx_id": HEX, "block_height": "42", "block_hash": HEX, "state": "Finalized"}),
    ("license.issued", {"license_id": ID, "network": "preprod", "entitlement_id": HEX}),
    ("reprint.attested", {"job_id": ID, "network": "preprod", "child_entitlement_id": HEX, "unit_index": 0}),
    ("rights.entitlement.projected", {"network": "preprod", "contract_address": HEX, "entitlement_id": HEX, "epoch": "1", "tx_id": HEX, "block_height": "42", "block_hash": HEX}),
    ("privacy.deletion.requested", {"job_id": ID, "scope": "account"}),
    ("privacy.deletion.completed", {"job_id": ID, "state": "completed_with_exceptions"}),
]


@pytest.mark.parametrize("name,payload", CASES)
def test_closed_contract(name, payload):
    event = EventEnvelope(event_type=name, schema_version="1", aggregate_type="test", aggregate_id=ID,
                          aggregate_version=1, environment="development", actor_ref="service:test", correlation_id=ID,
                          privacy_class=registry.get(name, "1").privacy_class, payload=payload)
    event.validate()
    for extra in ({"unexpected": "value"}, {"seed": "private material"}):
        event.payload = {**payload, **extra}
        with pytest.raises(EventValidationError):
            event.validate()
    if "network" in payload:
        event.payload = {**payload, "network": "mainnet"}
        with pytest.raises(EventValidationError):
            event.validate()
