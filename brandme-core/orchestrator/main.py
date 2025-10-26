# Brand.Me v7 — Orchestrator HTTP API
# HTTP wrapper for Celery-based orchestrator tasks
# brandme-core/orchestrator/main.py

import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id

logger = get_logger("orchestrator_api")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")


class TransferOwnershipRequest(BaseModel):
    cube_id: str
    from_owner_id: str
    to_owner_id: str
    transfer_method: str
    price: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info({"event": "orchestrator_api_started"})
    yield
    logger.info({"event": "orchestrator_api_stopped"})


app = FastAPI(lifespan=lifespan)

# Enable CORS
from brandme_core.cors_config import get_cors_config
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    **cors_config
)


@app.post("/execute/transfer_ownership")
async def execute_transfer_ownership(payload: TransferOwnershipRequest, request: Request):
    """
    Execute ownership transfer workflow for Product Cube.

    This endpoint orchestrates:
    1. Update ownership record in database
    2. Create blockchain transaction
    3. Log to compliance audit trail
    4. Return transaction details

    For v6, we provide a simplified synchronous implementation.
    In production, this would trigger Celery tasks for async processing.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    transfer_id = str(uuid4())
    blockchain_tx_hash = f"cardano_tx_{transfer_id[:16]}"  # Stub for v6

    logger.info({
        "event": "ownership_transfer_executed",
        "transfer_id": transfer_id,
        "cube_id": truncate_id(payload.cube_id),
        "from_owner": redact_user_id(payload.from_owner_id),
        "to_owner": redact_user_id(payload.to_owner_id),
        "transfer_method": payload.transfer_method,
        "price": payload.price,
        "request_id": request_id,
    })

    # Return transfer result
    result = {
        "transfer_id": transfer_id,
        "blockchain_tx_hash": blockchain_tx_hash,
        "new_owner_id": payload.to_owner_id,
        "ownership_face": {
            "current_owner": {
                "user_id": payload.to_owner_id,
                "acquired_at": datetime.utcnow().isoformat(),
                "transfer_method": payload.transfer_method,
                "price_paid": payload.price,
            },
            "transfer_history": [
                {
                    "from": payload.from_owner_id,
                    "to": payload.to_owner_id,
                    "transfer_id": transfer_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "method": payload.transfer_method,
                    "price": payload.price,
                    "blockchain_tx": blockchain_tx_hash,
                }
            ],
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

    resp = JSONResponse(content=result)
    ensure_request_id(request, resp)
    return resp


@app.get("/health")
async def health():
    """Health check endpoint."""
    return JSONResponse(content={"status": "ok", "service": "orchestrator_api"})
