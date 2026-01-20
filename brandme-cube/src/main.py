"""
Brand.Me Cube Service
Port 8007 - Product Cube storage and serving with Integrity Spine

This service stores and serves Product Cube data (6 faces per garment).
CRITICAL: Every face access is policy-gated. Never return face without policy check.
Brand.Me v8 — Global Integrity Spine
Cube Service: Port 8007 - Product Cube storage and serving

This service stores and serves Product Cube data (7 faces per garment).
CRITICAL: Every face access is policy-gated. Never return face without policy check.

v8: Uses Spanner for persistence, Firestore for real-time state
"""

from contextlib import asynccontextmanager
import os
from typing import Optional
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

# Import shared Brand.Me utilities (from brandme_core/)
from brandme_core.logging import get_logger, ensure_request_id, redact_user_id, truncate_id
from brandme_core.metrics import get_metrics_collector
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
from .models import (
    LifecycleTransitionRequest,
    LifecycleTransitionResponse,
    DissolveAuthorizationRequest,
    DissolveAuthorizationResponse,
    BiometricSyncRequest,
    LifecycleState,
    FaceName
)

logger = get_logger("cube")
metrics = get_metrics_collector("cube")

# Global resources (initialized in lifespan)
db_pool: Optional[asyncpg.Pool] = None
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
    Lifespan context manager for database pool and HTTP client.
    Pattern from brandme-core/brain/main.py
    """
    global db_pool, http_client
    Lifespan context manager for Spanner pool and HTTP client.
    v8: Uses Spanner instead of PostgreSQL.
    """
    global spanner_pool, http_client

    logger.info("cube_service_starting", port=8007)

    try:
        # Initialize database pool
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")

        db_pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        logger.info("database_pool_created")
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

        # Initialize cube service
        app.state.cube_service = CubeService(
            db_pool=db_pool,
        # Initialize cube service (v8: uses spanner_pool)
        app.state.cube_service = CubeService(
            spanner_pool=spanner_pool,
            policy_client=app.state.policy_client,
            compliance_client=app.state.compliance_client,
            orchestrator_client=app.state.orchestrator_client,
            identity_client=app.state.identity_client,
            metrics=metrics
        )

        logger.info("cube_service_initialized")
        logger.info({
            "event": "cube_service_initialized",
            "version": "v9",
            "database": "spanner",
            "molecular_data_enabled": ENABLE_MOLECULAR_DATA,
            "ar_sync_enabled": AR_SYNC_ENABLED,
            "ar_sync_latency_target_ms": AR_SYNC_LATENCY_TARGET_MS
        })
        logger.info("cube_service_initialized", database="spanner")

        yield

    finally:
        # Cleanup
        if http_client:
            await http_client.aclose()
            logger.info("http_client_closed")

        if db_pool:
            await db_pool.close()
            logger.info("database_pool_closed")
        if spanner_pool:
            await spanner_pool.close()
            logger.info("spanner_pool_closed")

        logger.info("cube_service_stopped")

# Create FastAPI application
app = FastAPI(
    title="Brand.Me Cube Service",
    description="Product Cube storage and serving with Integrity Spine (v6)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (cube is public-facing like brain, policy, knowledge, governance_console)
    description="Product Cube storage and serving with Integrity Spine (v9 - 2030 Agentic & Circular Economy)",
    version="3.0.0",
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

# Health check endpoints
@app.get("/health")
async def health():
    """Health check endpoint with database verification"""
    if db_pool is None:
        return JSONResponse(
            content={"status": "unhealthy", "service": "cube", "reason": "no_db_pool"},
            status_code=503
        )

    # Try database connection
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse(content={"status": "ok", "service": "cube"})
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        return JSONResponse(
            content={"status": "degraded", "service": "cube", "database": "unhealthy"},
            status_code=503
        )

@app.get("/health/live")
async def liveness():
    """Kubernetes liveness probe"""
    return JSONResponse(content={"status": "alive"})

@app.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe"""
    if db_pool is None or http_client is None:
        return JSONResponse(
            content={"status": "not_ready", "reason": "dependencies_not_initialized"},
            status_code=503
        )
    return JSONResponse(content={"status": "ready"})

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
        "version": "3.0.0",
        "description": "Product Cube storage and serving (v9 - 7 faces, circular economy)",
        "port": 8007,
        "features": {
            "molecular_data": ENABLE_MOLECULAR_DATA,
            "ar_sync": AR_SYNC_ENABLED,
            "ar_sync_latency_target_ms": AR_SYNC_LATENCY_TARGET_MS
        }
    }

        "version": "3.0.0",
        "description": "Product Cube storage and serving (v9 - 7 faces, circular economy)",
        "port": 8007,
        "features": {
            "molecular_data": ENABLE_MOLECULAR_DATA,
            "ar_sync": AR_SYNC_ENABLED,
            "ar_sync_latency_target_ms": AR_SYNC_LATENCY_TARGET_MS
        }
    }


# ===========================================
# v9: LIFECYCLE & CIRCULAR ECONOMY ENDPOINTS
# ===========================================

@app.post("/cubes/{cube_id}/lifecycle/transition")
async def transition_lifecycle(
    cube_id: str,
    req: LifecycleTransitionRequest,
    request: Request
):
    """
    v9: Transition cube lifecycle state.

    Valid transitions:
    - PRODUCED → ACTIVE
    - ACTIVE → REPAIR, DISSOLVE
    - REPAIR → ACTIVE, DISSOLVE
    - DISSOLVE → REPRINT
    - REPRINT → PRODUCED
    """
    request_id = ensure_request_id(request)
    cube_service: CubeService = request.app.state.cube_service

    try:
        # Call compliance service for state machine validation
        result = await cube_service.transition_lifecycle(
            cube_id=cube_id,
            new_state=req.new_state,
            triggered_by=req.triggered_by,
            notes=req.notes,
            esg_verification_required=req.esg_verification_required,
            request_id=request_id
        )

        return JSONResponse(content=result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error({
            "event": "lifecycle_transition_failed",
            "cube_id": cube_id[:8] + "...",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to transition lifecycle")


@app.post("/cubes/{cube_id}/lifecycle/dissolve/authorize")
async def authorize_dissolve(
    cube_id: str,
    req: DissolveAuthorizationRequest,
    request: Request
):
    """
    v9: Authorize dissolve for circular economy.

    Returns an auth key hash that the owner must use to confirm the dissolve.
    After dissolve, materials can be reprinted into new products.
    """
    request_id = ensure_request_id(request)
    cube_service: CubeService = request.app.state.cube_service

    try:
        result = await cube_service.authorize_dissolve(
            cube_id=cube_id,
            owner_id=req.owner_id,
            reason=req.reason,
            target_materials=req.target_materials,
            request_id=request_id
        )

        return JSONResponse(content=result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error({
            "event": "dissolve_authorization_failed",
            "cube_id": cube_id[:8] + "...",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to authorize dissolve")


@app.get("/cubes/{cube_id}/molecular")
async def get_molecular_data(cube_id: str, request: Request):
    """
    v9: Get molecular data face for a cube.

    Returns material composition, lifecycle state, and circular economy tracking.
    """
    if not ENABLE_MOLECULAR_DATA:
        raise HTTPException(
            status_code=503,
            detail="Molecular data feature is disabled"
        )

    request_id = ensure_request_id(request)
    viewer_id = getattr(request.state, "user_id", "anonymous")
    cube_service: CubeService = request.app.state.cube_service

    try:
        face = await cube_service.get_face(
            cube_id=cube_id,
            face_name=FaceName.MOLECULAR_DATA,
            viewer_id=viewer_id,
            request_id=request_id
        )
        return face

    except Exception as e:
        logger.error({
            "event": "molecular_data_fetch_failed",
            "cube_id": cube_id[:8] + "...",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to fetch molecular data")


@app.post("/cubes/{cube_id}/biometric-sync")
async def update_biometric_sync(
    cube_id: str,
    req: BiometricSyncRequest,
    request: Request
):
    """
    v9: Update biometric sync for AR glasses.

    Used to track the latest sync timestamp and latency for the Active Facet.
    Target latency: <100ms for real-time AR display.
    """
    if not AR_SYNC_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="AR sync feature is disabled"
        )

    request_id = ensure_request_id(request)
    cube_service: CubeService = request.app.state.cube_service

    try:
        result = await cube_service.update_biometric_sync(
            cube_id=cube_id,
            device_id=req.device_id,
            sync_timestamp=req.sync_timestamp,
            latency_ms=req.latency_ms,
            request_id=request_id
        )

        # Check if latency is within target
        latency_ok = req.latency_ms <= AR_SYNC_LATENCY_TARGET_MS

        metrics.observe_histogram(
            "ar_sync_latency_ms",
            req.latency_ms,
            {"cube_id_prefix": cube_id[:4]}
        )

        return JSONResponse(content={
            "status": "synced",
            "cube_id": cube_id,
            "device_id": req.device_id,
            "latency_ms": req.latency_ms,
            "latency_target_ms": AR_SYNC_LATENCY_TARGET_MS,
            "latency_within_target": latency_ok
        })

    except Exception as e:
        logger.error({
            "event": "biometric_sync_failed",
            "cube_id": cube_id[:8] + "...",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to update biometric sync")


@app.get("/cubes/{cube_id}/lineage")
async def get_reprint_lineage(cube_id: str, request: Request):
    """
    v9: Get reprint lineage for a cube.

    Traces the ancestry of reprinted products back to their original materials.
    Returns the DerivedFrom chain with burn proof verification.
    """
    request_id = ensure_request_id(request)
    cube_service: CubeService = request.app.state.cube_service

    try:
        lineage = await cube_service.get_reprint_lineage(
            cube_id=cube_id,
            request_id=request_id
        )

        return JSONResponse(content=lineage)

    except Exception as e:
        logger.error({
            "event": "lineage_fetch_failed",
            "cube_id": cube_id[:8] + "...",
            "error": str(e),
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to fetch lineage")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8007,
        log_config=None  # Use our custom logging
    )
