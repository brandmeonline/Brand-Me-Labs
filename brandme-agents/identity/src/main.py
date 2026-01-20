# Brand.Me v9 — 2030 Agentic & Circular Economy
# Implements: User identity, consent graph, ZK proof of ownership for AR glasses
# brandme-agents/identity/src/main.py

import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional, List
from pydantic import BaseModel

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id
from brandme_core.metrics import get_metrics_collector, generate_metrics
from brandme_core.spanner import create_spanner_client, SpannerClient
from brandme_core.spanner.consent_graph import ConsentGraphClient
from brandme_core.spanner.pool import create_pool_manager, SpannerPoolManager
from brandme_core.spanner.pii_redactor import PIIRedactingClient
from brandme_core.zk import ZKProofManager, ProofRequest, ProofType

logger = get_logger("identity_service")
metrics = get_metrics_collector("identity")

# v9: ZK Proof configuration
ZK_PROOF_ENABLED = os.getenv("ZK_PROOF_ENABLED", "true").lower() == "true"
ZK_PROOF_TTL_MINUTES = int(os.getenv("ZK_PROOF_CACHE_TTL_MINUTES", "60"))


class AddFriendRequest(BaseModel):
    friend_user_id: str


class UpdateConsentRequest(BaseModel):
    scope: str  # 'global', 'asset_specific', 'facet_specific'
    visibility: str  # 'public', 'friends_only', 'private'
    asset_id: Optional[str] = None
    facet_type: Optional[str] = None


# v9: ZK Proof request models
class GenerateProofRequest(BaseModel):
    """Request to generate a ZK proof of ownership."""
    asset_id: str
    device_id: Optional[str] = None  # AR glasses device ID
    challenge_nonce: Optional[str] = None  # Fresh challenge from verifier
    proof_type: str = "ownership"  # ownership, membership, attribute


class VerifyProofRequest(BaseModel):
    """Request to verify a ZK proof."""
    proof_id: str
    proof_data: str  # Base64 encoded proof data
    public_signals: dict
    device_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Spanner pool manager
    pool_manager = create_pool_manager()
    await pool_manager.initialize()
    app.state.spanner_pool = pool_manager

    # Initialize consent graph client
    app.state.consent_graph = ConsentGraphClient(pool_manager)

    # Initialize PII-redacting client
    app.state.pii_client = PIIRedactingClient(pool_manager)

    # v9: Initialize ZK proof manager for AR glasses
    if ZK_PROOF_ENABLED:
        app.state.zk_manager = ZKProofManager(
            spanner_pool=pool_manager,
            ttl_minutes=ZK_PROOF_TTL_MINUTES,
            enable_device_binding=True
        )
        logger.info({
            "event": "zk_proof_manager_initialized",
            "ttl_minutes": ZK_PROOF_TTL_MINUTES
        })
    else:
        app.state.zk_manager = None

    logger.info({
        "event": "identity_service_started",
        "database": "spanner",
        "project": os.getenv('SPANNER_PROJECT_ID', 'brandme-project'),
        "zk_proof_enabled": ZK_PROOF_ENABLED
    })

    yield

    # Cleanup
    await pool_manager.close()
    logger.info({"event": "identity_service_stopped"})


app = FastAPI(lifespan=lifespan)

# CORS configuration
from brandme_core.cors_config import get_cors_config
cors_config = get_cors_config()
app.add_middleware(CORSMiddleware, **cors_config)


@app.get("/identity/{user_id}/profile")
async def get_identity_profile(user_id: str, request: Request):
    """
    Get user identity profile including consent graph and friends.

    Returns:
        - user_id, display_name, region_code, trust_score
        - did_cardano (if available)
        - friends_allowed (list of friend user IDs)
        - consent_version

    Falls back to synthetic record if user not found (prevents 500s).
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    pool: SpannerPoolManager = app.state.spanner_pool
    consent_graph: ConsentGraphClient = app.state.consent_graph

    try:
        # Query user from Spanner
        from google.cloud.spanner_v1 import param_types

        async with pool.session() as snapshot:
            result = snapshot.execute_sql(
                """
                SELECT
                    user_id, handle, display_name, region_code,
                    trust_score, did_cardano, consent_version
                FROM Users
                WHERE user_id = @user_id
                """,
                params={'user_id': user_id},
                param_types={'user_id': param_types.STRING}
            )
            rows = list(result)

        if rows:
            row = rows[0]
            # Get friends list
            friends = await consent_graph.get_friends_list(user_id)

            payload = {
                "user_id": row[0],
                "handle": row[1],
                "display_name": row[2] or "unknown",
                "region_code": row[3] or "us-east1",
                "trust_score": float(row[4]) if row[4] else 0.5,
                "did_cardano": row[5],
                "friends_allowed": friends,
                "consent_version": row[6] or "consent_v1",
            }

            metrics.increment_counter("profile_lookups", {"status": "found"})
        else:
            # Return synthetic record for unknown users
            payload = {
                "user_id": user_id,
                "handle": None,
                "display_name": "unknown",
                "region_code": "unknown",
                "trust_score": 0.5,
                "did_cardano": None,
                "friends_allowed": [],
                "consent_version": "consent_v1",
            }

            metrics.increment_counter("profile_lookups", {"status": "not_found"})

    except Exception as e:
        logger.error({
            "event": "profile_lookup_failed",
            "user_redacted": redact_user_id(user_id),
            "error": str(e),
            "request_id": request_id
        })

        # Fallback for resilience
        payload = {
            "user_id": user_id,
            "display_name": "unknown",
            "region_code": "unknown",
            "trust_score": 0.5,
            "did_cardano": None,
            "friends_allowed": [],
            "consent_version": "consent_v1",
        }

        metrics.increment_counter("profile_lookups", {"status": "error"})

    logger.info({
        "event": "identity_profile_lookup",
        "user_redacted": redact_user_id(user_id),
        "region_code": payload["region_code"],
        "trust_score": payload["trust_score"],
        "friends_allowed_count": len(payload["friends_allowed"]),
        "request_id": request_id,
    })

    return JSONResponse(content=payload)


@app.get("/identity/{user_id}/friends")
async def get_friends(user_id: str, request: Request):
    """Get list of user's friends."""
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_graph: ConsentGraphClient = app.state.consent_graph

    try:
        friends = await consent_graph.get_friends_list(user_id)

        return JSONResponse(content={
            "user_id": user_id,
            "friends": friends,
            "count": len(friends)
        })

    except Exception as e:
        logger.error({
            "event": "get_friends_failed",
            "user_redacted": redact_user_id(user_id),
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to retrieve friends")


@app.post("/identity/{user_id}/friends")
async def add_friend(user_id: str, req: AddFriendRequest, request: Request):
    """Send a friend request."""
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_graph: ConsentGraphClient = app.state.consent_graph

    try:
        success = await consent_graph.add_friend(
            user_id_1=user_id,
            user_id_2=req.friend_user_id,
            initiated_by=user_id
        )

        if success:
            logger.info({
                "event": "friend_request_sent",
                "from": redact_user_id(user_id),
                "to": redact_user_id(req.friend_user_id),
                "request_id": request_id
            })
            return JSONResponse(content={"status": "pending", "message": "Friend request sent"})
        else:
            raise HTTPException(status_code=400, detail="Could not send friend request")

    except HTTPException:
        raise
    except Exception as e:
        logger.error({
            "event": "add_friend_failed",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to add friend")


@app.post("/identity/{user_id}/friends/{friend_id}/accept")
async def accept_friend(user_id: str, friend_id: str, request: Request):
    """Accept a pending friend request."""
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_graph: ConsentGraphClient = app.state.consent_graph

    try:
        success = await consent_graph.accept_friend(user_id, friend_id)

        if success:
            logger.info({
                "event": "friend_request_accepted",
                "user": redact_user_id(user_id),
                "friend": redact_user_id(friend_id),
                "request_id": request_id
            })
            return JSONResponse(content={"status": "accepted"})
        else:
            raise HTTPException(status_code=400, detail="Could not accept friend request")

    except HTTPException:
        raise
    except Exception as e:
        logger.error({
            "event": "accept_friend_failed",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to accept friend")


@app.get("/identity/{user_id}/consent")
async def get_consent_policies(user_id: str, request: Request):
    """Get user's consent policies."""
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    pool: SpannerPoolManager = app.state.spanner_pool

    try:
        from google.cloud.spanner_v1 import param_types

        async with pool.session() as snapshot:
            result = snapshot.execute_sql(
                """
                SELECT
                    consent_id, scope, visibility, asset_id, facet_type,
                    grantee_user_id, is_revoked, policy_version, created_at
                FROM ConsentPolicies
                WHERE user_id = @user_id AND is_revoked = false
                ORDER BY created_at DESC
                """,
                params={'user_id': user_id},
                param_types={'user_id': param_types.STRING}
            )

            policies = []
            for row in result:
                policies.append({
                    "consent_id": row[0],
                    "scope": row[1],
                    "visibility": row[2],
                    "asset_id": row[3],
                    "facet_type": row[4],
                    "grantee_user_id": row[5],
                    "is_revoked": row[6],
                    "policy_version": row[7],
                    "created_at": row[8].isoformat() if row[8] else None
                })

        return JSONResponse(content={
            "user_id": user_id,
            "policies": policies
        })

    except Exception as e:
        logger.error({
            "event": "get_consent_failed",
            "user_redacted": redact_user_id(user_id),
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to retrieve consent policies")


@app.post("/identity/{user_id}/consent")
async def update_consent(user_id: str, req: UpdateConsentRequest, request: Request):
    """Update user's consent policy."""
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_graph: ConsentGraphClient = app.state.consent_graph

    try:
        from brandme_core.spanner.consent_graph import ConsentScope, Visibility

        scope = ConsentScope(req.scope)
        visibility = Visibility(req.visibility)

        consent_id = await consent_graph.grant_consent(
            user_id=user_id,
            scope=scope,
            visibility=visibility,
            asset_id=req.asset_id,
            facet_type=req.facet_type
        )

        logger.info({
            "event": "consent_updated",
            "user_redacted": redact_user_id(user_id),
            "scope": req.scope,
            "visibility": req.visibility,
            "consent_id": consent_id,
            "request_id": request_id
        })

        return JSONResponse(content={
            "status": "created",
            "consent_id": consent_id
        })

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error({
            "event": "update_consent_failed",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to update consent")


@app.post("/identity/{user_id}/consent/revoke-all")
async def revoke_all_consent(user_id: str, request: Request):
    """
    Revoke ALL consent for a user (global revocation).

    This is an instant operation that revokes all consent policies.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_graph: ConsentGraphClient = app.state.consent_graph

    try:
        count = await consent_graph.revoke_global_consent(
            user_id=user_id,
            reason="user_requested_global_revocation"
        )

        logger.info({
            "event": "global_consent_revoked",
            "user_redacted": redact_user_id(user_id),
            "policies_revoked": count,
            "request_id": request_id
        })

        return JSONResponse(content={
            "status": "revoked",
            "policies_revoked": count
        })

    except Exception as e:
        logger.error({
            "event": "revoke_all_consent_failed",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to revoke consent")


# ===========================================
# v9: ZK PROOF OF OWNERSHIP ENDPOINTS
# For AR glasses proof of ownership without sharing private keys
# ===========================================

@app.post("/identity/{user_id}/zk/generate")
async def generate_zk_proof(user_id: str, req: GenerateProofRequest, request: Request):
    """
    Generate a ZK proof of asset ownership.

    Used by AR glasses to verify ownership without exposing private keys.
    The proof can be cached and reused until expiration.

    Args:
        user_id: User requesting the proof
        req: Proof generation request with asset_id and optional device binding

    Returns:
        ZK proof that can be sent to verifiers
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    if not ZK_PROOF_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="ZK proof service is disabled"
        )

    zk_manager: ZKProofManager = app.state.zk_manager

    try:
        # Map proof type string to enum
        try:
            proof_type = ProofType(req.proof_type)
        except ValueError:
            proof_type = ProofType.OWNERSHIP

        # Check for cached proof first
        cached = await zk_manager.get_cached_proof(
            user_id=user_id,
            asset_id=req.asset_id,
            device_id=req.device_id
        )

        if cached and cached.is_valid():
            logger.info({
                "event": "zk_proof_cache_hit",
                "user_redacted": redact_user_id(user_id),
                "asset_id": req.asset_id[:8] + "...",
                "request_id": request_id
            })

            metrics.increment_counter("zk_proof_requests", {"status": "cache_hit"})

            return JSONResponse(content={
                "status": "cached",
                "proof_id": cached.proof_id,
                "proof_data": cached.proof_data.decode() if isinstance(cached.proof_data, bytes) else cached.proof_data,
                "public_signals": cached.public_signals,
                "expires_at": cached.expires_at.isoformat(),
                "device_bound": cached.device_bound
            })

        # Generate new proof
        proof_request = ProofRequest(
            user_id=user_id,
            asset_id=req.asset_id,
            proof_type=proof_type,
            device_id=req.device_id,
            challenge_nonce=req.challenge_nonce
        )

        result = await zk_manager.generate_proof(proof_request)

        if not result.success:
            metrics.increment_counter("zk_proof_requests", {"status": "failed"})
            raise HTTPException(
                status_code=400,
                detail=result.error or "Failed to generate proof"
            )

        metrics.increment_counter("zk_proof_requests", {"status": "generated"})

        logger.info({
            "event": "zk_proof_generated",
            "user_redacted": redact_user_id(user_id),
            "asset_id": req.asset_id[:8] + "...",
            "proof_id": result.proof.proof_id,
            "generation_time_ms": result.generation_time_ms,
            "request_id": request_id
        })

        return JSONResponse(content={
            "status": "generated",
            "proof_id": result.proof.proof_id,
            "proof_data": result.proof.proof_data.decode() if isinstance(result.proof.proof_data, bytes) else result.proof.proof_data,
            "public_signals": result.proof.public_signals,
            "expires_at": result.proof.expires_at.isoformat(),
            "device_bound": result.proof.device_bound,
            "generation_time_ms": result.generation_time_ms
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error({
            "event": "zk_proof_generation_failed",
            "user_redacted": redact_user_id(user_id),
            "error": str(e),
            "request_id": request_id
        })
        metrics.increment_counter("zk_proof_requests", {"status": "error"})
        raise HTTPException(status_code=500, detail="Failed to generate ZK proof")


@app.post("/identity/{user_id}/zk/verify")
async def verify_zk_proof(user_id: str, req: VerifyProofRequest, request: Request):
    """
    Verify a ZK proof of ownership.

    Called by AR glasses or other verifiers to confirm ownership
    without needing to see the user's private key.

    Args:
        user_id: User who generated the proof
        req: Proof verification request

    Returns:
        Verification result with claim details
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    if not ZK_PROOF_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="ZK proof service is disabled"
        )

    zk_manager: ZKProofManager = app.state.zk_manager

    try:
        import json
        import base64
        from datetime import datetime

        # Reconstruct proof object from request
        try:
            proof_data = base64.b64decode(req.proof_data)
        except Exception:
            proof_data = req.proof_data.encode()

        from brandme_core.zk import ProofOfOwnership

        proof = ProofOfOwnership(
            proof_id=req.proof_id,
            user_id_commitment=req.public_signals.get("user_commitment", ""),
            asset_id_commitment=req.public_signals.get("asset_commitment", ""),
            proof_type=ProofType.OWNERSHIP,
            proof_data=proof_data,
            public_signals=req.public_signals,
            created_at=datetime.utcnow(),
            expires_at=datetime.fromisoformat(req.public_signals.get("expires_at", datetime.utcnow().isoformat())),
            device_bound=req.device_id
        )

        result = await zk_manager.verify_proof(
            proof=proof,
            device_id=req.device_id
        )

        if result.is_valid:
            metrics.increment_counter("zk_proof_verifications", {"status": "valid"})
        else:
            metrics.increment_counter("zk_proof_verifications", {"status": "invalid"})

        logger.info({
            "event": "zk_proof_verified",
            "user_redacted": redact_user_id(user_id),
            "proof_id": req.proof_id,
            "is_valid": result.is_valid,
            "verification_time_ms": result.verification_time_ms,
            "request_id": request_id
        })

        return JSONResponse(content={
            "is_valid": result.is_valid,
            "proof_id": result.proof_id,
            "verified_claims": result.verified_claims,
            "reason": result.reason,
            "verification_time_ms": result.verification_time_ms
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error({
            "event": "zk_proof_verification_failed",
            "error": str(e),
            "request_id": request_id
        })
        metrics.increment_counter("zk_proof_verifications", {"status": "error"})
        raise HTTPException(status_code=500, detail="Failed to verify ZK proof")


@app.get("/identity/{user_id}/zk/proofs")
async def list_active_proofs(user_id: str, request: Request):
    """
    List active ZK proofs for a user.

    Returns all non-expired proofs from the cache.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    if not ZK_PROOF_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="ZK proof service is disabled"
        )

    pool: SpannerPoolManager = app.state.spanner_pool

    try:
        from google.cloud.spanner_v1 import param_types

        async with pool.session() as snapshot:
            result = snapshot.execute_sql(
                """
                SELECT proof_id, asset_id, proof_type, device_id, created_at, expires_at
                FROM ZKProofCache
                WHERE user_id = @user_id
                    AND expires_at > CURRENT_TIMESTAMP()
                ORDER BY created_at DESC
                LIMIT 100
                """,
                params={"user_id": user_id},
                param_types={"user_id": param_types.STRING}
            )

            proofs = []
            for row in result:
                proofs.append({
                    "proof_id": row[0],
                    "asset_id": row[1],
                    "proof_type": row[2],
                    "device_id": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "expires_at": row[5].isoformat() if row[5] else None
                })

        return JSONResponse(content={
            "user_id": user_id,
            "active_proofs": proofs,
            "count": len(proofs)
        })

    except Exception as e:
        logger.error({
            "event": "list_proofs_failed",
            "user_redacted": redact_user_id(user_id),
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to list proofs")


@app.delete("/identity/{user_id}/zk/proofs")
async def invalidate_proofs(user_id: str, request: Request, asset_id: Optional[str] = None):
    """
    Invalidate ZK proofs for a user.

    Call this after ownership transfer to ensure old proofs can't be reused.

    Args:
        user_id: User whose proofs to invalidate
        asset_id: Optional specific asset (or all if not provided)

    Returns:
        Number of proofs invalidated
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    if not ZK_PROOF_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="ZK proof service is disabled"
        )

    zk_manager: ZKProofManager = app.state.zk_manager

    try:
        count = await zk_manager.invalidate_proofs(
            user_id=user_id,
            asset_id=asset_id
        )

        logger.info({
            "event": "zk_proofs_invalidated",
            "user_redacted": redact_user_id(user_id),
            "asset_id": asset_id[:8] + "..." if asset_id else "all",
            "count": count,
            "request_id": request_id
        })

        return JSONResponse(content={
            "status": "invalidated",
            "proofs_removed": count,
            "asset_id": asset_id
        })

    except Exception as e:
        logger.error({
            "event": "invalidate_proofs_failed",
            "user_redacted": redact_user_id(user_id),
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to invalidate proofs")


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
                "service": "identity",
                "version": "v9",
                "database": "spanner",
                "pool_utilization": stats.utilization,
                "zk_proof_enabled": ZK_PROOF_ENABLED
            })
        else:
            return JSONResponse(
                content={
                    "status": "degraded",
                    "service": "identity",
                    "database": "unhealthy"
                },
                status_code=503
            )
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        return JSONResponse(
            content={
                "status": "error",
                "service": "identity",
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
