# Brand.Me v8 — Global Integrity Spine with Spanner + Firestore
# Policy Service: Consent graph enforcement via Spanner
# brandme-core/policy/main.py

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id
from brandme_core.metrics import get_metrics_collector, generate_metrics
from brandme_core.spanner.pool import create_pool_manager, SpannerPoolManager
from brandme_core.spanner.consent_graph import ConsentGraphClient
from brandme_core.spanner.provenance import ProvenanceClient

logger = get_logger("policy_service")
metrics = get_metrics_collector("policy")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
BLOCKED_REGIONS = {"BLOCKED_REGION", "SANCTIONED_REGION"}


class PolicyCheckRequest(BaseModel):
    scanner_user_id: str
    garment_id: str
    region_code: str
    action: str


class FaceCheckRequest(BaseModel):
    viewer_id: str
    owner_id: str
    cube_id: str
    face_name: str


class TransferCheckRequest(BaseModel):
    from_owner_id: str
    to_owner_id: str
    cube_id: str
    price: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Spanner pool manager
    pool_manager = create_pool_manager()
    await pool_manager.initialize()
    app.state.spanner_pool = pool_manager

    # Initialize consent graph client
    app.state.consent_graph = ConsentGraphClient(pool_manager)

    # Initialize provenance client
    app.state.provenance = ProvenanceClient(pool_manager)

    logger.info({
        "event": "policy_service_started",
        "database": "spanner",
        "project": os.getenv('SPANNER_PROJECT_ID', 'brandme-project')
    })

    yield

    await pool_manager.close()
    logger.info({"event": "policy_service_stopped"})


app = FastAPI(lifespan=lifespan)

# CORS configuration
from brandme_core.cors_config import get_cors_config
cors_config = get_cors_config()
app.add_middleware(CORSMiddleware, **cors_config)


@app.post("/policy/check")
async def policy_check(payload: PolicyCheckRequest, request: Request):
    """
    Check policy: consent graph + region rules -> decision + resolved_scope + policy_version.

    Uses Spanner consent graph for O(1) consent lookups.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_graph: ConsentGraphClient = app.state.consent_graph
    provenance: ProvenanceClient = app.state.provenance

    # Check region first (fast fail)
    if payload.region_code in BLOCKED_REGIONS:
        logger.info({
            "event": "policy_decision_blocked_region",
            "region": payload.region_code,
            "request_id": request_id
        })

        metrics.increment_counter("policy_decisions", {"decision": "deny", "reason": "blocked_region"})

        return JSONResponse(content={
            "decision": "deny",
            "resolved_scope": "blocked",
            "policy_version": f"policy_v1_{payload.region_code}",
            "reason": "region_blocked"
        })

    try:
        # Get current owner from provenance
        ownership = await provenance.get_current_owner(payload.garment_id)

        if not ownership:
            # Asset not found - allow public access only
            logger.warning({
                "event": "asset_not_found",
                "garment_id": truncate_id(payload.garment_id),
                "request_id": request_id
            })

            return JSONResponse(content={
                "decision": "allow",
                "resolved_scope": "public",
                "policy_version": f"policy_v1_{payload.region_code}",
                "reason": "asset_not_found_public_only"
            })

        owner_id = ownership.owner_id

        # Check consent using Spanner graph
        consent_decision = await consent_graph.check_consent(
            viewer_id=payload.scanner_user_id,
            owner_id=owner_id,
            asset_id=payload.garment_id
        )

        # Determine decision
        if consent_decision.allowed:
            decision = "allow"
        elif consent_decision.visibility == "private":
            # Private data, not owner - escalate
            decision = "escalate"
        else:
            # Not allowed by consent settings
            decision = "escalate"

        resolved_scope = consent_decision.visibility
        policy_version = f"policy_v1_{payload.region_code}_{consent_decision.policy_version or 'default'}"

        resp_body = {
            "decision": decision,
            "resolved_scope": resolved_scope,
            "policy_version": policy_version,
            "consent_scope": consent_decision.scope,
            "reason": consent_decision.reason
        }

        metrics.increment_counter("policy_decisions", {
            "decision": decision,
            "scope": resolved_scope
        })

        logger.info({
            "event": "policy_decision",
            "scanner_user": redact_user_id(payload.scanner_user_id),
            "garment_owner": redact_user_id(owner_id),
            "garment_partial": truncate_id(payload.garment_id),
            "region_code": payload.region_code,
            "decision": decision,
            "resolved_scope": resolved_scope,
            "request_id": request_id,
        })

        return JSONResponse(content=resp_body)

    except Exception as e:
        logger.error({
            "event": "policy_check_failed",
            "error": str(e),
            "request_id": request_id
        })

        # Fail safe - escalate on error
        metrics.increment_counter("policy_decisions", {"decision": "escalate", "reason": "error"})

        return JSONResponse(content={
            "decision": "escalate",
            "resolved_scope": "unknown",
            "policy_version": f"policy_v1_{payload.region_code}",
            "reason": "policy_check_error"
        })


@app.post("/policy/canViewFace")
async def can_view_face(payload: FaceCheckRequest, request: Request):
    """
    Check if viewer can access a specific cube face.

    Uses Spanner consent graph for O(1) lookups with face-level granularity.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_graph: ConsentGraphClient = app.state.consent_graph

    viewer_id = payload.viewer_id
    owner_id = payload.owner_id
    cube_id = payload.cube_id
    face_name = payload.face_name

    # Same owner always gets full access
    if viewer_id == owner_id:
        metrics.increment_counter("face_policy_decisions", {
            "decision": "allow",
            "face": face_name,
            "reason": "owner"
        })

        return JSONResponse(content={
            "decision": "allow",
            "resolved_scope": "private",
            "reason": "viewer_is_owner"
        })

    try:
        # Check consent via Spanner graph
        consent_decision = await consent_graph.check_consent(
            viewer_id=viewer_id,
            owner_id=owner_id,
            asset_id=cube_id,
            facet_type=face_name
        )

        # Face-specific rules
        public_faces = {"product_details", "provenance", "social_layer", "esg_impact"}
        private_faces = {"ownership"}
        authenticated_faces = {"lifecycle"}

        if face_name in public_faces:
            # Public faces always allowed
            decision = "allow"
            resolved_scope = "public"
            reason = "public_face"

        elif face_name in private_faces:
            # Private faces require owner consent or friendship
            if consent_decision.allowed and consent_decision.visibility in ("friends_only", "custom"):
                decision = "allow"
                resolved_scope = consent_decision.visibility
                reason = "consent_granted"
            else:
                decision = "escalate"
                resolved_scope = "private"
                reason = "private_face_escalate"

        elif face_name in authenticated_faces:
            # Authenticated faces require authentication
            if viewer_id == "anonymous":
                decision = "deny"
                resolved_scope = "public"
                reason = "anonymous_denied"
            elif consent_decision.allowed:
                decision = "allow"
                resolved_scope = consent_decision.visibility
                reason = "authenticated_access"
            else:
                decision = "escalate"
                resolved_scope = "authenticated"
                reason = "authenticated_escalate"

        else:
            # Unknown face - escalate for safety
            decision = "escalate"
            resolved_scope = "unknown"
            reason = "unknown_face"

        metrics.increment_counter("face_policy_decisions", {
            "decision": decision,
            "face": face_name,
            "reason": reason
        })

        logger.info({
            "event": "face_policy_decision",
            "viewer": redact_user_id(viewer_id),
            "owner": redact_user_id(owner_id),
            "cube_partial": truncate_id(cube_id),
            "face": face_name,
            "decision": decision,
            "resolved_scope": resolved_scope,
            "reason": reason,
            "request_id": request_id,
        })

        return JSONResponse(content={
            "decision": decision,
            "resolved_scope": resolved_scope,
            "reason": reason
        })

    except Exception as e:
        logger.error({
            "event": "face_policy_check_failed",
            "error": str(e),
            "request_id": request_id
        })

        # Fail safe - escalate on error
        metrics.increment_counter("face_policy_decisions", {
            "decision": "escalate",
            "face": face_name,
            "reason": "error"
        })

        return JSONResponse(content={
            "decision": "escalate",
            "resolved_scope": "unknown",
            "reason": "policy_check_error"
        })


@app.post("/policy/canTransferOwnership")
async def can_transfer_ownership(payload: TransferCheckRequest, request: Request):
    """
    Check if ownership transfer is allowed.

    Validates:
    - High-value transfers require human approval
    - Sender must be current owner
    - Receiver must be valid user
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    provenance: ProvenanceClient = app.state.provenance
    pool: SpannerPoolManager = app.state.spanner_pool

    from_owner_id = payload.from_owner_id
    to_owner_id = payload.to_owner_id
    cube_id = payload.cube_id
    price = payload.price

    try:
        # Verify current ownership
        ownership = await provenance.get_current_owner(cube_id)

        if not ownership:
            logger.warning({
                "event": "transfer_asset_not_found",
                "cube_id": truncate_id(cube_id),
                "request_id": request_id
            })

            metrics.increment_counter("transfer_policy_decisions", {
                "decision": "deny",
                "reason": "asset_not_found"
            })

            return JSONResponse(content={
                "decision": "deny",
                "reason": "asset_not_found"
            })

        if ownership.owner_id != from_owner_id:
            logger.warning({
                "event": "transfer_not_owner",
                "claimed_owner": redact_user_id(from_owner_id),
                "actual_owner": redact_user_id(ownership.owner_id),
                "request_id": request_id
            })

            metrics.increment_counter("transfer_policy_decisions", {
                "decision": "deny",
                "reason": "not_owner"
            })

            return JSONResponse(content={
                "decision": "deny",
                "reason": "sender_not_owner"
            })

        # Verify receiver exists
        from google.cloud.spanner_v1 import param_types

        async with pool.session() as snapshot:
            result = snapshot.execute_sql(
                "SELECT user_id FROM Users WHERE user_id = @user_id",
                params={'user_id': to_owner_id},
                param_types={'user_id': param_types.STRING}
            )
            receiver_exists = len(list(result)) > 0

        if not receiver_exists:
            metrics.increment_counter("transfer_policy_decisions", {
                "decision": "deny",
                "reason": "invalid_receiver"
            })

            return JSONResponse(content={
                "decision": "deny",
                "reason": "receiver_not_found"
            })

        # High-value transfers require human approval
        HIGH_VALUE_THRESHOLD = 10000.0

        if price and price > HIGH_VALUE_THRESHOLD:
            decision = "escalate"
            reason = "high_value_transaction"
        else:
            decision = "allow"
            reason = "standard_transfer"

        metrics.increment_counter("transfer_policy_decisions", {
            "decision": decision,
            "reason": reason
        })

        logger.info({
            "event": "ownership_transfer_policy",
            "from_owner": redact_user_id(from_owner_id),
            "to_owner": redact_user_id(to_owner_id),
            "cube_partial": truncate_id(cube_id),
            "price": price,
            "decision": decision,
            "reason": reason,
            "request_id": request_id,
        })

        return JSONResponse(content={
            "decision": decision,
            "reason": reason
        })

    except Exception as e:
        logger.error({
            "event": "transfer_policy_check_failed",
            "error": str(e),
            "request_id": request_id
        })

        metrics.increment_counter("transfer_policy_decisions", {
            "decision": "escalate",
            "reason": "error"
        })

        return JSONResponse(content={
            "decision": "escalate",
            "reason": "policy_check_error"
        })


@app.get("/policy/provenance/{asset_id}")
async def get_provenance(asset_id: str, request: Request):
    """
    Get full provenance chain for an asset.

    O(n) where n = number of transfers.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    provenance: ProvenanceClient = app.state.provenance

    try:
        prov = await provenance.get_full_provenance(asset_id)

        if not prov:
            return JSONResponse(
                content={"error": "asset_not_found"},
                status_code=404
            )

        # Convert to JSON-serializable format
        chain = []
        for entry in prov.chain:
            chain.append({
                "sequence": entry.sequence_num,
                "from_user_id": entry.from_user_id,
                "to_user_id": entry.to_user_id,
                "transfer_type": entry.transfer_type,
                "price": entry.price,
                "currency": entry.currency,
                "blockchain_tx_hash": entry.blockchain_tx_hash,
                "transfer_at": entry.transfer_at.isoformat() if entry.transfer_at else None
            })

        return JSONResponse(content={
            "asset_id": prov.asset_id,
            "creator_id": prov.creator_id,
            "creator_name": prov.creator_name,
            "current_owner_id": prov.current_owner_id,
            "current_owner_name": prov.current_owner_name,
            "created_at": prov.created_at.isoformat() if prov.created_at else None,
            "transfer_count": prov.transfer_count,
            "chain": chain
        })

    except Exception as e:
        logger.error({
            "event": "get_provenance_failed",
            "asset_id": truncate_id(asset_id),
            "error": str(e),
            "request_id": request_id
        })
        return JSONResponse(
            content={"error": "failed_to_retrieve_provenance"},
            status_code=500
        )


@app.get("/policy/provenance/{asset_id}/verify")
async def verify_provenance(asset_id: str, request: Request):
    """
    Verify the integrity of an asset's provenance chain.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    provenance: ProvenanceClient = app.state.provenance

    try:
        result = await provenance.verify_provenance_chain(asset_id)
        return JSONResponse(content=result)

    except Exception as e:
        logger.error({
            "event": "verify_provenance_failed",
            "asset_id": truncate_id(asset_id),
            "error": str(e),
            "request_id": request_id
        })
        return JSONResponse(
            content={"error": "verification_failed"},
            status_code=500
        )


@app.post("/policy/canViewFace")
async def can_view_face(payload: dict, request: Request):
    """
    Check if viewer can access a specific cube face.
    Used by cube-service for per-face policy decisions.

    Payload:
        viewer_id: str - User requesting access
        owner_id: str - Cube owner
        cube_id: str - Cube identifier
        face_name: str - Face being requested

    Returns:
        {"decision": "allow" | "escalate" | "deny"}
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    viewer_id = payload.get("viewer_id")
    owner_id = payload.get("owner_id")
    cube_id = payload.get("cube_id")
    face_name = payload.get("face_name")

    # Same owner always gets full access
    if viewer_id == owner_id:
        decision = "allow"
        resolved_scope = "private"
    else:
        # Fetch owner consent settings
        consent = await fetch_owner_and_consent(
            viewer_id,
            cube_id,
            request_id,
            app.state.http_client
        )

        trust_score = consent["trust_score"]
        friends_allowed = consent["friends_allowed"]

        # Check if viewer is in friends list
        is_friend = viewer_id in friends_allowed

        # Face-specific rules
        public_faces = {"product_details", "provenance", "social_layer", "esg_impact"}
        private_faces = {"ownership"}
        authenticated_faces = {"lifecycle"}

        if face_name in public_faces:
            decision = "allow"
            resolved_scope = "public"
        elif face_name in private_faces:
            # Ownership face requires escalation for non-owners
            if is_friend and trust_score >= 0.75:
                decision = "allow"
                resolved_scope = "friends_only"
            else:
                decision = "escalate"
                resolved_scope = "private"
        elif face_name in authenticated_faces:
            # Lifecycle requires authentication
            if viewer_id == "anonymous":
                decision = "deny"
                resolved_scope = "public"
            elif is_friend:
                decision = "allow"
                resolved_scope = "friends_only"
            else:
                decision = "escalate"
                resolved_scope = "authenticated"
        else:
            # Unknown face, escalate
            decision = "escalate"
            resolved_scope = "unknown"

    logger.info({
        "event": "face_policy_decision",
        "viewer": redact_user_id(viewer_id),
        "owner": redact_user_id(owner_id),
        "cube_partial": truncate_id(cube_id),
        "face": face_name,
        "decision": decision,
        "request_id": request_id,
    })

    resp = JSONResponse(content={"decision": decision, "resolved_scope": resolved_scope})
    ensure_request_id(request, resp)
    return resp


@app.post("/policy/canTransferOwnership")
async def can_transfer_ownership(payload: dict, request: Request):
    """
    Check if ownership transfer is allowed.
    Used by cube-service for ownership transfer operations.

    Payload:
        from_owner_id: str - Current owner
        to_owner_id: str - Prospective new owner
        cube_id: str - Cube identifier
        price: float - Transfer price (optional)

    Returns:
        {"decision": "allow" | "escalate" | "deny"}
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    from_owner_id = payload.get("from_owner_id")
    to_owner_id = payload.get("to_owner_id")
    cube_id = payload.get("cube_id")
    price = payload.get("price")

    # High-value transfers require human approval
    if price and price > 10000:
        decision = "escalate"
        reason = "high_value_transaction"
    else:
        # Allow standard transfers
        decision = "allow"
        reason = "standard_transfer"

    logger.info({
        "event": "ownership_transfer_policy",
        "from_owner": redact_user_id(from_owner_id),
        "to_owner": redact_user_id(to_owner_id),
        "cube_partial": truncate_id(cube_id),
        "price": price,
        "decision": decision,
        "reason": reason,
        "request_id": request_id,
    })

    resp = JSONResponse(content={"decision": decision, "reason": reason})
    ensure_request_id(request, resp)
    return resp


@app.get("/health")
async def health():
    """Health check endpoint that verifies Spanner connectivity."""
    pool: SpannerPoolManager = app.state.spanner_pool

    try:
        is_healthy = await pool.refresh_health()
        stats = await pool.get_stats()

        if is_healthy:
            return JSONResponse(content={
                "status": "ok",
                "service": "policy",
                "database": "spanner",
                "pool_utilization": stats.utilization
            })
        else:
            return JSONResponse(
                content={
                    "status": "degraded",
                    "service": "policy",
                    "database": "unhealthy"
                },
                status_code=503
            )
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        return JSONResponse(
            content={
                "status": "error",
                "service": "policy",
                "message": str(e)
            },
            status_code=503
        )


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
