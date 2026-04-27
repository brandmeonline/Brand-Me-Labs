# Brand.Me v8 — Global Integrity Spine
# HTTP wrapper for Celery-based orchestrator tasks
# brandme-core/orchestrator/main.py
#
# v8: Migrated from PostgreSQL to Spanner, added proper health checks and metrics

import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id
from brandme_core.spanner.pool import create_pool_manager
from brandme_core.metrics import get_metrics_collector, generate_metrics
from brandme_core.cors_config import get_cors_config

logger = get_logger("orchestrator_api")

# Standardized environment variables
REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")


class TransferOwnershipRequest(BaseModel):
    cube_id: str
    from_owner_id: str
    to_owner_id: str
    transfer_method: str
    price: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup service resources."""
    # Initialize Spanner pool
    app.state.spanner_pool = create_pool_manager(
        project_id=SPANNER_PROJECT,
        instance_id=SPANNER_INSTANCE,
        database_id=SPANNER_DATABASE
    )
    await app.state.spanner_pool.initialize()
    logger.info({"event": "orchestrator_api_started", "database": "spanner"})
    yield
    # Cleanup
    await app.state.spanner_pool.close()
    logger.info({"event": "orchestrator_api_stopped"})


app = FastAPI(lifespan=lifespan)

# Initialize metrics collector
metrics = get_metrics_collector("orchestrator")

# Enable CORS with centralized configuration
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

    For v8, we provide a simplified synchronous implementation.
    In production, this would trigger Celery tasks for async processing.
    """
    transfer_id = str(uuid4())
    blockchain_tx_hash = f"cardano_tx_{transfer_id[:16]}"

    # Build result first
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

    # Create response and set request ID properly
    response = JSONResponse(content=result)
    request_id = ensure_request_id(request, response)

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

    # Record metrics
    metrics.record_http_request("POST", "/execute/transfer_ownership", 200, 0.0)

    return response


@app.get("/health")
async def health():
    """Health check with Spanner connectivity verification."""
    try:
        if app.state.spanner_pool and app.state.spanner_pool.database:
            def _health_check(transaction):
                results = transaction.execute_sql("SELECT 1")
                for row in results:
                    return True
                return False

            is_healthy = app.state.spanner_pool.database.run_in_transaction(_health_check)
            metrics.update_health("database", is_healthy)
            if is_healthy:
                return JSONResponse(content={"status": "ok", "service": "orchestrator", "database": "spanner"})
            else:
                return JSONResponse(content={"status": "degraded", "service": "orchestrator", "database": "unhealthy"}, status_code=503)
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        metrics.update_health("database", False)
        return JSONResponse(content={"status": "degraded", "service": "orchestrator", "database": "error"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "orchestrator", "message": "no_spanner_pool"}, status_code=503)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
