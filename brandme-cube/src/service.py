"""
Cube Service - Business Logic

CRITICAL INTEGRITY SPINE PATTERN:
1. NEVER return face data without calling Policy first
2. If Policy returns "allow" → return face data
3. If Policy returns "escalate" → call Compliance, return escalation response
4. If Policy returns "deny" → return 403
5. Log EVERY action to Compliance service
"""

from typing import Optional, Dict, Any
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
    TransferResponse
)
from .clients import (
    PolicyClient,
    ComplianceClient,
    OrchestratorClient,
    IdentityClient
)

logger = get_logger("cube.service")

class CubeService:
    """Product Cube business logic with Integrity Spine enforcement"""

    def __init__(
        self,
        db_pool,
        policy_client: PolicyClient,
        compliance_client: ComplianceClient,
        orchestrator_client: OrchestratorClient,
        identity_client: IdentityClient,
        metrics: MetricsCollector
    ):
        self.db = db_pool
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
        """Fetch cube from database"""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT cube_id, owner_id, created_at, updated_at,
                       product_details, provenance, ownership,
                       social_layer, esg_impact, lifecycle,
                       visibility_settings
                FROM cubes
                WHERE cube_id = $1
                """,
                cube_id
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

    async def _update_ownership_face(
        self,
        cube_id: str,
        transfer_data: Dict[str, Any]
    ):
        """Update ownership face after transfer"""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE cubes
                SET ownership = $1,
                    owner_id = $2,
                    updated_at = $3
                WHERE cube_id = $4
                """,
                transfer_data.get("ownership_face"),
                transfer_data.get("new_owner_id"),
                datetime.utcnow(),
                cube_id
            )
