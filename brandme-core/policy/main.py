# Brand.Me v7 — Stable Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-core/policy/main.py

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id
from brandme_core.db import safe_close_pool

logger = get_logger("policy_service")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")


class PolicyCheckRequest(BaseModel):
    scanner_user_id: str
    garment_id: str
    region_code: str
    action: str


async def fetch_owner_and_consent(scanner_user_id: str, garment_id: str, request_id: str, http_client) -> dict:
    """
    1. Resolve garment owner.
    TODO: SELECT owner_user_id FROM garments WHERE garment_id=$1
    TEMP: owner_user_id = "owner-stub-123"
    2. GET http://identity:8005/identity/{owner_user_id}/profile with retry logic
    Headers: {"X-Request-Id": request_id}
    3. Return owner_user_id, owner_region_code, trust_score, friends_allowed, consent_version
    # v6 fix: Ensures friends_allowed and trust_score defaults are returned
    """
    from brandme_core.http_client import http_get_with_retry
    from brandme_core.env import get_service_url
    
    owner_user_id = "owner-stub-123"
    identity_url = f"{get_service_url('identity')}/identity/{owner_user_id}/profile"

    # v7 fix: use retry logic for service-to-service calls
    try:
        response = await http_get_with_retry(
            http_client,
            identity_url,
            headers={"X-Request-Id": request_id},
            timeout=10.0,
            max_retries=3,
        )
        profile = response.json()
        # v6 fix: explicit defaults for friends_allowed and trust_score
        return {
            "owner_user_id": owner_user_id,
            "owner_region_code": profile.get("region_code", "unknown"),
            "trust_score": profile.get("trust_score", 0.5),
            "friends_allowed": profile.get("friends_allowed", []),
            "consent_version": profile.get("consent_version", "consent_v1_alpha"),
        }
    except Exception as e:
        logger.error({"event": "identity_call_failed", "error": str(e), "request_id": request_id})
        # v6 fix: fallback defaults if identity service fails
        return {
            "owner_user_id": owner_user_id,
            "owner_region_code": "unknown",
            "trust_score": 0.5,
            "friends_allowed": [],
            "consent_version": "consent_v1_alpha",
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "policy_service_started"})
    yield
    if app.state.http_client:
        await app.state.http_client.aclose()
    logger.info({"event": "policy_service_stopped"})


app = FastAPI(lifespan=lifespan)

# v7 fix: enable CORS with secure configuration
from brandme_core.cors_config import get_cors_config
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    **cors_config
)


@app.post("/policy/check")
async def policy_check(payload: PolicyCheckRequest, request: Request):
    """
    Check policy: consent graph + region rules -> decision + resolved_scope + policy_version.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent = await fetch_owner_and_consent(
        payload.scanner_user_id,
        payload.garment_id,
        request_id,
        app.state.http_client,
    )

    owner_user_id = consent["owner_user_id"]
    trust_score = consent["trust_score"]
    friends_allowed = consent["friends_allowed"]

    if payload.scanner_user_id == owner_user_id:
        resolved_scope = "private"
    elif payload.scanner_user_id in friends_allowed:
        resolved_scope = "friends_only"
    else:
        resolved_scope = "public"

    blocked_regions = {"BLOCKED_REGION"}
    if payload.region_code in blocked_regions:
        decision = "deny"
    else:
        if resolved_scope != "public" and trust_score < 0.75:
            decision = "escalate"
        else:
            decision = "allow"

    policy_version = f"policy_v1_{payload.region_code}"

    resp_body = {
        "decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
    }

    json_resp = JSONResponse(content=resp_body)
    request_id = ensure_request_id(request, json_resp)

    logger.info({
        "event": "policy_decision",
        "scanner_user": redact_user_id(payload.scanner_user_id),
        "garment_owner": redact_user_id(owner_user_id),
        "garment_partial": truncate_id(payload.garment_id),
        "region_code": payload.region_code,
        "decision": decision,
        "resolved_scope": resolved_scope,
        "request_id": request_id,
    })

    return json_resp


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
    """Health check endpoint."""
    return JSONResponse(content={"status": "ok", "service": "policy"})
