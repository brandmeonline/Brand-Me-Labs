"""
Brand.Me v8 — Global Integrity Spine
Cube Service: Port 8007 - Product Cube storage and serving

This service stores and serves Product Cube data (6 faces per garment).
CRITICAL: Every face access is policy-gated. Never return face without policy check.

v8: Uses Spanner for persistence, Firestore for real-time state
"""

from contextlib import asynccontextmanager
import os
from typing import Optional
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx

# Import shared Brand.Me utilities (from brandme_core/)
from brandme_core.logging import get_logger, ensure_request_id, redact_user_id, truncate_id
from brandme_core.health import create_health_router, HealthChecker
from brandme_core.metrics import get_metrics_collector
from brandme_core.telemetry import setup_telemetry
from brandme_core.spanner.pool import create_pool_manager
from brandme_core.cors_config import get_cors_config

# Local imports
from .api import cubes, faces
from .service import CubeService
from .clients import (
    PolicyClient,
    ComplianceClient,
    OrchestratorClient,
    IdentityClient
)

logger = get_logger("cube")
metrics = get_metrics_collector("cube")

# Environment variables for Spanner (v8)
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")

# Global resources (initialized in lifespan)
spanner_pool = None
http_client: Optional[httpx.AsyncClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for Spanner pool and HTTP client.
    v8: Uses Spanner instead of PostgreSQL.
    """
    global spanner_pool, http_client

    logger.info("cube_service_starting", port=8007)

    try:
        # Initialize Spanner pool (v8)
        spanner_pool = create_pool_manager(
            project_id=SPANNER_PROJECT,
            instance_id=SPANNER_INSTANCE,
            database_id=SPANNER_DATABASE
        )
        await spanner_pool.initialize()
        logger.info("spanner_pool_created", database="spanner")

        # Initialize HTTP client for service-to-service calls
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        logger.info("http_client_created")

        # Initialize service clients
        app.state.policy_client = PolicyClient(
            base_url=os.getenv("POLICY_URL", "http://policy:8001"),
            http_client=http_client
        )

        app.state.compliance_client = ComplianceClient(
            base_url=os.getenv("COMPLIANCE_URL", "http://compliance:8004"),
            http_client=http_client
        )

        app.state.orchestrator_client = OrchestratorClient(
            base_url=os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8002"),
            http_client=http_client
        )

        app.state.identity_client = IdentityClient(
            base_url=os.getenv("IDENTITY_URL", "http://identity:8005"),
            http_client=http_client
        )

        # Initialize cube service (v8: uses spanner_pool)
        app.state.cube_service = CubeService(
            spanner_pool=spanner_pool,
            policy_client=app.state.policy_client,
            compliance_client=app.state.compliance_client,
            orchestrator_client=app.state.orchestrator_client,
            identity_client=app.state.identity_client,
            metrics=metrics
        )

        logger.info("cube_service_initialized", database="spanner")

        yield

    finally:
        # Cleanup
        if http_client:
            await http_client.aclose()
            logger.info("http_client_closed")

        if spanner_pool:
            await spanner_pool.close()
            logger.info("spanner_pool_closed")

        logger.info("cube_service_stopped")

# Create FastAPI application
app = FastAPI(
    title="Brand.Me Cube Service",
    description="Product Cube storage and serving with Integrity Spine (v8)",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware - use centralized configuration
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    **cors_config
)

# Request ID middleware (ensure X-Request-Id propagation)
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Ensure X-Request-Id is present and propagate it"""
    request_id = ensure_request_id(request)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response

# Health checks (v8: uses spanner_pool)
health_checker = HealthChecker("cube")
health_checker.add_check("spanner", lambda: spanner_pool is not None)
health_checker.add_check("http_client", lambda: http_client is not None)
app.include_router(create_health_router(health_checker))

# API routes
app.include_router(cubes.router, prefix="/cubes", tags=["cubes"])
app.include_router(faces.router, prefix="/cubes", tags=["faces"])

# Metrics endpoint (Prometheus)
@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Setup OpenTelemetry tracing
setup_telemetry("cube", app)

# Root endpoint
@app.get("/")
async def root():
    return {
        "service": "cube",
        "version": "1.0.0",
        "description": "Product Cube storage and serving",
        "port": 8007
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8007,
        log_config=None  # Use our custom logging
    )
