"""
Brand.Me Compliance Service
============================
Tamper-evident audit logging and regulator view with SHA256 hash chaining.

Features:
- Hash-chained audit trail
- Database connection with retries
- Health check endpoints
- Safe JSONB handling for PostgreSQL
"""
import datetime as dt
import hashlib
import json
import uuid
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core import (
    get_logger,
    ensure_request_id,
    config,
    create_db_pool,
    safe_close_pool,
    DatabaseError,
)

logger = get_logger("compliance_service")
pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    try:
        pool = await create_db_pool()
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
        logger.info("Compliance service startup complete")
    except DatabaseError as e:
        logger.error("Database initialization failed", extra={"error": str(e)})
        if not config.ENABLE_STUB_MODE:
            raise

    yield
    await safe_close_pool(pool)
    logger.info("Compliance service shutdown complete")


app = FastAPI(
    title="Brand.Me Compliance Service",
    description="Tamper-evident audit logging and regulator view",
    version="2.0.0",
    lifespan=lifespan
)


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


@app.get("/health")
async def health_check():
    health_status = {"service": "compliance", "status": "healthy", "database": "unknown"}
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["database"] = "healthy"
        except Exception as e:
            health_status["database"] = "unhealthy"
            if not config.ENABLE_STUB_MODE:
                return JSONResponse(health_status, status_code=503)
    return JSONResponse(health_status)


@app.post("/audit/log")
async def audit_log(payload: AuditLogRequest, request: Request):
    if not pool:
        raise HTTPException(503, "Database unavailable")

    try:
        async with pool.acquire() as conn:
            prev_row = await conn.fetchrow(
                "SELECT entry_hash FROM audit_log WHERE scan_id = $1 ORDER BY created_at DESC LIMIT 1",
                payload.scan_id
            )
            prev_hash = prev_row["entry_hash"] if prev_row else ""

            timestamp = dt.datetime.utcnow().isoformat() + "Z"
            hash_input = prev_hash + payload.decision_summary + json.dumps(payload.decision_detail, sort_keys=True) + timestamp
            entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            await conn.execute(
                """
                INSERT INTO audit_log (scan_id, decision_summary, decision_detail, risk_flagged, escalated_to_human, entry_hash, prev_hash)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
                """,
                payload.scan_id,
                payload.decision_summary,
                json.dumps(payload.decision_detail),
                payload.risk_flagged,
                payload.escalated_to_human,
                entry_hash,
                prev_hash
            )

        response = JSONResponse({"status": "logged", "entry_hash": entry_hash})
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "audit_logged",
            "scan_id": payload.scan_id,
            "risk_flagged": payload.risk_flagged,
            "escalated": payload.escalated_to_human,
            "request_id": request_id
        })

        return response

    except Exception as e:
        logger.error("Audit log failed", extra={"error": str(e)})
        raise HTTPException(500, f"Audit log failed: {str(e)}")


@app.post("/audit/anchorChain")
async def anchor_chain(payload: AnchorChainRequest, request: Request):
    if not pool:
        raise HTTPException(503, "Database unavailable")

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chain_anchor (scan_id, cardano_tx_hash, midnight_tx_hash, crosschain_root_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (scan_id) DO UPDATE SET
                    cardano_tx_hash = EXCLUDED.cardano_tx_hash,
                    midnight_tx_hash = EXCLUDED.midnight_tx_hash,
                    crosschain_root_hash = EXCLUDED.crosschain_root_hash
                """,
                payload.scan_id, payload.cardano_tx_hash, payload.midnight_tx_hash, payload.crosschain_root_hash
            )

        response = JSONResponse({"status": "ok"})
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "chain_anchor_recorded",
            "scan_id": payload.scan_id,
            "request_id": request_id
        })

        return response

    except Exception as e:
        logger.error("Chain anchor failed", extra={"error": str(e)})
        raise HTTPException(500, f"Chain anchor failed: {str(e)}")


@app.get("/audit/{scan_id}/explain")
async def audit_explain(scan_id: str, request: Request):
    if not pool:
        raise HTTPException(503, "Database unavailable")

    try:
        async with pool.acquire() as conn:
            audit_row = await conn.fetchrow(
                "SELECT decision_detail, created_at FROM audit_log WHERE scan_id = $1 ORDER BY created_at DESC LIMIT 1",
                scan_id
            )

            if not audit_row:
                raise HTTPException(404, "Scan not found")

            chain_row = await conn.fetchrow(
                "SELECT cardano_tx_hash, midnight_tx_hash, crosschain_root_hash FROM chain_anchor WHERE scan_id = $1",
                scan_id
            )

            decision_detail = audit_row["decision_detail"]
            result = {
                "scan_id": scan_id,
                "occurred_at": decision_detail.get("occurred_at", audit_row["created_at"].isoformat() + "Z"),
                "region_code": decision_detail.get("region_code", "unknown"),
                "policy_version": decision_detail.get("policy_version", "unknown"),
                "resolved_scope": decision_detail.get("resolved_scope", "unknown"),
                "shown_facets_count": decision_detail.get("shown_facets_count", 0),
                "cardano_tx_hash": chain_row["cardano_tx_hash"] if chain_row else None,
                "midnight_tx_hash": chain_row["midnight_tx_hash"] if chain_row else None,
                "crosschain_root_hash": chain_row["crosschain_root_hash"] if chain_row else None
            }

        response = JSONResponse(result)
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "audit_explained",
            "scan_id": scan_id,
            "request_id": request_id
        })

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Audit explain failed", extra={"error": str(e)})
        raise HTTPException(500, f"Audit explain failed: {str(e)}")


@app.post("/audit/escalate")
async def audit_escalate(payload: EscalationRequest, request: Request):
    if not pool:
        raise HTTPException(503, "Database unavailable")

    try:
        decision_detail = {
            "scan_id": payload.scan_id,
            "region_code": payload.region_code,
            "reason": payload.reason,
            "requires_human_approval": payload.requires_human_approval
        }

        async with pool.acquire() as conn:
            prev_row = await conn.fetchrow(
                "SELECT entry_hash FROM audit_log WHERE scan_id = $1 ORDER BY created_at DESC LIMIT 1",
                payload.scan_id
            )
            prev_hash = prev_row["entry_hash"] if prev_row else ""

            timestamp = dt.datetime.utcnow().isoformat() + "Z"
            hash_input = prev_hash + "escalation_request" + json.dumps(decision_detail, sort_keys=True) + timestamp
            entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            await conn.execute(
                """
                INSERT INTO audit_log (scan_id, decision_summary, decision_detail, risk_flagged, escalated_to_human, entry_hash, prev_hash)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
                """,
                payload.scan_id, "escalation_request", json.dumps(decision_detail), True, True, entry_hash, prev_hash
            )

        response = JSONResponse({"status": "queued"})
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "escalation_queued",
            "scan_id": payload.scan_id,
            "region_code": payload.region_code,
            "request_id": request_id
        })

        return response

    except Exception as e:
        logger.error("Escalation failed", extra={"error": str(e)})
        raise HTTPException(500, f"Escalation failed: {str(e)}")
