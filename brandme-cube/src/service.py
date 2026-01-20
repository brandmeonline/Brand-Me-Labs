"""
Cube Service - Business Logic
Brand.Me v9 — Cube Service Business Logic

CRITICAL INTEGRITY SPINE PATTERN:
1. NEVER return face data without calling Policy first
2. If Policy returns "allow" → return face data
3. If Policy returns "escalate" → call Compliance, return escalation response
4. If Policy returns "deny" → return 403
5. Log EVERY action to Compliance service

v9 Features:
- 7 faces including molecular_data
- DPP Lifecycle State Machine (PRODUCED→ACTIVE→REPAIR→DISSOLVE→REPRINT)
- Biometric Sync for AR glasses
- Reprint lineage tracking
"""

from typing import Optional, Dict, Any

v9 Features:
- 7 faces including molecular_data
- DPP Lifecycle State Machine (PRODUCED→ACTIVE→REPAIR→DISSOLVE→REPRINT)
- Biometric Sync for AR glasses
- Reprint lineage tracking
"""

import hashlib
import secrets
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import uuid4
from fastapi import HTTPException

from brandme_core.logging import get_logger, redact_user_id, truncate_id
from brandme_core.metrics import MetricsCollector

from .models import (
    ProductCube,
    CubeFace,
    FaceName,
    FaceStatus,
    VisibilityLevel,
    PolicyDecision,
    CreateCubeRequest,
    TransferOwnershipRequest,
    TransferResponse,
    LifecycleState
)
from .clients import (
    PolicyClient,
    ComplianceClient,
    OrchestratorClient,
    IdentityClient
)

logger = get_logger("cube.service")

# v9: Valid lifecycle transitions
VALID_TRANSITIONS = {
    LifecycleState.PRODUCED: [LifecycleState.ACTIVE],
    LifecycleState.ACTIVE: [LifecycleState.REPAIR, LifecycleState.DISSOLVE],
    LifecycleState.REPAIR: [LifecycleState.ACTIVE, LifecycleState.DISSOLVE],
    LifecycleState.DISSOLVE: [LifecycleState.REPRINT],
    LifecycleState.REPRINT: [LifecycleState.PRODUCED],
}

class CubeService:
    """Product Cube business logic with Integrity Spine enforcement (v9)"""

    def __init__(
        self,
        db_pool,
# v9: Valid lifecycle transitions
VALID_TRANSITIONS = {
    LifecycleState.PRODUCED: [LifecycleState.ACTIVE],
    LifecycleState.ACTIVE: [LifecycleState.REPAIR, LifecycleState.DISSOLVE],
    LifecycleState.REPAIR: [LifecycleState.ACTIVE, LifecycleState.DISSOLVE],
    LifecycleState.DISSOLVE: [LifecycleState.REPRINT],
    LifecycleState.REPRINT: [LifecycleState.PRODUCED],
}

class CubeService:
    """Product Cube business logic with Integrity Spine enforcement (v9)"""

    def __init__(
        self,
        spanner_pool,
        policy_client: PolicyClient,
        compliance_client: ComplianceClient,
        orchestrator_client: OrchestratorClient,
        identity_client: IdentityClient,
        metrics: MetricsCollector
    ):
        self.db = db_pool
        self.spanner_pool = spanner_pool
        self.policy = policy_client
        self.compliance = compliance_client
        self.orchestrator = orchestrator_client
        self.identity = identity_client
        self.metrics = metrics

    async def get_cube(
        self,
        cube_id: str,
        viewer_id: str,
        request_id: str
    ) -> ProductCube:
        """
        Get full cube with policy-filtered faces

        CRITICAL: Calls policy for EACH face before returning it
        """
        logger.info(
            "get_cube_requested",
            cube_id=truncate_id(cube_id),
            viewer=redact_user_id(viewer_id),
            request_id=request_id
        )

        # 1. Fetch cube from database
        cube_data = await self._fetch_cube_from_db(cube_id)
        if not cube_data:
            raise HTTPException(status_code=404, detail="Cube not found")

        owner_id = cube_data["owner_id"]

        # 2. For each face, check Policy
        faces_response = {}

        for face_name in FaceName:
            try:
                # Call Policy service
                policy_decision = await self.policy.can_view_face(
                    viewer_id=viewer_id,
                    owner_id=owner_id,
                    cube_id=cube_id,
                    face_name=face_name.value,
                    request_id=request_id
                )

                if policy_decision == PolicyDecision.ALLOW:
                    # Return face data
                    face_data = cube_data["faces"].get(face_name.value, {})
                    faces_response[face_name] = CubeFace(
                        face_name=face_name,
                        status=FaceStatus.VISIBLE,
                        visibility=cube_data["visibility_settings"].get(
                            face_name.value, VisibilityLevel.PUBLIC
                        ),
                        data=face_data.get("data"),
                        blockchain_tx_hash=face_data.get("blockchain_tx_hash")
                    )

                    # Log successful access to Compliance
                    await self.compliance.log_event(
                        cube_id=cube_id,
                        face_name=face_name.value,
                        action="view_face",
                        actor_id=viewer_id,
                        policy_decision="allow",
                        request_id=request_id
                    )

                    # Increment metrics
                    self.metrics.increment_counter(
                        "face_requests_total",
                        {"face": face_name.value, "status": "allow"}
                    )

                elif policy_decision == PolicyDecision.ESCALATE:
                    # Register escalation with Compliance
                    escalation = await self.compliance.escalate(
                        cube_id=cube_id,
                        face_name=face_name.value,
                        actor_id=viewer_id,
                        reason=f"Policy escalated access to {face_name.value}",
                        request_id=request_id
                    )

                    faces_response[face_name] = CubeFace(
                        face_name=face_name,
                        status=FaceStatus.ESCALATED,
                        visibility=VisibilityLevel.PRIVATE,
                        escalation_id=escalation.get("escalation_id"),
                        message="Owner approval required to view this data",
                        estimated_response_time="24 hours",
                        governance_console_url=escalation.get("governance_console_url")
                    )

                    self.metrics.increment_counter(
                        "face_requests_total",
                        {"face": face_name.value, "status": "escalate"}
                    )

                    logger.info(
                        "face_escalated",
                        cube_id=truncate_id(cube_id),
                        face=face_name.value,
                        escalation_id=escalation.get("escalation_id"),
                        request_id=request_id
                    )

                else:  # DENY
                    # Log denial to Compliance
                    await self.compliance.log_event(
                        cube_id=cube_id,
                        face_name=face_name.value,
                        action="view_face_denied",
                        actor_id=viewer_id,
                        policy_decision="deny",
                        request_id=request_id
                    )

                    self.metrics.increment_counter(
                        "face_requests_total",
                        {"face": face_name.value, "status": "deny"}
                    )

                    # Don't include denied faces in response
                    pass

            except Exception as e:
                logger.error(
                    "face_check_failed",
                    cube_id=truncate_id(cube_id),
                    face=face_name.value,
                    error=str(e),
                    request_id=request_id
                )
                # Continue with other faces
                continue

        return ProductCube(
            cube_id=cube_id,
            owner_id=owner_id,
            created_at=cube_data["created_at"],
            updated_at=cube_data["updated_at"],
            faces=faces_response
        )

    async def get_face(
        self,
        cube_id: str,
        face_name: FaceName,
        viewer_id: str,
        request_id: str
    ) -> CubeFace:
        """
        Get single face with policy check

        Raises HTTPException(403) if denied
        """
        logger.info(
            "get_face_requested",
            cube_id=truncate_id(cube_id),
            face=face_name.value,
            viewer=redact_user_id(viewer_id),
            request_id=request_id
        )

        # 1. Get cube to find owner
        cube_data = await self._fetch_cube_from_db(cube_id)
        if not cube_data:
            raise HTTPException(status_code=404, detail="Cube not found")

        owner_id = cube_data["owner_id"]

        # 2. Call Policy
        policy_decision = await self.policy.can_view_face(
            viewer_id=viewer_id,
            owner_id=owner_id,
            cube_id=cube_id,
            face_name=face_name.value,
            request_id=request_id
        )

        # 3. Handle decision
        if policy_decision == PolicyDecision.ALLOW:
            # Log access
            await self.compliance.log_event(
                cube_id=cube_id,
                face_name=face_name.value,
                action="view_face",
                actor_id=viewer_id,
                policy_decision="allow",
                request_id=request_id
            )

            # Return face
            face_data = cube_data["faces"].get(face_name.value, {})
            return CubeFace(
                face_name=face_name,
                status=FaceStatus.VISIBLE,
                visibility=cube_data["visibility_settings"].get(
                    face_name.value, VisibilityLevel.PUBLIC
                ),
                data=face_data.get("data"),
                blockchain_tx_hash=face_data.get("blockchain_tx_hash")
            )

        elif policy_decision == PolicyDecision.ESCALATE:
            # Register escalation
            escalation = await self.compliance.escalate(
                cube_id=cube_id,
                face_name=face_name.value,
                actor_id=viewer_id,
                reason=f"Policy escalated access to {face_name.value}",
                request_id=request_id
            )

            return CubeFace(
                face_name=face_name,
                status=FaceStatus.ESCALATED,
                visibility=VisibilityLevel.PRIVATE,
                escalation_id=escalation.get("escalation_id"),
                message=f"Owner approval required to view {face_name.value}",
                estimated_response_time="24 hours",
                governance_console_url=escalation.get("governance_console_url")
            )

        else:  # DENY
            # Log denial
            await self.compliance.log_event(
                cube_id=cube_id,
                face_name=face_name.value,
                action="view_face_denied",
                actor_id=viewer_id,
                policy_decision="deny",
                request_id=request_id
            )

            raise HTTPException(
                status_code=403,
                detail=f"Access denied to {face_name.value}"
            )

    async def transfer_ownership(
        self,
        cube_id: str,
        request: TransferOwnershipRequest,
        requester_id: str,
        request_id: str
    ) -> TransferResponse:
        """
        Transfer ownership with Integrity Spine enforcement

        THE INTEGRITY SPINE IN ACTION:
        1. Policy check
        2. If allow: Orchestrator executes, Compliance logs
        3. If escalate: Compliance registers, Governance notified
        4. If deny: Return 403
        """
        logger.info(
            "transfer_ownership_requested",
            cube_id=truncate_id(cube_id),
            from_owner=redact_user_id(request.from_owner_id),
            to_owner=redact_user_id(request.to_owner_id),
            request_id=request_id
        )

        # 1. Verify requester is current owner
        cube_data = await self._fetch_cube_from_db(cube_id)
        if cube_data["owner_id"] != requester_id:
            raise HTTPException(
                status_code=403,
                detail="Only owner can transfer ownership"
            )

        # 2. Call Policy
        policy_decision = await self.policy.can_transfer_ownership(
            from_owner_id=request.from_owner_id,
            to_owner_id=request.to_owner_id,
            cube_id=cube_id,
            price=request.price,
            request_id=request_id
        )

        # 3. Handle decision
        if policy_decision == PolicyDecision.ALLOW:
            # Execute transfer via Orchestrator
            transfer_result = await self.orchestrator.execute_transfer_ownership(
                cube_id=cube_id,
                from_owner_id=request.from_owner_id,
                to_owner_id=request.to_owner_id,
                transfer_method=request.transfer_method.value,
                price=request.price,
                request_id=request_id
            )

            # Update ownership face in DB
            await self._update_ownership_face(cube_id, transfer_result)

            # Log transfer to Compliance
            await self.compliance.log_event(
                cube_id=cube_id,
                face_name="ownership",
                action="transfer_ownership",
                actor_id=requester_id,
                policy_decision="allow",
                context={
                    "transfer_method": request.transfer_method.value,
                    "price": request.price,
                    "to_owner": request.to_owner_id
                },
                request_id=request_id
            )

            self.metrics.increment_counter(
                "ownership_transfers_total",
                {"status": "complete"}
            )

            return TransferResponse(
                status="transfer_complete",
                transfer_id=transfer_result.get("transfer_id"),
                blockchain_tx_hash=transfer_result.get("blockchain_tx_hash"),
                new_owner_id=request.to_owner_id,
                transfer_date=datetime.utcnow()
            )

        elif policy_decision == PolicyDecision.ESCALATE:
            # Register escalation
            escalation = await self.compliance.escalate(
                cube_id=cube_id,
                face_name="ownership",
                actor_id=requester_id,
                reason=f"Ownership transfer requires manual approval (price: {request.price})",
                request_id=request_id
            )

            self.metrics.increment_counter(
                "ownership_transfers_total",
                {"status": "escalated"}
            )

            return TransferResponse(
                status="transfer_pending_approval",
                escalation_id=escalation.get("escalation_id"),
                message="Ownership transfer requires manual approval due to high transaction value",
                estimated_approval_time="24 hours",
                governance_console_url=escalation.get("governance_console_url")
            )

        else:  # DENY
            # Log denial
            await self.compliance.log_event(
                cube_id=cube_id,
                face_name="ownership",
                action="transfer_ownership_denied",
                actor_id=requester_id,
                policy_decision="deny",
                request_id=request_id
            )

            self.metrics.increment_counter(
                "ownership_transfers_total",
                {"status": "denied"}
            )

            raise HTTPException(
                status_code=403,
                detail="Ownership transfer not allowed"
            )

    # Helper methods

    async def _fetch_cube_from_db(self, cube_id: str) -> Optional[Dict[str, Any]]:
        """Fetch cube from Spanner database (v9: includes molecular_data)"""
        from google.cloud.spanner_v1 import param_types
        import json

        def _fetch(transaction):
            results = transaction.execute_sql(
                """
                SELECT asset_id, owner_id, created_at, updated_at,
                       display_name, asset_type, lifecycle_state,
                       public_esg_score, reprint_generation, parent_asset_id
                FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )

            if not row:
                return None

            return {
                "cube_id": str(row["cube_id"]),
                "owner_id": str(row["owner_id"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "faces": {
                    "product_details": row["product_details"] or {},
                    "provenance": row["provenance"] or {},
                    "ownership": row["ownership"] or {},
                    "social_layer": row["social_layer"] or {},
                    "esg_impact": row["esg_impact"] or {},
                    "lifecycle": row["lifecycle"] or {}
                },
                "visibility_settings": row["visibility_settings"] or {}
            }
        """Fetch cube from Spanner database (v9: includes molecular_data)"""
        from google.cloud.spanner_v1 import param_types
        import json

        def _fetch(transaction):
            results = transaction.execute_sql(
                """
                SELECT asset_id, owner_id, created_at, updated_at,
                       display_name, asset_type, lifecycle_state,
                       public_esg_score, reprint_generation, parent_asset_id
                FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )
            for row in results:
                return row
            return None

        row = self.spanner_pool.database.run_in_transaction(_fetch)

        if not row:
            return None

        # v9: Build face data from Spanner columns
        return {
            "cube_id": row[0],
            "owner_id": row[1],
            "created_at": row[2],
            "updated_at": row[3],
            "lifecycle_state": row[6] or "PRODUCED",
            "reprint_generation": row[8] or 0,
            "parent_asset_id": row[9],
            "faces": {
                "product_details": {"display_name": row[4], "asset_type": row[5]},
                "provenance": {},
                "ownership": {"owner_id": row[1]},
                "social_layer": {},
                "esg_impact": {"public_esg_score": row[7]},
                "lifecycle": {"state": row[6] or "PRODUCED"},
                "molecular_data": {
                    "lifecycle_state": row[6] or "PRODUCED",
                    "reprint_generation": row[8] or 0,
                    "parent_asset_id": row[9]
                }
            },
            "visibility_settings": {}
        }

    async def _update_ownership_face(
        self,
        cube_id: str,
        transfer_data: Dict[str, Any]
    ):
        """Update ownership in Spanner after transfer"""
        from google.cloud import spanner

        def _update(transaction):
            # Mark previous ownership as ended
            transaction.update(
                table="Owns",
                columns=["owner_id", "asset_id", "is_current", "ended_at"],
                values=[
                    (transfer_data.get("from_owner_id"), cube_id, False, spanner.COMMIT_TIMESTAMP),
                ]
            )
            # Create new ownership record
            transaction.insert(
                table="Owns",
                columns=["owner_id", "asset_id", "acquired_at", "transfer_method", "is_current"],
                values=[
                    (transfer_data.get("new_owner_id"), cube_id, spanner.COMMIT_TIMESTAMP, transfer_data.get("transfer_method", "transfer"), True)
                ]
            )

        self.spanner_pool.database.run_in_transaction(_update)

    # ===========================================
    # v9: LIFECYCLE & CIRCULAR ECONOMY METHODS
    # ===========================================

    async def transition_lifecycle(
        self,
        cube_id: str,
        new_state: LifecycleState,
        triggered_by: str,
        notes: Optional[str],
        esg_verification_required: bool,
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Transition cube lifecycle state.

        Validates transition against state machine and records event.
        """
        # Fetch current state
        cube_data = await self._fetch_cube_from_db(cube_id)
        if not cube_data:
            raise ValueError(f"Cube {cube_id} not found")

        current_state_str = cube_data.get("lifecycle_state", "PRODUCED")
        try:
            current_state = LifecycleState(current_state_str)
        except ValueError:
            current_state = LifecycleState.PRODUCED

        # Validate transition
        valid_next_states = VALID_TRANSITIONS.get(current_state, [])
        if new_state not in valid_next_states:
            raise ValueError(
                f"Invalid transition from {current_state.value} to {new_state.value}. "
                f"Valid transitions: {[s.value for s in valid_next_states]}"
            )

        # ESG verification for DISSOLVE transitions
        if new_state == LifecycleState.DISSOLVE and esg_verification_required:
            esg_result = await self.compliance.verify_esg(
                asset_id=cube_id,
                transaction_type="dissolve",
                request_id=request_id
            )
            if not esg_result.get("approved", False):
                return {
                    "status": "escalated",
                    "cube_id": cube_id,
                    "previous_state": current_state.value,
                    "new_state": new_state.value,
                    "esg_verified": False,
                    "message": esg_result.get("reason", "ESG verification failed"),
                    "escalation_id": esg_result.get("escalation_id")
                }

        # Update state in Spanner
        await self._update_lifecycle_state(cube_id, new_state, triggered_by, notes)

        # Log to compliance
        await self.compliance.log_event(
            cube_id=cube_id,
            face_name="molecular_data",
            action="lifecycle_transition",
            actor_id=triggered_by,
            policy_decision="allow",
            context={
                "from_state": current_state.value,
                "to_state": new_state.value,
                "notes": notes
            },
            request_id=request_id
        )

        self.metrics.increment_counter(
            "lifecycle_transitions_total",
            {"from_state": current_state.value, "to_state": new_state.value}
        )

        logger.info({
            "event": "lifecycle_transition_complete",
            "cube_id": cube_id[:8] + "...",
            "from_state": current_state.value,
            "to_state": new_state.value,
            "triggered_by": triggered_by[:8] + "...",
            "request_id": request_id
        })

        return {
            "status": "success",
            "cube_id": cube_id,
            "previous_state": current_state.value,
            "new_state": new_state.value,
            "transition_timestamp": datetime.utcnow().isoformat(),
            "esg_verified": esg_verification_required
        }

    async def _update_lifecycle_state(
        self,
        cube_id: str,
        new_state: LifecycleState,
        triggered_by: str,
        notes: Optional[str]
    ):
        """Update lifecycle state in Spanner"""
        from google.cloud import spanner

        def _update(transaction):
            # Update Assets table
            transaction.update(
                table="Assets",
                columns=["asset_id", "lifecycle_state", "updated_at"],
                values=[(cube_id, new_state.value, spanner.COMMIT_TIMESTAMP)]
            )

            # Insert lifecycle event
            event_id = str(uuid4())
            transaction.insert(
                table="LifecycleEvents",
                columns=[
                    "event_id", "asset_id", "from_state", "to_state",
                    "triggered_by", "notes", "event_timestamp"
                ],
                values=[(
                    event_id, cube_id, None, new_state.value,
                    triggered_by, notes, spanner.COMMIT_TIMESTAMP
                )]
            )

        self.spanner_pool.database.run_in_transaction(_update)

    async def authorize_dissolve(
        self,
        cube_id: str,
        owner_id: str,
        reason: str,
        target_materials: Optional[List[str]],
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Authorize dissolve for circular economy.

        Generates an auth key that the owner must use to confirm dissolve.
        """
        # Verify ownership
        cube_data = await self._fetch_cube_from_db(cube_id)
        if not cube_data:
            raise ValueError(f"Cube {cube_id} not found")

        if cube_data["owner_id"] != owner_id:
            raise ValueError("Only owner can authorize dissolve")

        # Check lifecycle state (must be ACTIVE or REPAIR)
        current_state = cube_data.get("lifecycle_state", "PRODUCED")
        if current_state not in ["ACTIVE", "REPAIR"]:
            raise ValueError(f"Cannot authorize dissolve from state {current_state}")

        # Generate auth key
        auth_key = secrets.token_hex(32)
        auth_key_hash = hashlib.sha256(auth_key.encode()).hexdigest()

        # Store auth key hash in Spanner
        await self._store_dissolve_auth(cube_id, auth_key_hash)

        # Get recoverable materials
        materials = await self._get_cube_materials(cube_id)

        # Log to compliance
        await self.compliance.log_event(
            cube_id=cube_id,
            face_name="molecular_data",
            action="dissolve_authorized",
            actor_id=owner_id,
            policy_decision="allow",
            context={"reason": reason, "target_materials": target_materials},
            request_id=request_id
        )

        logger.info({
            "event": "dissolve_authorized",
            "cube_id": cube_id[:8] + "...",
            "owner_id": owner_id[:8] + "...",
            "request_id": request_id
        })

        return {
            "status": "authorized",
            "cube_id": cube_id,
            "auth_key": auth_key,  # Return plaintext to owner (only time)
            "auth_key_hash": auth_key_hash,
            "recoverable_materials": materials,
            "estimated_value_usd": sum(m.get("estimated_value", 0) for m in materials)
        }

    async def _store_dissolve_auth(self, cube_id: str, auth_key_hash: str):
        """Store dissolve authorization in Spanner"""
        from google.cloud import spanner

        def _store(transaction):
            transaction.update(
                table="Assets",
                columns=["asset_id", "dissolve_auth_key_hash", "updated_at"],
                values=[(cube_id, auth_key_hash, spanner.COMMIT_TIMESTAMP)]
            )

        self.spanner_pool.database.run_in_transaction(_store)

    async def _get_cube_materials(self, cube_id: str) -> List[Dict[str, Any]]:
        """Get materials for a cube from Spanner"""
        from google.cloud.spanner_v1 import param_types

        def _fetch(transaction):
            results = transaction.execute_sql(
                """
                SELECT m.material_id, m.material_type, m.esg_score,
                       c.weight_pct
                FROM ComposedOf c
                JOIN Materials m ON c.material_id = m.material_id
                WHERE c.asset_id = @asset_id
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )
            materials = []
            for row in results:
                materials.append({
                    "material_id": row[0],
                    "material_type": row[1],
                    "esg_score": row[2],
                    "weight_pct": row[3],
                    "estimated_value": 10.0  # Placeholder
                })
            return materials

        return self.spanner_pool.database.run_in_transaction(_fetch)

    async def update_biometric_sync(
        self,
        cube_id: str,
        device_id: str,
        sync_timestamp: datetime,
        latency_ms: float,
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Update biometric sync for AR glasses.

        Tracks sync latency for Active Facet performance monitoring.
        """
        from google.cloud import spanner

        def _update(transaction):
            transaction.update(
                table="Assets",
                columns=[
                    "asset_id", "last_biometric_sync",
                    "ar_sync_latency_ms", "updated_at"
                ],
                values=[(cube_id, sync_timestamp, latency_ms, spanner.COMMIT_TIMESTAMP)]
            )

        self.spanner_pool.database.run_in_transaction(_update)

        logger.info({
            "event": "biometric_sync_updated",
            "cube_id": cube_id[:8] + "...",
            "device_id": device_id[:8] + "...",
            "latency_ms": latency_ms,
            "request_id": request_id
        })

        return {
            "status": "synced",
            "cube_id": cube_id,
            "device_id": device_id,
            "sync_timestamp": sync_timestamp.isoformat(),
            "latency_ms": latency_ms
        }

    async def get_reprint_lineage(
        self,
        cube_id: str,
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Get reprint lineage for a cube.

        Traces ancestry through DerivedFrom edges.
        """
        from google.cloud.spanner_v1 import param_types

        def _fetch_lineage(transaction):
            # Get current cube info
            current = transaction.execute_sql(
                """
                SELECT asset_id, display_name, lifecycle_state,
                       reprint_generation, created_at
                FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )
        """Update ownership in Spanner after transfer"""
        from google.cloud import spanner

        def _update(transaction):
            # Mark previous ownership as ended
            transaction.update(
                table="Owns",
                columns=["owner_id", "asset_id", "is_current", "ended_at"],
                values=[
                    (transfer_data.get("from_owner_id"), cube_id, False, spanner.COMMIT_TIMESTAMP),
                ]
            )
            # Create new ownership record
            transaction.insert(
                table="Owns",
                columns=["owner_id", "asset_id", "acquired_at", "transfer_method", "is_current"],
                values=[
                    (transfer_data.get("new_owner_id"), cube_id, spanner.COMMIT_TIMESTAMP, transfer_data.get("transfer_method", "transfer"), True)
            transaction.update(
                table="Owns",
                columns=["owner_id", "asset_id", "is_active"],
                values=[
                    (transfer_data.get("from_owner_id"), cube_id, False),
                ]
            )
            transaction.insert(
                table="Owns",
                columns=["owner_id", "asset_id", "acquired_at", "share_pct", "is_active"],
                values=[
                    (transfer_data.get("new_owner_id"), cube_id, spanner.COMMIT_TIMESTAMP, 100.0, True)
                ]
            )

        self.spanner_pool.database.run_in_transaction(_update)

    # ===========================================
    # v9: LIFECYCLE & CIRCULAR ECONOMY METHODS
    # ===========================================

    async def transition_lifecycle(
        self,
        cube_id: str,
        new_state: LifecycleState,
        triggered_by: str,
        notes: Optional[str],
        esg_verification_required: bool,
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Transition cube lifecycle state.

        Validates transition against state machine and records event.
        """
        # Fetch current state
        cube_data = await self._fetch_cube_from_db(cube_id)
        if not cube_data:
            raise ValueError(f"Cube {cube_id} not found")

        current_state_str = cube_data.get("lifecycle_state", "PRODUCED")
        try:
            current_state = LifecycleState(current_state_str)
        except ValueError:
            current_state = LifecycleState.PRODUCED

        # Validate transition
        valid_next_states = VALID_TRANSITIONS.get(current_state, [])
        if new_state not in valid_next_states:
            raise ValueError(
                f"Invalid transition from {current_state.value} to {new_state.value}. "
                f"Valid transitions: {[s.value for s in valid_next_states]}"
            )

        # ESG verification for DISSOLVE transitions
        if new_state == LifecycleState.DISSOLVE and esg_verification_required:
            esg_result = await self.compliance.verify_esg(
                asset_id=cube_id,
                transaction_type="dissolve",
                request_id=request_id
            )
            if not esg_result.get("approved", False):
                return {
                    "status": "escalated",
                    "cube_id": cube_id,
                    "previous_state": current_state.value,
                    "new_state": new_state.value,
                    "esg_verified": False,
                    "message": esg_result.get("reason", "ESG verification failed"),
                    "escalation_id": esg_result.get("escalation_id")
                }

        # Update state in Spanner
        await self._update_lifecycle_state(cube_id, new_state, triggered_by, notes)

        # Log to compliance
        await self.compliance.log_event(
            cube_id=cube_id,
            face_name="molecular_data",
            action="lifecycle_transition",
            actor_id=triggered_by,
            policy_decision="allow",
            context={
                "from_state": current_state.value,
                "to_state": new_state.value,
                "notes": notes
            },
            request_id=request_id
        )

        self.metrics.increment_counter(
            "lifecycle_transitions_total",
            {"from_state": current_state.value, "to_state": new_state.value}
        )

        logger.info({
            "event": "lifecycle_transition_complete",
            "cube_id": cube_id[:8] + "...",
            "from_state": current_state.value,
            "to_state": new_state.value,
            "triggered_by": triggered_by[:8] + "...",
            "request_id": request_id
        })

        return {
            "status": "success",
            "cube_id": cube_id,
            "previous_state": current_state.value,
            "new_state": new_state.value,
            "transition_timestamp": datetime.utcnow().isoformat(),
            "esg_verified": esg_verification_required
        }

    async def _update_lifecycle_state(
        self,
        cube_id: str,
        new_state: LifecycleState,
        triggered_by: str,
        notes: Optional[str]
    ):
        """Update lifecycle state in Spanner"""
        from google.cloud import spanner

        def _update(transaction):
            # Update Assets table
            transaction.update(
                table="Assets",
                columns=["asset_id", "lifecycle_state", "updated_at"],
                values=[(cube_id, new_state.value, spanner.COMMIT_TIMESTAMP)]
            )

            # Insert lifecycle event
            event_id = str(uuid4())
            transaction.insert(
                table="LifecycleEvents",
                columns=[
                    "event_id", "asset_id", "from_state", "to_state",
                    "triggered_by", "notes", "event_timestamp"
                ],
                values=[(
                    event_id, cube_id, None, new_state.value,
                    triggered_by, notes, spanner.COMMIT_TIMESTAMP
                )]
            )

        self.spanner_pool.database.run_in_transaction(_update)

    async def authorize_dissolve(
        self,
        cube_id: str,
        owner_id: str,
        reason: str,
        target_materials: Optional[List[str]],
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Authorize dissolve for circular economy.

        Generates an auth key that the owner must use to confirm dissolve.
        """
        # Verify ownership
        cube_data = await self._fetch_cube_from_db(cube_id)
        if not cube_data:
            raise ValueError(f"Cube {cube_id} not found")

        if cube_data["owner_id"] != owner_id:
            raise ValueError("Only owner can authorize dissolve")

        # Check lifecycle state (must be ACTIVE or REPAIR)
        current_state = cube_data.get("lifecycle_state", "PRODUCED")
        if current_state not in ["ACTIVE", "REPAIR"]:
            raise ValueError(f"Cannot authorize dissolve from state {current_state}")

        # Generate auth key
        auth_key = secrets.token_hex(32)
        auth_key_hash = hashlib.sha256(auth_key.encode()).hexdigest()

        # Store auth key hash in Spanner
        await self._store_dissolve_auth(cube_id, auth_key_hash)

        # Get recoverable materials
        materials = await self._get_cube_materials(cube_id)

        # Log to compliance
        await self.compliance.log_event(
            cube_id=cube_id,
            face_name="molecular_data",
            action="dissolve_authorized",
            actor_id=owner_id,
            policy_decision="allow",
            context={"reason": reason, "target_materials": target_materials},
            request_id=request_id
        )

        logger.info({
            "event": "dissolve_authorized",
            "cube_id": cube_id[:8] + "...",
            "owner_id": owner_id[:8] + "...",
            "request_id": request_id
        })

        return {
            "status": "authorized",
            "cube_id": cube_id,
            "auth_key": auth_key,  # Return plaintext to owner (only time)
            "auth_key_hash": auth_key_hash,
            "recoverable_materials": materials,
            "estimated_value_usd": sum(m.get("estimated_value", 0) for m in materials)
        }

    async def _store_dissolve_auth(self, cube_id: str, auth_key_hash: str):
        """Store dissolve authorization in Spanner"""
        from google.cloud import spanner

        def _store(transaction):
            transaction.update(
                table="Assets",
                columns=["asset_id", "dissolve_auth_key_hash", "updated_at"],
                values=[(cube_id, auth_key_hash, spanner.COMMIT_TIMESTAMP)]
            )

        self.spanner_pool.database.run_in_transaction(_store)

    async def _get_cube_materials(self, cube_id: str) -> List[Dict[str, Any]]:
        """Get materials for a cube from Spanner"""
        from google.cloud.spanner_v1 import param_types

        def _fetch(transaction):
            results = transaction.execute_sql(
                """
                SELECT m.material_id, m.material_type, m.esg_score,
                       c.weight_pct
                FROM ComposedOf c
                JOIN Materials m ON c.material_id = m.material_id
                WHERE c.asset_id = @asset_id
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )
            materials = []
            for row in results:
                materials.append({
                    "material_id": row[0],
                    "material_type": row[1],
                    "esg_score": row[2],
                    "weight_pct": row[3],
                    "estimated_value": 10.0  # Placeholder
                })
            return materials

        return self.spanner_pool.database.run_in_transaction(_fetch)

    async def update_biometric_sync(
        self,
        cube_id: str,
        device_id: str,
        sync_timestamp: datetime,
        latency_ms: float,
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Update biometric sync for AR glasses.

        Tracks sync latency for Active Facet performance monitoring.
        """
        from google.cloud import spanner

        def _update(transaction):
            transaction.update(
                table="Assets",
                columns=[
                    "asset_id", "last_biometric_sync",
                    "ar_sync_latency_ms", "updated_at"
                ],
                values=[(cube_id, sync_timestamp, latency_ms, spanner.COMMIT_TIMESTAMP)]
            )

        self.spanner_pool.database.run_in_transaction(_update)

        logger.info({
            "event": "biometric_sync_updated",
            "cube_id": cube_id[:8] + "...",
            "device_id": device_id[:8] + "...",
            "latency_ms": latency_ms,
            "request_id": request_id
        })

        return {
            "status": "synced",
            "cube_id": cube_id,
            "device_id": device_id,
            "sync_timestamp": sync_timestamp.isoformat(),
            "latency_ms": latency_ms
        }

    async def get_reprint_lineage(
        self,
        cube_id: str,
        request_id: str
    ) -> Dict[str, Any]:
        """
        v9: Get reprint lineage for a cube.

        Traces ancestry through DerivedFrom edges.
        """
        from google.cloud.spanner_v1 import param_types

        def _fetch_lineage(transaction):
            # Get current cube info
            current = transaction.execute_sql(
                """
                SELECT asset_id, display_name, lifecycle_state,
                       reprint_generation, created_at
                FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )
            current_data = None
            for row in current:
                current_data = {
                    "asset_id": row[0],
                    "display_name": row[1],
                    "lifecycle_state": row[2],
                    "reprint_generation": row[3],
                    "created_at": row[4].isoformat() if row[4] else None
                }

            if not current_data:
                return None

            # Get ancestors via DerivedFrom
            ancestors = transaction.execute_sql(
                """
                SELECT d.parent_asset_id, d.burn_proof_tx_hash, d.derived_at,
                       a.display_name, a.lifecycle_state, a.reprint_generation
                FROM DerivedFrom d
                JOIN Assets a ON d.parent_asset_id = a.asset_id
                WHERE d.child_asset_id = @asset_id
                ORDER BY d.derived_at DESC
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )

            ancestor_list = []
            for row in ancestors:
                ancestor_list.append({
                    "parent_asset_id": row[0],
                    "burn_proof_tx_hash": row[1],
                    "derived_at": row[2].isoformat() if row[2] else None,
                    "display_name": row[3],
                    "lifecycle_state": row[4],
                    "reprint_generation": row[5]
                })

            return {
                "current": current_data,
                "ancestors": ancestor_list
            }

        lineage = self.spanner_pool.database.run_in_transaction(_fetch_lineage)

        if not lineage:
            raise ValueError(f"Cube {cube_id} not found")

        logger.info({
            "event": "lineage_fetched",
            "cube_id": cube_id[:8] + "...",
            "ancestor_count": len(lineage.get("ancestors", [])),
            "request_id": request_id
        })

        return {
            "cube_id": cube_id,
            "lineage": lineage,
            "is_reprinted": len(lineage.get("ancestors", [])) > 0,
            "generation": lineage["current"].get("reprint_generation", 0)
        }
