"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Entitlement projection: chain observation → RightsEntitlements.

Only finalized operations with block evidence are projected. Application
data can never create or advance an entitlement: the projection is
idempotent per transaction and monotonic in epoch, so a replayed or stale
observation cannot roll ownership back.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, param_types as pt
from google.cloud.spanner_v1.database import Database

from brandme_core.events import EventEnvelope, write_events
from brandme_core.domains.events import RIGHTS_ENTITLEMENT_PROJECTED


class ProjectionRejected(Exception):
    pass


@dataclass(frozen=True)
class FinalizedObservation:
    """Built from a ChainOperation in state Finalized plus the contract ledger read at that block."""
    network: str
    contract_address: str
    operation_state: str
    tx_id: str
    block_height: int
    block_hash: str
    finalized_at: datetime
    entitlement_id: str
    issuer_id: str
    epoch: int
    status: str
    transferable: bool
    reprintable: bool
    parent_consumption: Optional[str] = None
    asset_id: Optional[str] = None


def apply_observation(db: Database, o: FinalizedObservation, controller_subject_ref: Optional[str] = None, *, environment: str) -> str:
    """Returns 'inserted' | 'advanced' | 'unchanged'. Raises ProjectionRejected for non-final evidence."""
    if o.operation_state != "Finalized" or not o.block_hash or o.block_height < 0:
        raise ProjectionRejected("only finalized chain evidence is projected")
    if o.status not in ("active", "revoked"):
        raise ProjectionRejected(f"unknown status {o.status}")
    if o.network == "mainnet":
        raise ProjectionRejected("Mainnet is not enabled in this build")

    event = EventEnvelope(
        event_type=RIGHTS_ENTITLEMENT_PROJECTED.event_type, schema_version="1", aggregate_type="rights_entitlement",
        aggregate_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"brandme:rights:{o.network}:{o.contract_address}:{o.entitlement_id}")),
        aggregate_version=1,
        environment=environment, actor_ref="service:chain-reconciler", correlation_id=str(uuid.uuid4()),
        privacy_class="restricted", payload={"network": o.network, "contract_address": o.contract_address,
            "entitlement_id": o.entitlement_id, "epoch": str(o.epoch), "tx_id": o.tx_id,
            "block_height": str(o.block_height), "block_hash": o.block_hash},
    )
    event.validate()

    def fn(txn: Any) -> str:
        rows = list(txn.execute_sql(
            "SELECT epoch, status, last_block_height, projection_version FROM RightsEntitlements "
            "WHERE network = @n AND contract_address = @c AND entitlement_id = @e",
            params={"n": o.network, "c": o.contract_address, "e": o.entitlement_id},
            param_types={"n": pt.STRING, "c": pt.STRING, "e": pt.STRING}))
        cols = ["network", "contract_address", "entitlement_id", "asset_id", "issuer_id", "epoch", "status", "transferable",
                "reprintable", "parent_consumption", "controller_subject_ref", "last_tx_id", "last_block_height", "finalized_at", "updated_at", "projection_version"]
        vals = [o.network, o.contract_address, o.entitlement_id, o.asset_id, o.issuer_id, o.epoch, o.status, o.transferable,
                o.reprintable, o.parent_consumption, controller_subject_ref, o.tx_id, o.block_height, o.finalized_at, COMMIT_TIMESTAMP, 1]
        if not rows:
            event.aggregate_version = 1
            txn.insert("RightsEntitlements", cols, [vals])
            write_events(txn, [event])
            return "inserted"
        epoch, status, height, version = rows[0]
        newer = (o.block_height, o.epoch) > (height, epoch)
        if not newer:
            return "unchanged"
        if o.epoch < epoch:
            raise ProjectionRejected("epoch cannot decrease")
        if status == "revoked" and o.status == "active":
            raise ProjectionRejected("revoked entitlement cannot be re-activated by a projection")
        if o.epoch > epoch and controller_subject_ref is None:
            vals[cols.index("controller_subject_ref")] = None   # control moved; old member link is dropped
        event.aggregate_version = (version or 0) + 1
        vals[-1] = event.aggregate_version
        txn.update("RightsEntitlements", cols, [vals])
        write_events(txn, [event])
        return "advanced"

    return db.run_in_transaction(fn)
