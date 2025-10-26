# brandme-agents/compliance/src/main.py

import hashlib
import json
import uuid
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncpg

from brandme_core.logging import get_logger, ensure_request_id

logger = get_logger("compliance_service")


class AuditLogRequest(BaseModel):
    scan_id: str
    decision_summary: str
    decision_detail: dict
    risk_flagged: bool
    escalated_to_human: bool
    human_approver_id: Optional[str] = None


class AnchorChainRequest(BaseModel):
    scan_id: str
    cardano_tx_hash: str
    midnight_tx_hash: str
    crosschain_root_hash: str


class EscalateRequest(BaseModel):
    scan_id: str
    region_code: str
    reason: str
    requires_human_approval: bool


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
    logger.info({"event": "compliance_service_started"})
    yield
    # Shutdown
    await app.state.db_pool.close()
    logger.info({"event": "compliance_service_stopped"})


app = FastAPI(lifespan=lifespan)


@app.post("/audit/log")
async def audit_log(payload: AuditLogRequest, request: Request):
    """
    Log audit entry with hash-chaining for integrity.
    """
    async with app.state.db_pool.acquire() as conn:
        # Get previous hash for this scan_id
        prev_row = await conn.fetchrow(
            """
            SELECT entry_hash FROM audit_log
            WHERE related_scan_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            payload.scan_id,
        )
        prev_hash = prev_row["entry_hash"] if prev_row else ""

        # Compute entry hash
        hash_input = (
            prev_hash + payload.decision_summary + json.dumps(payload.decision_detail)
        )
        entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Insert audit entry
        await conn.execute(
            """
            INSERT INTO audit_log (
                audit_id, related_scan_id, created_at, decision_summary,
                decision_detail, risk_flagged, escalated_to_human,
                human_approver_id, prev_hash, entry_hash
            ) VALUES ($1, $2, NOW(), $3, $4::jsonb, $5, $6, $7, $8, $9)
            """,
            str(uuid.uuid4()),
            payload.scan_id,
            payload.decision_summary,
            json.dumps(payload.decision_detail),
            payload.risk_flagged,
            payload.escalated_to_human,
            payload.human_approver_id,
            prev_hash,
            entry_hash,
        )

    response = JSONResponse(content={"status": "logged"})
    request_id = ensure_request_id(request, response)

    logger.info(
        {
            "event": "audit_logged",
            "scan_id": payload.scan_id,
            "risk_flagged": payload.risk_flagged,
            "escalated_to_human": payload.escalated_to_human,
            "request_id": request_id,
        }
    )

    return response


@app.post("/audit/anchorChain")
async def anchor_chain(payload: AnchorChainRequest, request: Request):
    """
    Record blockchain anchor hashes for a scan.
    NEVER log private Midnight payloads, only tx hashes.
    """
    # For now, just acknowledge. In production, persist reconciliation row.

    response = JSONResponse(content={"status": "ok"})
    request_id = ensure_request_id(request, response)

    logger.info(
        {
            "event": "anchor_chain_recorded",
            "scan_id": payload.scan_id,
            "cardano_tx_hash": payload.cardano_tx_hash,
            "midnight_tx_hash": payload.midnight_tx_hash,
            "request_id": request_id,
        }
    )

    return response


@app.post("/audit/escalate")
async def escalate(payload: EscalateRequest, request: Request):
    """
    Queue escalation for human review.
    """
    async with app.state.db_pool.acquire() as conn:
        # Get previous hash (empty for first entry)
        prev_row = await conn.fetchrow(
            """
            SELECT entry_hash FROM audit_log
            WHERE related_scan_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            payload.scan_id,
        )
        prev_hash = prev_row["entry_hash"] if prev_row else ""

        # Compute entry hash
        decision_detail = {"reason": payload.reason, "region_code": payload.region_code}
        hash_input = prev_hash + "escalation_request" + json.dumps(decision_detail)
        entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Insert escalation entry
        await conn.execute(
            """
            INSERT INTO audit_log (
                audit_id, related_scan_id, created_at, decision_summary,
                decision_detail, risk_flagged, escalated_to_human,
                human_approver_id, prev_hash, entry_hash
            ) VALUES ($1, $2, NOW(), $3, $4::jsonb, $5, $6, $7, $8, $9)
            """,
            str(uuid.uuid4()),
            payload.scan_id,
            "escalation_request",
            json.dumps(decision_detail),
            True,
            True,
            None,
            prev_hash,
            entry_hash,
        )

    response = JSONResponse(content={"status": "queued"})
    request_id = ensure_request_id(request, response)

    logger.info(
        {
            "event": "audit_escalated",
            "scan_id": payload.scan_id,
            "region_code": payload.region_code,
            "request_id": request_id,
        }
    )

    return response


@app.get("/audit/{scan_id}/explain")
async def audit_explain(scan_id: str, request: Request):
    """
    Explain audit trail for a scan.
    NEVER return facet bodies or user PII here.
    """
    async with app.state.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                se.scan_id,
                se.occurred_at,
                se.region_code,
                se.policy_version,
                se.resolved_scope,
                jsonb_array_length(se.shown_facets::jsonb) AS shown_facets_count,
                ca.cardano_tx_hash,
                ca.midnight_tx_hash,
                ca.crosschain_root_hash
            FROM scan_event se
            LEFT JOIN chain_anchor ca ON se.scan_id = ca.scan_id
            WHERE se.scan_id = $1
            """,
            scan_id,
        )

    if not row:
        response = JSONResponse(content={"error": "not_found"}, status_code=404)
        ensure_request_id(request, response)
        return response

    body = {
        "scan_id": row["scan_id"],
        "occurred_at": row["occurred_at"].isoformat() + "Z" if row["occurred_at"] else None,
        "region_code": row["region_code"],
        "policy_version": row["policy_version"],
        "resolved_scope": row["resolved_scope"],
        "shown_facets_count": row["shown_facets_count"] or 0,
        "cardano_tx_hash": row["cardano_tx_hash"],
        "midnight_tx_hash": row["midnight_tx_hash"],
        "crosschain_root_hash": row["crosschain_root_hash"],
    }

    response = JSONResponse(content=body)
    request_id = ensure_request_id(request, response)

    logger.info(
        {
            "event": "audit_explain",
            "scan_id": scan_id,
            "region_code": row["region_code"],
            "shown_facets_count": body["shown_facets_count"],
            "request_id": request_id,
        }
    )

    return response


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
