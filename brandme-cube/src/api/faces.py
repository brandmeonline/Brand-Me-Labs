"""Face API Endpoints"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from ..models import FaceName
from brandme_core.logging import get_logger

router = APIRouter()
logger = get_logger("cube.api.faces")

@router.get("/{cube_id}/faces/{face_name}")
async def get_face(
    cube_id: str,
    face_name: str,
    request: Request
):
    """
    Get single face with policy check

    Returns 200 with status="visible" if allowed
    Returns 200 with status="escalated_pending_human" if escalated
    Returns 403 if denied
    """
    viewer_id = request.state.get("user_id", "anonymous")
    request_id = request.state.request_id
    cube_service = request.app.state.cube_service

    # Validate face_name
    try:
        face_enum = FaceName(face_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid face name: {face_name}")

    try:
        face = await cube_service.get_face(cube_id, face_enum, viewer_id, request_id)
        return face
    except HTTPException as e:
        if e.status_code == 403:
            # Denied
            return JSONResponse(
                status_code=403,
                content={
                    "error": "access_denied",
                    "message": f"You do not have permission to view {face_name}"
                }
            )
        raise
