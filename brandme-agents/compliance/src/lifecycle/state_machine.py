"""
Brand.Me v9 — DPP Lifecycle State Machine
==========================================

Implements the Digital Product Passport state machine for circular economy.

State Transitions:
    PRODUCED → ACTIVE        (Ownership transfer from factory)
    ACTIVE   → REPAIR        (User initiates repair)
    REPAIR   → ACTIVE        (Repair complete)
    ACTIVE   → DISSOLVE      (End of life, requires dissolve_auth_key)
    REPAIR   → DISSOLVE      (Unrepairable, requires dissolve_auth_key)
    DISSOLVE → REPRINT       (Requires Midnight burn proof)
    REPRINT  → PRODUCED      (New item created, generation incremented)
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from brandme_core.logging import get_logger

logger = get_logger("lifecycle.state_machine")


class LifecycleState(str, Enum):
    """DPP Lifecycle states."""
    PRODUCED = "PRODUCED"
    ACTIVE = "ACTIVE"
    REPAIR = "REPAIR"
    DISSOLVE = "DISSOLVE"
    REPRINT = "REPRINT"


class StateTransitionError(Exception):
    """Invalid state transition attempted."""
    pass


class BurnProofRequiredError(Exception):
    """Burn proof required for DISSOLVE→REPRINT transition."""
    pass


class DissolveAuthRequiredError(Exception):
    """Dissolve authorization required for →DISSOLVE transition."""
    pass


@dataclass
class TransitionRequest:
    """Request to transition an asset's lifecycle state."""
    asset_id: str
    from_state: LifecycleState
    to_state: LifecycleState
    triggered_by: str                           # user_id or agent_id
    trigger_type: str                           # "user", "agent", "system"
    dissolve_auth_key: Optional[str] = None     # Required for →DISSOLVE
    burn_proof_hash: Optional[str] = None       # Required for DISSOLVE→REPRINT
    parent_material_batch: Optional[str] = None # For REPRINT lineage
    notes: Optional[str] = None


@dataclass
class TransitionResult:
    """Result of a state transition."""
    success: bool
    event_id: str
    from_state: LifecycleState
    to_state: LifecycleState
    esg_delta: Optional[float] = None
    carbon_saved_kg: Optional[float] = None
    water_saved_liters: Optional[float] = None
    error: Optional[str] = None
    requires_human_approval: bool = False
    audit_hash: Optional[str] = None


@dataclass
class LifecycleEvent:
    """Recorded lifecycle event."""
    event_id: str
    asset_id: str
    from_state: Optional[LifecycleState]
    to_state: LifecycleState
    triggered_by: str
    trigger_type: str
    dissolve_auth_verified: bool = False
    burn_proof_hash: Optional[str] = None
    parent_material_batch: Optional[str] = None
    esg_delta: Optional[float] = None
    carbon_saved_kg: Optional[float] = None
    water_saved_liters: Optional[float] = None
    cardano_tx_hash: Optional[str] = None
    midnight_tx_hash: Optional[str] = None
    occurred_at: datetime = field(default_factory=datetime.utcnow)


class LifecycleStateMachine:
    """
    DPP Lifecycle State Machine for circular economy.

    Manages transitions between lifecycle states with proper validation,
    burn proof verification, and ESG tracking.
    """

    # Valid state transitions
    VALID_TRANSITIONS: Dict[LifecycleState, List[LifecycleState]] = {
        LifecycleState.PRODUCED: [LifecycleState.ACTIVE],
        LifecycleState.ACTIVE: [LifecycleState.REPAIR, LifecycleState.DISSOLVE],
        LifecycleState.REPAIR: [LifecycleState.ACTIVE, LifecycleState.DISSOLVE],
        LifecycleState.DISSOLVE: [LifecycleState.REPRINT],
        LifecycleState.REPRINT: [LifecycleState.PRODUCED],
    }

    # Transitions requiring special authorization
    DISSOLVE_AUTH_REQUIRED = [
        (LifecycleState.ACTIVE, LifecycleState.DISSOLVE),
        (LifecycleState.REPAIR, LifecycleState.DISSOLVE),
    ]

    BURN_PROOF_REQUIRED = [
        (LifecycleState.DISSOLVE, LifecycleState.REPRINT),
    ]

    # ESG impact estimates for transitions (positive = improvement)
    ESG_IMPACT: Dict[tuple, Dict[str, float]] = {
        (LifecycleState.ACTIVE, LifecycleState.REPAIR): {
            "esg_delta": 0.1,
            "carbon_saved_kg": 2.5,
            "water_saved_liters": 50.0,
        },
        (LifecycleState.DISSOLVE, LifecycleState.REPRINT): {
            "esg_delta": 0.3,
            "carbon_saved_kg": 8.0,
            "water_saved_liters": 200.0,
        },
    }

    def __init__(
        self,
        spanner_pool,
        burn_proof_verifier=None,
        esg_verifier=None,
        min_esg_score: float = 0.5
    ):
        """
        Initialize the state machine.

        Args:
            spanner_pool: Spanner connection pool
            burn_proof_verifier: Midnight burn proof verifier
            esg_verifier: Cardano ESG score verifier
            min_esg_score: Minimum ESG score for transactions
        """
        self.spanner_pool = spanner_pool
        self.burn_proof_verifier = burn_proof_verifier
        self.esg_verifier = esg_verifier
        self.min_esg_score = min_esg_score

    def is_valid_transition(
        self,
        from_state: LifecycleState,
        to_state: LifecycleState
    ) -> bool:
        """Check if a state transition is valid."""
        valid_targets = self.VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_targets

    def requires_dissolve_auth(
        self,
        from_state: LifecycleState,
        to_state: LifecycleState
    ) -> bool:
        """Check if transition requires dissolve authorization."""
        return (from_state, to_state) in self.DISSOLVE_AUTH_REQUIRED

    def requires_burn_proof(
        self,
        from_state: LifecycleState,
        to_state: LifecycleState
    ) -> bool:
        """Check if transition requires burn proof."""
        return (from_state, to_state) in self.BURN_PROOF_REQUIRED

    async def get_current_state(self, asset_id: str) -> Optional[LifecycleState]:
        """Get the current lifecycle state of an asset."""
        from google.cloud.spanner_v1 import param_types

        def _get_state(transaction):
            results = transaction.execute_sql(
                """
                SELECT lifecycle_state FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": asset_id},
                param_types={"asset_id": param_types.STRING}
            )
            for row in results:
                return LifecycleState(row[0]) if row[0] else None
            return None

        return self.spanner_pool.database.run_in_transaction(_get_state)

    async def verify_dissolve_auth(
        self,
        asset_id: str,
        dissolve_auth_key: str
    ) -> bool:
        """
        Verify dissolve authorization key against stored hash.

        Args:
            asset_id: The asset being dissolved
            dissolve_auth_key: The provided authorization key

        Returns:
            True if key matches, False otherwise
        """
        from google.cloud.spanner_v1 import param_types

        # Hash the provided key
        key_hash = hashlib.sha256(dissolve_auth_key.encode()).hexdigest()

        def _verify(transaction):
            results = transaction.execute_sql(
                """
                SELECT m.dissolve_auth_key_hash
                FROM Assets a
                JOIN Materials m ON a.primary_material_id = m.material_id
                WHERE a.asset_id = @asset_id
                """,
                params={"asset_id": asset_id},
                param_types={"asset_id": param_types.STRING}
            )
            for row in results:
                stored_hash = row[0]
                return stored_hash == key_hash
            return False

        return self.spanner_pool.database.run_in_transaction(_verify)

    async def verify_burn_proof(
        self,
        burn_proof_hash: str,
        parent_asset_id: str
    ) -> bool:
        """
        Verify Midnight burn proof for DISSOLVE→REPRINT transition.

        Args:
            burn_proof_hash: Hash of the burn proof from Midnight
            parent_asset_id: ID of the dissolved parent asset

        Returns:
            True if burn proof is valid
        """
        if self.burn_proof_verifier:
            return await self.burn_proof_verifier.verify(
                burn_proof_hash,
                parent_asset_id
            )

        # Stub: In production, verify against Midnight
        logger.warning({
            "event": "burn_proof_stub_verification",
            "burn_proof_hash": burn_proof_hash[:16] + "...",
            "parent_asset_id": parent_asset_id[:8] + "..."
        })
        return True

    async def transition(
        self,
        request: TransitionRequest
    ) -> TransitionResult:
        """
        Execute a lifecycle state transition.

        Args:
            request: The transition request

        Returns:
            TransitionResult with success status and details
        """
        from google.cloud import spanner
        from google.cloud.spanner_v1 import param_types

        event_id = str(uuid.uuid4())

        # Validate transition
        if not self.is_valid_transition(request.from_state, request.to_state):
            return TransitionResult(
                success=False,
                event_id=event_id,
                from_state=request.from_state,
                to_state=request.to_state,
                error=f"Invalid transition: {request.from_state.value} → {request.to_state.value}"
            )

        # Check dissolve authorization
        if self.requires_dissolve_auth(request.from_state, request.to_state):
            if not request.dissolve_auth_key:
                raise DissolveAuthRequiredError(
                    "Dissolve authorization key required for this transition"
                )
            is_authorized = await self.verify_dissolve_auth(
                request.asset_id,
                request.dissolve_auth_key
            )
            if not is_authorized:
                return TransitionResult(
                    success=False,
                    event_id=event_id,
                    from_state=request.from_state,
                    to_state=request.to_state,
                    error="Invalid dissolve authorization key"
                )

        # Check burn proof
        if self.requires_burn_proof(request.from_state, request.to_state):
            if not request.burn_proof_hash:
                raise BurnProofRequiredError(
                    "Midnight burn proof required for DISSOLVE→REPRINT transition"
                )
            if not request.parent_material_batch:
                raise BurnProofRequiredError(
                    "Parent material batch required for REPRINT lineage"
                )
            is_valid = await self.verify_burn_proof(
                request.burn_proof_hash,
                request.asset_id
            )
            if not is_valid:
                return TransitionResult(
                    success=False,
                    event_id=event_id,
                    from_state=request.from_state,
                    to_state=request.to_state,
                    error="Invalid burn proof"
                )

        # Get ESG impact
        esg_impact = self.ESG_IMPACT.get(
            (request.from_state, request.to_state),
            {"esg_delta": 0.0, "carbon_saved_kg": 0.0, "water_saved_liters": 0.0}
        )

        # Execute transition in Spanner
        def _execute_transition(transaction):
            # Update asset lifecycle state
            transaction.update(
                table="Assets",
                columns=["asset_id", "lifecycle_state", "updated_at"],
                values=[(
                    request.asset_id,
                    request.to_state.value,
                    spanner.COMMIT_TIMESTAMP
                )]
            )

            # Insert lifecycle event
            transaction.insert(
                table="LifecycleEvents",
                columns=[
                    "event_id", "asset_id", "from_state", "to_state",
                    "triggered_by", "trigger_type", "dissolve_auth_verified",
                    "burn_proof_hash", "parent_material_batch",
                    "esg_delta", "carbon_saved_kg", "water_saved_liters",
                    "notes", "occurred_at"
                ],
                values=[(
                    event_id,
                    request.asset_id,
                    request.from_state.value if request.from_state else None,
                    request.to_state.value,
                    request.triggered_by,
                    request.trigger_type,
                    self.requires_dissolve_auth(request.from_state, request.to_state),
                    request.burn_proof_hash,
                    request.parent_material_batch,
                    esg_impact["esg_delta"],
                    esg_impact["carbon_saved_kg"],
                    esg_impact["water_saved_liters"],
                    request.notes,
                    spanner.COMMIT_TIMESTAMP
                )]
            )

            # If REPRINT→PRODUCED, increment reprint_generation
            if request.from_state == LifecycleState.REPRINT:
                transaction.execute_sql(
                    """
                    UPDATE Assets
                    SET reprint_generation = reprint_generation + 1,
                        updated_at = PENDING_COMMIT_TIMESTAMP()
                    WHERE asset_id = @asset_id
                    """,
                    params={"asset_id": request.asset_id},
                    param_types={"asset_id": param_types.STRING}
                )

            return True

        try:
            self.spanner_pool.database.run_in_transaction(_execute_transition)

            # Create audit hash
            audit_input = f"{event_id}{request.asset_id}{request.to_state.value}"
            audit_hash = hashlib.sha256(audit_input.encode()).hexdigest()

            logger.info({
                "event": "lifecycle_transition_complete",
                "event_id": event_id,
                "asset_id": request.asset_id[:8] + "...",
                "from_state": request.from_state.value if request.from_state else None,
                "to_state": request.to_state.value,
                "triggered_by": request.triggered_by[:8] + "...",
                "esg_delta": esg_impact["esg_delta"]
            })

            return TransitionResult(
                success=True,
                event_id=event_id,
                from_state=request.from_state,
                to_state=request.to_state,
                esg_delta=esg_impact["esg_delta"],
                carbon_saved_kg=esg_impact["carbon_saved_kg"],
                water_saved_liters=esg_impact["water_saved_liters"],
                audit_hash=audit_hash
            )

        except Exception as e:
            logger.error({
                "event": "lifecycle_transition_failed",
                "event_id": event_id,
                "asset_id": request.asset_id[:8] + "...",
                "error": str(e)
            })
            return TransitionResult(
                success=False,
                event_id=event_id,
                from_state=request.from_state,
                to_state=request.to_state,
                error=str(e)
            )

    async def get_lifecycle_history(
        self,
        asset_id: str
    ) -> List[LifecycleEvent]:
        """
        Get full lifecycle history for an asset.

        Args:
            asset_id: The asset ID

        Returns:
            List of lifecycle events ordered by time
        """
        from google.cloud.spanner_v1 import param_types

        def _get_history(transaction):
            results = transaction.execute_sql(
                """
                SELECT
                    event_id, asset_id, from_state, to_state,
                    triggered_by, trigger_type, dissolve_auth_verified,
                    burn_proof_hash, parent_material_batch,
                    esg_delta, carbon_saved_kg, water_saved_liters,
                    cardano_tx_hash, midnight_tx_hash, occurred_at
                FROM LifecycleEvents
                WHERE asset_id = @asset_id
                ORDER BY occurred_at ASC
                """,
                params={"asset_id": asset_id},
                param_types={"asset_id": param_types.STRING}
            )

            events = []
            for row in results:
                events.append(LifecycleEvent(
                    event_id=row[0],
                    asset_id=row[1],
                    from_state=LifecycleState(row[2]) if row[2] else None,
                    to_state=LifecycleState(row[3]),
                    triggered_by=row[4],
                    trigger_type=row[5],
                    dissolve_auth_verified=row[6],
                    burn_proof_hash=row[7],
                    parent_material_batch=row[8],
                    esg_delta=row[9],
                    carbon_saved_kg=row[10],
                    water_saved_liters=row[11],
                    cardano_tx_hash=row[12],
                    midnight_tx_hash=row[13],
                    occurred_at=row[14]
                ))
            return events

        return self.spanner_pool.database.run_in_transaction(_get_history)

    async def get_circularity_metrics(
        self,
        asset_id: str
    ) -> Dict[str, Any]:
        """
        Get circularity metrics for an asset.

        Returns total ESG impact, repair count, reprint generation.
        """
        from google.cloud.spanner_v1 import param_types

        def _get_metrics(transaction):
            # Get asset info
            asset_results = transaction.execute_sql(
                """
                SELECT lifecycle_state, reprint_generation
                FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": asset_id},
                param_types={"asset_id": param_types.STRING}
            )
            asset_row = None
            for row in asset_results:
                asset_row = row
                break

            # Get aggregated metrics from lifecycle events
            metrics_results = transaction.execute_sql(
                """
                SELECT
                    COUNT(*) as total_events,
                    SUM(CASE WHEN to_state = 'REPAIR' THEN 1 ELSE 0 END) as repair_count,
                    SUM(COALESCE(esg_delta, 0)) as total_esg_delta,
                    SUM(COALESCE(carbon_saved_kg, 0)) as total_carbon_saved,
                    SUM(COALESCE(water_saved_liters, 0)) as total_water_saved
                FROM LifecycleEvents
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": asset_id},
                param_types={"asset_id": param_types.STRING}
            )
            metrics_row = None
            for row in metrics_results:
                metrics_row = row
                break

            return {
                "current_state": asset_row[0] if asset_row else None,
                "reprint_generation": asset_row[1] if asset_row else 0,
                "total_events": metrics_row[0] if metrics_row else 0,
                "repair_count": metrics_row[1] if metrics_row else 0,
                "total_esg_delta": metrics_row[2] if metrics_row else 0.0,
                "total_carbon_saved_kg": metrics_row[3] if metrics_row else 0.0,
                "total_water_saved_liters": metrics_row[4] if metrics_row else 0.0,
            }

        return self.spanner_pool.database.run_in_transaction(_get_metrics)
