"""Cube API Endpoints"""

from fastapi import APIRouter, Depends, Request, HTTPException
from ..models import ProductCube, CreateCubeRequest, TransferOwnershipRequest
from brandme_core.logging import get_logger

router = APIRouter()
logger = get_logger("cube.api.cubes")

@router.get("/{cube_id}")
async def get_cube(cube_id: str, request: Request):
    """
    Get full cube with policy-filtered faces

    CRITICAL: cube_service.get_cube() calls policy for EACH face
    """
    # Extract user_id from request (auth middleware sets this)
    viewer_id = request.state.get("user_id", "anonymous")
    request_id = request.state.request_id

    cube_service = request.app.state.cube_service
    cube = await cube_service.get_cube(cube_id, viewer_id, request_id)
    return cube

@router.post("/{cube_id}/transferOwnership")
async def transfer_ownership(
    cube_id: str,
    request_body: TransferOwnershipRequest,
    request: Request
):
    """
    Transfer ownership with Integrity Spine:
    Policy → Compliance → Governance (if escalated) → Orchestrator → Blockchain
    """
    requester_id = request.state.get("user_id")
    if not requester_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    request_id = request.state.request_id
    cube_service = request.app.state.cube_service

    result = await cube_service.transfer_ownership(
        cube_id,
        request_body,
        requester_id,
        request_id
    )
    return result

@router.get("/search")
async def search_cubes(
    brand: str = None,
    style: str = None,
    min_sustainability_score: float = None,
    request: Request = None
):
    """Search cubes (policy-filtered)"""
    # TODO: Implement search with policy filtering
    return {"message": "Search endpoint - implementation pending"}
