# brandme-core/policy/main.py

import datetime as dt
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id

logger = get_logger("policy_service")


class PolicyCheckRequest(BaseModel):
    scanner_user_id: str
    garment_id: str
    region_code: str
    action: str


async def fetch_owner_and_consent(scanner_user_id: str, garment_id: str, request_id: str, http_client) -> dict:
    """
    1. Resolve garment owner.
    TODO: SELECT owner_user_id FROM garments WHERE garment_id=$1
    2. GET http://identity:8005/identity/{owner_user_id}/profile
    3. Return owner_user_id, owner_region_code, trust_score, friends_allowed, consent_version
    """
    owner_user_id = "owner-stub-123"
    
    try:
        response = await http_client.get(
            f"http://identity:8005/identity/{owner_user_id}/profile",
            headers={"X-Request-Id": request_id},
            timeout=10.0,
        )
        response.raise_for_status()
        profile = response.json()
        return {
            "owner_user_id": owner_user_id,
            "owner_region_code": profile.get("region_code", "unknown"),
            "trust_score": profile.get("trust_score", 0.5),
            "friends_allowed": profile.get("friends_allowed", []),
            "consent_version": profile.get("consent_version", "consent_v1_alpha"),
        }
    except Exception as e:
        logger.error({"event": "identity_call_failed", "error": str(e), "request_id": request_id})
        return {
            "owner_user_id": owner_user_id,
            "owner_region_code": "unknown",
            "trust_score": 0.5,
            "friends_allowed": [],
            "consent_version": "consent_v1_alpha",
        }
class PolicyCheckResponse(BaseModel):
    decision: str  # "allow" | "deny" | "escalate"
    resolved_scope: str  # "public" | "friends_only" | "private"
    policy_version: str


async def fetch_consent_graph(
    scanner_user_id: str, garment_owner_user_id: str, request_id: str, http_client
) -> dict:
    """
    GET http://identity:8005/identity/{garment_owner_user_id}/profile
    Headers: {"X-Request-Id": request_id}
    Expected response includes: {"user_id", "friends_allowed", "consent_version", "region_code", "trust_score"}
    """
    # TODO: Uncomment for production HTTP call
    # try:
    #     response = await http_client.get(
    #         f"http://identity:8005/identity/{garment_owner_user_id}/profile",
    #         headers={"X-Request-Id": request_id},
    #         timeout=10.0,
    #     )
    #     response.raise_for_status()
    #     return response.json()
    # except Exception as e:
    #     logger.error({"event": "identity_call_failed", "error": str(e), "request_id": request_id})
    #     # Fallback
    #     return {
    #         "friends_allowed": [],
    #         "consent_version": "consent_v1_alpha",
    #         "trust_score": 0.5,
    #     }

    # MLS stub:
    return {
        "friends_allowed": [],
        "consent_version": "consent_v1_alpha",
        "trust_score": 0.8,
    }


def is_allowed(region_code: str) -> bool:
    """Check if region is allowed."""
    blocked_regions = {"BLOCKED_REGION"}
    return region_code not in blocked_regions


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "policy_service_started"})
    yield
    # Startup
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "policy_service_started"})
    yield
    # Shutdown
    await app.state.http_client.aclose()
    logger.info({"event": "policy_service_stopped"})


app = FastAPI(lifespan=lifespan)


@app.post("/policy/check")
async def policy_check(payload: PolicyCheckRequest, request: Request):
    """
    Check policy: consent graph + region rules -> decision + resolved_scope + policy_version.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    consent_data = await fetch_owner_and_consent(
        payload.scanner_user_id,
        payload.garment_id,
        request_id,
        app.state.http_client,
    )

    owner_user_id = consent_data["owner_user_id"]
    trust_score = consent_data["trust_score"]
    friends_allowed = consent_data["friends_allowed"]

    if payload.scanner_user_id == owner_user_id:
    # For MLS, assume garment owner is same as scanner (self-scan) or a synthetic owner
    # TODO: lookup garment_owner_user_id from garment_id in garments table
    garment_owner_user_id = payload.scanner_user_id  # MLS stub

    consent_graph = await fetch_consent_graph(
        payload.scanner_user_id, garment_owner_user_id, request_id, app.state.http_client
    )

    friends_allowed = consent_graph.get("friends_allowed", [])
    trust_score = consent_graph.get("trust_score", 0.5)

    # Determine resolved_scope based on consent graph
    if payload.scanner_user_id == garment_owner_user_id:
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
    # Check region rules
    if not is_allowed(payload.region_code):
        decision = "deny"
    else:
        # TODO: tune trust_score threshold per region, and keep per-region legal basis
        if resolved_scope != "public" and trust_score < 0.6:
            decision = "escalate"
        else:
            decision = "allow"

    policy_version = f"policy_v1_{payload.region_code}"

    response_body = {
        "decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
    }

    response = JSONResponse(content=response_body)
    request_id = ensure_request_id(request, response)

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
    logger.info(
        {
            "event": "policy_checked",
            "scanner_user": redact_user_id(payload.scanner_user_id),
            "garment_owner": redact_user_id(garment_owner_user_id),
            "resolved_scope": resolved_scope,
            "decision": decision,
            "region_code": payload.region_code,
            "request_id": request_id,
        }
    )

    return response


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
