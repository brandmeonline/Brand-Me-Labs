# brandme-core/orchestrator/worker.py

import datetime as dt
import hashlib
import uuid
from typing import List, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncpg
import httpx

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id

logger = get_logger("orchestrator_service")


class OrchestratorScanPacket(BaseModel):
    scan_id: str
    scanner_user_id: str
    garment_id: str
    resolved_scope: str
    policy_version: str
    region_code: str
    occurred_at: str


async def call_knowledge_service(garment_id: str, scope: str, request_id: str, http_client) -> List[Dict[str, object]]:
    """
    GET http://knowledge:8003/garment/{garment_id}/passport?scope={scope}
    """
    try:
        response = await http_client.get(
            f"http://knowledge:8003/garment/{garment_id}/passport",
            params={"scope": scope},
            headers={"X-Request-Id": request_id},
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("facets", [])
    except Exception as e:
        logger.error({"event": "knowledge_call_failed", "error": str(e), "request_id": request_id})
        return []


async def call_compliance_audit_log(scan_id: str, decision_summary: str, decision_detail: Dict[str, object], risk_flagged: bool, escalated_to_human: bool, request_id: str, http_client) -> None:
    """
    POST http://compliance:8004/audit/log
    """
    try:
        await http_client.post(
            "http://compliance:8004/audit/log",
            json={
                "scan_id": scan_id,
                "decision_summary": decision_summary,
                "decision_detail": decision_detail,
                "risk_flagged": risk_flagged,
                "escalated_to_human": escalated_to_human,
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
        )
    except Exception as e:
        logger.error({"event": "compliance_audit_log_failed", "error": str(e), "request_id": request_id})


async def call_compliance_anchor_chain(scan_id: str, tx_hashes: Dict[str, str], request_id: str, http_client) -> None:
    """
    POST http://compliance:8004/audit/anchorChain
    """
    try:
        await http_client.post(
            "http://compliance:8004/audit/anchorChain",
            json={
                "scan_id": scan_id,
                "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
                "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
                "crosschain_root_hash": tx_hashes["crosschain_root_hash"],
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
        )
    except Exception as e:
        logger.error({"event": "compliance_anchor_chain_failed", "error": str(e), "request_id": request_id})
async def call_knowledge_service(
    garment_id: str, scope: str, request_id: str, http_client
) -> List[Dict[str, object]]:
    """
    GET http://knowledge:8003/garment/{garment_id}/passport?scope={scope}
    Headers: {"X-Request-Id": request_id}
    Expect: {"garment_id", "facets": [...]}
    MUST ONLY return the "facets". NEVER access fields not in that shape.
    TODO: This is where we enforce that orchestrator only ever stores previews, not private payloads.
    """
    # TODO: Uncomment for production HTTP call
    # try:
    #     response = await http_client.get(
    #         f"http://knowledge:8003/garment/{garment_id}/passport",
    #         params={"scope": scope},
    #         headers={"X-Request-Id": request_id},
    #         timeout=15.0,
    #     )
    #     response.raise_for_status()
    #     data = response.json()
    #     return data.get("facets", [])
    # except Exception as e:
    #     logger.error({"event": "knowledge_call_failed", "error": str(e), "request_id": request_id})
    #     return []

    # MLS stub:
    return [
        {
            "facet_type": "ESG",
            "facet_payload_preview": {"summary": "Sustainability certified", "rating": "A"},
        },
        {
            "facet_type": "ORIGIN",
            "facet_payload_preview": {
                "designer": "Stella McCartney",
                "cut_and_sewn": "Italy",
            },
        },
        {
            "facet_type": "MATERIALS",
            "facet_payload_preview": {"composition": "95% Organic Cotton, 5% Elastane"},
        },
    ]


async def call_compliance_audit_log(
    scan_id: str,
    decision_summary: str,
    decision_detail: Dict[str, object],
    risk_flagged: bool,
    escalated_to_human: bool,
    request_id: str,
    http_client,
) -> None:
    """
    POST http://compliance:8004/audit/log
    JSON body: {"scan_id", "decision_summary", "decision_detail", "risk_flagged", "escalated_to_human"}
    Headers: {"X-Request-Id": request_id}
    """
    # TODO: Uncomment for production HTTP call
    # try:
    #     response = await http_client.post(
    #         "http://compliance:8004/audit/log",
    #         json={
    #             "scan_id": scan_id,
    #             "decision_summary": decision_summary,
    #             "decision_detail": decision_detail,
    #             "risk_flagged": risk_flagged,
    #             "escalated_to_human": escalated_to_human,
    #         },
    #         headers={"X-Request-Id": request_id},
    #         timeout=10.0,
    #     )
    #     response.raise_for_status()
    # except Exception as e:
    #     logger.error({"event": "compliance_audit_log_failed", "error": str(e), "request_id": request_id})

    # MLS stub: no-op
    pass


async def call_compliance_anchor_chain(
    scan_id: str, tx_hashes: Dict[str, str], request_id: str, http_client
) -> None:
    """
    POST http://compliance:8004/audit/anchorChain
    JSON body: {"scan_id", "cardano_tx_hash", "midnight_tx_hash", "crosschain_root_hash"}
    Headers: {"X-Request-Id": request_id}
    """
    # TODO: Uncomment for production HTTP call
    # try:
    #     response = await http_client.post(
    #         "http://compliance:8004/audit/anchorChain",
    #         json={
    #             "scan_id": scan_id,
    #             "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
    #             "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
    #             "crosschain_root_hash": tx_hashes["crosschain_root_hash"],
    #         },
    #         headers={"X-Request-Id": request_id},
    #         timeout=10.0,
    #     )
    #     response.raise_for_status()
    # except Exception as e:
    #     logger.error({"event": "compliance_anchor_chain_failed", "error": str(e), "request_id": request_id})

    # MLS stub: no-op
    pass


def call_tx_builder(garment_id: str, facets: List[Dict], scope: str) -> Dict[str, str]:
    """
    Build transaction hashes for Cardano (public), Midnight (private), and crosschain root.
    """
    import json
    facet_hash = hashlib.sha256(json.dumps(facets, sort_keys=True).encode()).hexdigest()
    TODO: Replace with real blockchain transaction construction.
    """
    facet_hash = hashlib.sha256(str(facets).encode()).hexdigest()
    cardano_hash = hashlib.sha256((garment_id + scope + facet_hash).encode()).hexdigest()
    midnight_hash = hashlib.sha256((garment_id + "midnight" + facet_hash).encode()).hexdigest()
    crosschain_root = hashlib.sha256((cardano_hash + midnight_hash).encode()).hexdigest()

    return {
        "cardano_tx_hash": "tx_cardano_" + cardano_hash[:16],
        "midnight_tx_hash": "tx_midnight_" + midnight_hash[:16],
        "crosschain_root_hash": "root_" + crosschain_root[:16],
    }


async def process_allowed_scan(decision_packet: Dict[str, str], request_id: str, db_pool, http_client) -> Dict[str, object]:
    """
    Process allowed scan: fetch facets, persist, anchor, audit.
    TODO: if decision_packet represents escalated scan, DO NOT anchor. Call compliance /audit/escalate instead.
async def process_allowed_scan(
    decision_packet: Dict[str, str],
    request_id: str,
    db_pool,
    http_client,
) -> Dict[str, object]:
    """
    Process allowed scan: fetch facets, persist, anchor, audit.
    TODO: if decision_packet actually represents an escalated scan, we should NOT anchor.
    Instead we should call compliance /audit/escalate.
    """
    scan_id = decision_packet["scan_id"]
    scanner_user_id = decision_packet["scanner_user_id"]
    garment_id = decision_packet["garment_id"]
    resolved_scope = decision_packet["resolved_scope"]
    policy_version = decision_packet["policy_version"]
    region_code = decision_packet["region_code"]
    occurred_at = decision_packet["occurred_at"]

    shown_facets = await call_knowledge_service(garment_id, resolved_scope, request_id, http_client)

    # Fetch public-safe facets
    shown_facets = await call_knowledge_service(garment_id, resolved_scope, request_id, http_client)

    # Persist scan_event
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO scan_event (
                scan_id, scanner_user_id, garment_id, occurred_at,
                resolved_scope, policy_version, region_code, shown_facets
                scan_id, scanner_user_id, garment_id, resolved_scope,
                policy_version, region_code, occurred_at, shown_facets
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (scan_id) DO NOTHING
            """,
            scan_id,
            scanner_user_id,
            garment_id,
            occurred_at,
            resolved_scope,
            policy_version,
            region_code,
            str(shown_facets),
        )

    tx_hashes = call_tx_builder(garment_id, shown_facets, resolved_scope)

            resolved_scope,
            policy_version,
            region_code,
            occurred_at,
            str(shown_facets),  # Convert to JSON string for JSONB
        )

    # Build blockchain tx hashes
    tx_hashes = call_tx_builder(garment_id, shown_facets, resolved_scope)

    # Persist chain_anchor
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chain_anchor (
                scan_id, cardano_tx_hash, midnight_tx_hash, crosschain_root_hash, anchored_at
            ) VALUES ($1, $2, $3, $4, NOW())
                scan_id, cardano_tx_hash, midnight_tx_hash, crosschain_root_hash
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (scan_id) DO NOTHING
            """,
            scan_id,
            tx_hashes["cardano_tx_hash"],
            tx_hashes["midnight_tx_hash"],
            tx_hashes["crosschain_root_hash"],
        )

    # Audit log
    await call_compliance_audit_log(
        scan_id,
        f"policy allowed scope {resolved_scope}",
        {"policy_version": policy_version, "region_code": region_code},
        "scan_committed",
        {
            "garment_id": garment_id,
            "resolved_scope": resolved_scope,
            "region_code": region_code,
            "shown_facets_count": len(shown_facets),
        },
        risk_flagged=False,
        escalated_to_human=False,
        request_id=request_id,
        http_client=http_client,
    )

    await call_compliance_anchor_chain(scan_id, tx_hashes, request_id, http_client)

    logger.info({
        "event": "scan_committed",
        "scan_id": scan_id,
        "scanner_user": redact_user_id(scanner_user_id),
        "garment_partial": truncate_id(garment_id),
        "region_code": region_code,
        "shown_facets_count": len(shown_facets),
        "request_id": request_id,
    })
    # Record anchor chain in compliance
    await call_compliance_anchor_chain(scan_id, tx_hashes, request_id, http_client)

    logger.info(
        {
            "event": "scan_processed",
            "scan_id": scan_id,
            "scanner_user": redact_user_id(scanner_user_id),
            "garment_partial": truncate_id(garment_id),
            "shown_facets_count": len(shown_facets),
            "request_id": request_id,
        }
    )

    return {
        "status": "ok",
        "scan_id": scan_id,
        "shown_facets_count": len(shown_facets),
        "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
        "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
        "crosschain_root_hash": tx_hashes["crosschain_root_hash"],
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db_pool = await asyncpg.create_pool(
        host="postgres",
        port=5432,
        database="brandme",
        user="postgres",
        password="postgres",
        min_size=5,
        max_size=20,
    )
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "orchestrator_service_started"})
    yield
    # Shutdown
    await app.state.db_pool.close()
    await app.state.http_client.aclose()
    logger.info({"event": "orchestrator_service_stopped"})


app = FastAPI(lifespan=lifespan)


@app.post("/scan/commit")
async def scan_commit(payload: OrchestratorScanPacket, request: Request):
    """
    Commit allowed scan: persist, anchor, audit.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    decision_packet = payload.dict()

    result = await process_allowed_scan(
        decision_packet,
        request_id,
        app.state.db_pool,
        app.state.http_client,
    )
    try:
        result = await process_allowed_scan(
            decision_packet,
            request_id,
            app.state.db_pool,
            app.state.http_client,
        )
    except Exception as e:
        logger.error(
            {
                "event": "scan_commit_failed",
                "scan_id": payload.scan_id,
                "error": str(e),
                "request_id": request_id,
            }
        )
        response = JSONResponse(content={"error": "internal_error"}, status_code=500)
        ensure_request_id(request, response)
        return response

    response = JSONResponse(content=result)
    request_id = ensure_request_id(request, response)

    return response


    logger.info(
        {
            "event": "scan_committed",
            "scan_id": payload.scan_id,
            "scanner_user": redact_user_id(payload.scanner_user_id),
            "garment_partial": truncate_id(payload.garment_id),
            "region_code": payload.region_code,
            "shown_facets_count": result["shown_facets_count"],
            "request_id": request_id,
        }
    )

    return response


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
