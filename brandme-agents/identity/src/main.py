# Brand.Me v8 — Global Integrity Spine with Spanner + Firestore
# Implements: User identity, consent graph, friendship lookups via Spanner
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

logger = get_logger("identity_service")
metrics = get_metrics_collector("identity")


class AddFriendRequest(BaseModel):
    friend_user_id: str


class UpdateConsentRequest(BaseModel):
    scope: str  # 'global', 'asset_specific', 'facet_specific'
    visibility: str  # 'public', 'friends_only', 'private'
    asset_id: Optional[str] = None
    facet_type: Optional[str] = None


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

    logger.info({
        "event": "identity_service_started",
        "database": "spanner",
        "project": os.getenv('SPANNER_PROJECT_ID', 'brandme-project')
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
                "database": "spanner",
                "pool_utilization": stats.utilization
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
