import datetime as dt
import hashlib
import json
import uuid
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id

logger = get_logger("orchestrator_service")


async def call_knowledge_service(garment_id: str, scope: str, request_id: str) -> List[Dict[str, object]]:
    """
    Query knowledge service:
    GET http://knowledge:8003/garment/{garment_id}/passport?scope={scope}

    Headers: X-Request-Id: request_id
    Return ONLY the "facets" list from the JSON.
    """
    # MLS stub:
    return [
        {
            "facet_type": "esg_score",
            "value": {"carbon_g_per_unit": 120, "water_l_per_unit": 45},
            "visibility": "public"
        }
    ]

    # Production:
    # async with httpx.AsyncClient() as client:
    #     resp = await client.get(
    #         f"http://knowledge:8003/garment/{garment_id}/passport",
    #         params={"scope": scope},
    #         headers={"X-Request-Id": request_id}
    #     )
    #     resp.raise_for_status()
    #     data = resp.json()
    #     return data.get("facets", [])


async def call_compliance_audit_log(
    scan_id: str,
    decision_summary: str,
    decision_detail: Dict[str, object],
    risk_flagged: bool,
    escalated_to_human: bool,
    request_id: str
) -> None:
    """
    POST http://compliance:8004/audit/log

    Body: {
        "scan_id": scan_id,
        "decision_summary": decision_summary,
        "decision_detail": decision_detail,
        "risk_flagged": risk_flagged,
        "escalated_to_human": escalated_to_human
    }
    Headers: X-Request-Id: request_id
    """
    # Production:
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://compliance:8004/audit/log",
            json={
                "scan_id": scan_id,
                "decision_summary": decision_summary,
                "decision_detail": decision_detail,
                "risk_flagged": risk_flagged,
                "escalated_to_human": escalated_to_human
            },
            headers={"X-Request-Id": request_id}
        )


async def call_compliance_anchor_chain(
    scan_id: str,
    tx_hashes: Dict[str, str],
    request_id: str
) -> None:
    """
    POST http://compliance:8004/audit/anchorChain

    Body: {
        "scan_id": scan_id,
        "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
        "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
        "crosschain_root_hash": tx_hashes["crosschain_root_hash"]
    }
    Headers: X-Request-Id: request_id
    """
    # Production:
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://compliance:8004/audit/anchorChain",
            json={
                "scan_id": scan_id,
                "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
                "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
                "crosschain_root_hash": tx_hashes["crosschain_root_hash"]
            },
            headers={"X-Request-Id": request_id}
        )


async def call_cardano_anchor(facets: List[Dict], garment_id: str, scan_id: str) -> str:
    """Stub: anchor public facets to Cardano."""
    public_facets = [f for f in facets if f.get("visibility") == "public"]
    payload = {
        "garment_id": garment_id,
        "scan_id": scan_id,
        "public_facets_count": len(public_facets)
    }
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    tx_hash = f"cardano_{payload_hash[:16]}"
    logger.info({
        "event": "cardano_anchor_stub",
        "scan_id": scan_id,
        "tx_hash": tx_hash,
        "public_facets_count": len(public_facets)
    })
    return tx_hash


async def call_midnight_anchor(facets: List[Dict], garment_id: str, scan_id: str, scope: str) -> str:
    """Stub: anchor private facets to Midnight."""
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
        "event": "midnight_anchor_stub",
        "scan_id": scan_id,
        "tx_hash": tx_hash,
        "private_facets_count": len(private_facets)
    })
    return tx_hash


def compute_crosschain_root(cardano_tx: str, midnight_tx: str) -> str:
    """Compute a deterministic cross-chain root hash."""
    combined = f"{cardano_tx}|{midnight_tx}"
    root = hashlib.sha256(combined.encode()).hexdigest()
    return root


async def process_allowed_scan(decision_packet: Dict[str, str], request_id: str) -> Dict[str, object]:
    """
    Orchestrate the allowed scan flow:
    1. Fetch facets from knowledge service (scoped by resolved_scope)
    2. Anchor public facets to Cardano
    3. Anchor private facets to Midnight
    4. Compute cross-chain root
    5. Log to compliance
    6. Return scan result
    """
    scan_id = decision_packet["scan_id"]
    garment_id = decision_packet["garment_id"]
    scanner_user_id = decision_packet["scanner_user_id"]
    resolved_scope = decision_packet["resolved_scope"]
    policy_version = decision_packet["policy_version"]
    region_code = decision_packet["region_code"]
    occurred_at = decision_packet.get("occurred_at", dt.datetime.utcnow().isoformat() + "Z")

    # TODO: if decision_packet.get("escalated") == True:
    #   MUST NOT anchor and MUST set risk_flagged=True and escalated_to_human=True

    # 1. Fetch facets
    facets = await call_knowledge_service(garment_id, resolved_scope, request_id)

    # 2. Anchor to Cardano (public)
    cardano_tx_hash = await call_cardano_anchor(facets, garment_id, scan_id)

    # 3. Anchor to Midnight (private)
    midnight_tx_hash = await call_midnight_anchor(facets, garment_id, scan_id, resolved_scope)

    # 4. Compute cross-chain root
    crosschain_root_hash = compute_crosschain_root(cardano_tx_hash, midnight_tx_hash)

    # 5. Log to compliance
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

    # 6. Anchor chain hashes to compliance
    tx_hashes = {
        "cardano_tx_hash": cardano_tx_hash,
        "midnight_tx_hash": midnight_tx_hash,
        "crosschain_root_hash": crosschain_root_hash
    }

    await call_compliance_anchor_chain(scan_id, tx_hashes, request_id)

    # 7. Return result
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
        "cardano_tx_hash": cardano_tx_hash,
        "midnight_tx_hash": midnight_tx_hash,
        "crosschain_root_hash": crosschain_root_hash,
        "request_id": request_id
    })

    return result


# FastAPI app
app = FastAPI()


class OrchestratorScanPacket(BaseModel):
    scan_id: str
    scanner_user_id: str
    garment_id: str
    resolved_scope: str
    policy_version: str
    region_code: str
    occurred_at: str  # iso8601Z string from brain


@app.post("/scan/commit")
async def scan_commit(packet: OrchestratorScanPacket, request: Request):
    """
    HTTP endpoint for brain to call orchestrator.
    """
    # Build decision_packet dict
    decision_packet = {
        "scan_id": packet.scan_id,
        "scanner_user_id": packet.scanner_user_id,
        "garment_id": packet.garment_id,
        "resolved_scope": packet.resolved_scope,
        "policy_version": packet.policy_version,
        "region_code": packet.region_code,
        "occurred_at": packet.occurred_at
    }

    # Get request_id from headers or generate
    temp_request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    # Process
    result = await process_allowed_scan(decision_packet, temp_request_id)

    # Wrap in JSONResponse
    response = JSONResponse(result)

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log
    logger.info({
        "event": "scan_commit_endpoint",
        "scan_id": packet.scan_id,
        "scanner_user_redacted": redact_user_id(packet.scanner_user_id),
        "garment_partial": packet.garment_id[:8] + "…",
        "region_code": packet.region_code,
        "shown_facets_count": result["shown_facets_count"],
        "request_id": request_id
    })

    return response
