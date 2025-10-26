import datetime as dt
import hashlib
import json
import uuid
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id

logger = get_logger("compliance_service")

pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(
        host="postgres",
        port=5432,
        database="brandme",
        user="brandme_user",
        password="brandme_pass",
        min_size=2,
        max_size=10,
    )
    logger.info({"event": "compliance_startup", "pool_ready": True})

    # Create audit_log table if not exists
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                scan_id TEXT NOT NULL,
                decision_summary TEXT NOT NULL,
                decision_detail JSONB NOT NULL,
                risk_flagged BOOLEAN DEFAULT FALSE,
                escalated_to_human BOOLEAN DEFAULT FALSE,
                human_approver_id TEXT,
                entry_hash TEXT NOT NULL,
                prev_hash TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chain_anchor (
                id SERIAL PRIMARY KEY,
                scan_id TEXT NOT NULL UNIQUE,
                cardano_tx_hash TEXT,
                midnight_tx_hash TEXT,
                crosschain_root_hash TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

    yield
    await pool.close()
    logger.info({"event": "compliance_shutdown"})


app = FastAPI(lifespan=lifespan)


class AuditLogRequest(BaseModel):
    scan_id: str
    decision_summary: str
    decision_detail: dict
    risk_flagged: bool
    escalated_to_human: bool


class AnchorChainRequest(BaseModel):
    scan_id: str
    cardano_tx_hash: str
    midnight_tx_hash: str
    crosschain_root_hash: str


class EscalationRequest(BaseModel):
    scan_id: str
    region_code: str
    reason: str
    requires_human_approval: bool


@app.post("/audit/log")
async def audit_log(payload: AuditLogRequest, request: Request):
    """
    Log audit event with SHA256 chaining.
    """
    async with pool.acquire() as conn:
        # Get previous hash for this scan_id
        prev_row = await conn.fetchrow(
            "SELECT entry_hash FROM audit_log WHERE scan_id = $1 ORDER BY created_at DESC LIMIT 1",
            payload.scan_id
        )
        prev_hash = prev_row["entry_hash"] if prev_row else ""

        # Compute current entry hash
        timestamp = dt.datetime.utcnow().isoformat() + "Z"
        hash_input = prev_hash + payload.decision_summary + json.dumps(payload.decision_detail, sort_keys=True) + timestamp
        entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Insert
        await conn.execute(
            """
            INSERT INTO audit_log (scan_id, decision_summary, decision_detail, risk_flagged, escalated_to_human, entry_hash, prev_hash, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            """,
            payload.scan_id,
            payload.decision_summary,
            payload.decision_detail,
            payload.risk_flagged,
            payload.escalated_to_human,
            entry_hash,
            prev_hash
        )

    # Build response
    response = JSONResponse({"status": "logged"})

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log
    logger.info({
        "event": "audit_log_entry",
        "scan_id": payload.scan_id,
        "risk_flagged": payload.risk_flagged,
        "escalated_to_human": payload.escalated_to_human,
        "entry_hash": entry_hash,
        "request_id": request_id
    })

    return response


@app.post("/audit/anchorChain")
async def anchor_chain(payload: AnchorChainRequest, request: Request):
    """
    Record chain anchor hashes for a scan.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chain_anchor (scan_id, cardano_tx_hash, midnight_tx_hash, crosschain_root_hash, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (scan_id) DO UPDATE SET
                cardano_tx_hash = EXCLUDED.cardano_tx_hash,
                midnight_tx_hash = EXCLUDED.midnight_tx_hash,
                crosschain_root_hash = EXCLUDED.crosschain_root_hash
            """,
            payload.scan_id,
            payload.cardano_tx_hash,
            payload.midnight_tx_hash,
            payload.crosschain_root_hash
        )

    # Build response
    response = JSONResponse({"status": "ok"})

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log (DO NOT log raw Midnight payloads, just tx hashes)
    logger.info({
        "event": "chain_anchor_recorded",
        "scan_id": payload.scan_id,
        "cardano_tx_hash": payload.cardano_tx_hash,
        "midnight_tx_hash": payload.midnight_tx_hash,
        "crosschain_root_hash": payload.crosschain_root_hash,
        "request_id": request_id
    })

    return response


@app.get("/audit/{scan_id}/explain")
async def audit_explain(scan_id: str, request: Request):
    """
    Explain audit trail for a scan.
    JOIN scan_event and chain_anchor.
    Return ONLY: scan_id, occurred_at, region_code, policy_version, resolved_scope,
                 shown_facets_count, cardano_tx_hash, midnight_tx_hash, crosschain_root_hash
    DO NOT return facets, purchase history, or owner lineage.
    """
    async with pool.acquire() as conn:
        # Get latest audit_log entry for this scan
        audit_row = await conn.fetchrow(
            """
            SELECT decision_detail, created_at
            FROM audit_log
            WHERE scan_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            scan_id
        )

        # Get chain_anchor
        chain_row = await conn.fetchrow(
            "SELECT cardano_tx_hash, midnight_tx_hash, crosschain_root_hash FROM chain_anchor WHERE scan_id = $1",
            scan_id
        )

        if not audit_row:
            response = JSONResponse({"error": "scan_id not found"}, status_code=404)
            request_id = ensure_request_id(request, response)
            return response

        decision_detail = audit_row["decision_detail"]
        occurred_at = decision_detail.get("occurred_at", audit_row["created_at"].isoformat() + "Z")
        region_code = decision_detail.get("region_code", "unknown")
        policy_version = decision_detail.get("policy_version", "unknown")
        resolved_scope = decision_detail.get("resolved_scope", "unknown")
        shown_facets_count = decision_detail.get("shown_facets_count", 0)

        result = {
            "scan_id": scan_id,
            "occurred_at": occurred_at,
            "region_code": region_code,
            "policy_version": policy_version,
            "resolved_scope": resolved_scope,
            "shown_facets_count": shown_facets_count,
            "cardano_tx_hash": chain_row["cardano_tx_hash"] if chain_row else None,
            "midnight_tx_hash": chain_row["midnight_tx_hash"] if chain_row else None,
            "crosschain_root_hash": chain_row["crosschain_root_hash"] if chain_row else None
        }

    # Build response
    response = JSONResponse(result)

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log
    logger.info({
        "event": "audit_explain",
        "scan_id": scan_id,
        "region_code": region_code,
        "shown_facets_count": shown_facets_count,
        "request_id": request_id
    })

    return response


@app.post("/audit/escalate")
async def audit_escalate(payload: EscalationRequest, request: Request):
    """
    Record an escalation request.
    INSERT INTO audit_log with escalated_to_human=True, risk_flagged=True.
    This will be consumed by governance_console.
    """
    decision_detail = {
        "scan_id": payload.scan_id,
        "region_code": payload.region_code,
        "reason": payload.reason,
        "requires_human_approval": payload.requires_human_approval
    }

    async with pool.acquire() as conn:
        # Get previous hash
        prev_row = await conn.fetchrow(
            "SELECT entry_hash FROM audit_log WHERE scan_id = $1 ORDER BY created_at DESC LIMIT 1",
            payload.scan_id
        )
        prev_hash = prev_row["entry_hash"] if prev_row else ""

        # Compute entry hash
        timestamp = dt.datetime.utcnow().isoformat() + "Z"
        hash_input = prev_hash + "escalation_request" + json.dumps(decision_detail, sort_keys=True) + timestamp
        entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Insert escalation
        await conn.execute(
            """
            INSERT INTO audit_log (scan_id, decision_summary, decision_detail, risk_flagged, escalated_to_human, entry_hash, prev_hash, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            """,
            payload.scan_id,
            "escalation_request",
            decision_detail,
            True,
            True,
            entry_hash,
            prev_hash
        )

    # Build response
    response = JSONResponse({"status": "queued"})

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log
    logger.info({
        "event": "escalation_queued",
        "scan_id": payload.scan_id,
        "region_code": payload.region_code,
        "reason": payload.reason,
        "request_id": request_id
    })

    return response
