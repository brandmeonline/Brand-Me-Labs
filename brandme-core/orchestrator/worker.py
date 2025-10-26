"""
Brand.Me Orchestrator Service
==============================
Coordinates scan processing: knowledge retrieval, blockchain anchoring, compliance logging.

Features:
- Resilient HTTP clients with automatic retries
- Proper error handling for downstream services
- Health check endpoints
- Graceful degradation when services are unavailable
"""
import datetime as dt
import hashlib
import json
import uuid
from typing import Dict, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator

from brandme_core import (
    get_logger,
    redact_user_id,
    ensure_request_id,
    config,
    get_http_client,
    close_all_clients,
    ServiceUnavailableError,
)

logger = get_logger("orchestrator_service")


# ============================================================================
# Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("Orchestrator service startup complete")
    yield
    await close_all_clients()
    logger.info("Orchestrator service shutdown complete")


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Brand.Me Orchestrator Service",
    description="Scan processing coordination and blockchain anchoring",
    version="2.0.0",
    lifespan=lifespan
)


# ============================================================================
# Request/Response Models
# ============================================================================

class OrchestratorScanPacket(BaseModel):
    scan_id: str
    scanner_user_id: str
    garment_id: str
    resolved_scope: str
    policy_version: str
    region_code: str
    occurred_at: str

    @validator('*')
    def validate_not_empty(cls, v):
        if isinstance(v, str) and (not v or not v.strip()):
            raise ValueError("Field cannot be empty")
        return v


# ============================================================================
# Helper Functions - Service Calls
# ============================================================================

async def call_knowledge_service(garment_id: str, scope: str, request_id: str) -> List[Dict]:
    """Query knowledge service for garment facets."""
    if config.ENABLE_STUB_MODE:
        return [
            {
                "facet_type": "esg_score",
                "value": {"carbon_g_per_unit": 120, "water_l_per_unit": 45},
                "visibility": "public"
            }
        ]

    try:
        client = get_http_client("knowledge", config.KNOWLEDGE_SERVICE_URL)
        response = await client.get(
            f"/garment/{garment_id}/passport",
            request_id=request_id,
            params={"scope": scope}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("facets", [])

    except ServiceUnavailableError as e:
        logger.warning("Knowledge service unavailable, using stub", extra={"error": str(e)})
        return []


async def call_compliance_audit_log(
    scan_id: str,
    decision_summary: str,
    decision_detail: Dict,
    risk_flagged: bool,
    escalated_to_human: bool,
    request_id: str
) -> None:
    """Log audit event to compliance service."""
    if config.ENABLE_STUB_MODE:
        logger.debug("Stub: would log to compliance", extra={"scan_id": scan_id})
        return

    try:
        client = get_http_client("compliance", config.COMPLIANCE_SERVICE_URL)
        await client.post(
            "/audit/log",
            request_id=request_id,
            json={
                "scan_id": scan_id,
                "decision_summary": decision_summary,
                "decision_detail": decision_detail,
                "risk_flagged": risk_flagged,
                "escalated_to_human": escalated_to_human
            }
        )
    except ServiceUnavailableError as e:
        logger.error("Compliance service unavailable for audit log", extra={"error": str(e), "scan_id": scan_id})
        # Don't fail the scan - audit can be replayed later


async def call_compliance_anchor_chain(
    scan_id: str,
    tx_hashes: Dict[str, str],
    request_id: str
) -> None:
    """Record blockchain anchors in compliance service."""
    if config.ENABLE_STUB_MODE:
        logger.debug("Stub: would record anchors", extra={"scan_id": scan_id})
        return

    try:
        client = get_http_client("compliance", config.COMPLIANCE_SERVICE_URL)
        await client.post(
            "/audit/anchorChain",
            request_id=request_id,
            json={
                "scan_id": scan_id,
                **tx_hashes
            }
        )
    except ServiceUnavailableError as e:
        logger.error("Compliance service unavailable for anchor recording", extra={"error": str(e), "scan_id": scan_id})


# ============================================================================
# Helper Functions - Blockchain Anchoring (Stubs)
# ============================================================================

async def call_cardano_anchor(facets: List[Dict], garment_id: str, scan_id: str) -> str:
    """Anchor public facets to Cardano."""
    public_facets = [f for f in facets if f.get("visibility") == "public"]
    payload = {
        "garment_id": garment_id,
        "scan_id": scan_id,
        "public_facets_count": len(public_facets)
    }
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    tx_hash = f"cardano_{payload_hash[:16]}"

    logger.info({
        "event": "cardano_anchor",
        "scan_id": scan_id,
        "tx_hash": tx_hash,
        "public_facets_count": len(public_facets)
    })
    return tx_hash


async def call_midnight_anchor(facets: List[Dict], garment_id: str, scan_id: str, scope: str) -> str:
    """Anchor private facets to Midnight."""
    private_facets = [f for f in facets if f.get("visibility") in ["private", "friends_only"]]
    payload = {
        "garment_id": garment_id,
        "scan_id": scan_id,
        "scope": scope,
        "private_facets_count": len(private_facets)
    }
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    tx_hash = f"midnight_{payload_hash[:16]}"

    logger.info({
        "event": "midnight_anchor",
        "scan_id": scan_id,
        "tx_hash": tx_hash,
        "private_facets_count": len(private_facets)
    })
    return tx_hash


def compute_crosschain_root(cardano_tx: str, midnight_tx: str) -> str:
    """Compute deterministic cross-chain root hash."""
    combined = f"{cardano_tx}|{midnight_tx}"
    return hashlib.sha256(combined.encode()).hexdigest()


# ============================================================================
# Core Processing Logic
# ============================================================================

async def process_allowed_scan(decision_packet: Dict[str, str], request_id: str) -> Dict:
    """
    Orchestrate the allowed scan flow:
    1. Fetch facets from knowledge service
    2. Anchor to Cardano and Midnight
    3. Compute cross-chain root
    4. Log to compliance
    5. Return scan result
    """
    scan_id = decision_packet["scan_id"]
    garment_id = decision_packet["garment_id"]
    scanner_user_id = decision_packet["scanner_user_id"]
    resolved_scope = decision_packet["resolved_scope"]
    policy_version = decision_packet["policy_version"]
    region_code = decision_packet["region_code"]
    occurred_at = decision_packet.get("occurred_at", dt.datetime.utcnow().isoformat() + "Z")

    # 1. Fetch facets
    facets = await call_knowledge_service(garment_id, resolved_scope, request_id)

    # 2. Anchor to blockchains
    cardano_tx_hash = await call_cardano_anchor(facets, garment_id, scan_id)
    midnight_tx_hash = await call_midnight_anchor(facets, garment_id, scan_id, resolved_scope)

    # 3. Compute cross-chain root
    crosschain_root_hash = compute_crosschain_root(cardano_tx_hash, midnight_tx_hash)

    # 4. Log to compliance
    decision_detail = {
        "garment_id": garment_id,
        "scanner_user_id": scanner_user_id,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
        "region_code": region_code,
        "occurred_at": occurred_at,
        "shown_facets_count": len(facets)
    }

    await call_compliance_audit_log(
        scan_id=scan_id,
        decision_summary="scan_allowed",
        decision_detail=decision_detail,
        risk_flagged=False,
        escalated_to_human=False,
        request_id=request_id
    )

    # 5. Record chain anchors
    tx_hashes = {
        "cardano_tx_hash": cardano_tx_hash,
        "midnight_tx_hash": midnight_tx_hash,
        "crosschain_root_hash": crosschain_root_hash
    }

    await call_compliance_anchor_chain(scan_id, tx_hashes, request_id)

    # 6. Build result
    result = {
        "status": "ok",
        "scan_id": scan_id,
        "shown_facets_count": len(facets),
        "cardano_tx_hash": cardano_tx_hash,
        "midnight_tx_hash": midnight_tx_hash,
        "crosschain_root_hash": crosschain_root_hash
    }

    logger.info({
        "event": "scan_orchestrated",
        "scan_id": scan_id,
        "garment_partial": garment_id[:8] + "…",
        "scanner_user_redacted": redact_user_id(scanner_user_id),
        "shown_facets_count": len(facets),
        "request_id": request_id
    })

    return result


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({
        "service": "orchestrator",
        "status": "healthy",
        "timestamp": dt.datetime.utcnow().isoformat() + "Z"
    })


@app.post("/scan/commit")
async def scan_commit(packet: OrchestratorScanPacket, request: Request):
    """
    Process and commit an allowed scan.

    This endpoint coordinates:
    - Knowledge retrieval
    - Blockchain anchoring
    - Compliance logging
    """
    try:
        # Build decision packet
        decision_packet = packet.dict()

        # Get or generate request ID
        temp_request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

        # Process the scan
        result = await process_allowed_scan(decision_packet, temp_request_id)

        # Build response
        response = JSONResponse(result)
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "scan_commit_complete",
            "scan_id": packet.scan_id,
            "scanner_user_redacted": redact_user_id(packet.scanner_user_id),
            "garment_partial": packet.garment_id[:8] + "…",
            "region_code": packet.region_code,
            "shown_facets_count": result["shown_facets_count"],
            "request_id": request_id
        })

        return response

    except Exception as e:
        logger.error("Error in scan_commit", extra={"error": str(e), "scan_id": packet.scan_id})
        raise HTTPException(
            status_code=500,
            detail={"error": "Scan processing failed", "message": str(e)}
        )
