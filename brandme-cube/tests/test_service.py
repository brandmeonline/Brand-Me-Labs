"""Unit tests for CubeService"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.service import CubeService
from src.models import PolicyDecision, FaceName

@pytest.mark.asyncio
async def test_get_cube_with_policy_allow():
    """Test cube retrieval when policy allows all faces"""
    # Mock dependencies
    mock_db = AsyncMock()
    mock_policy = Mock()
    mock_policy.can_view_face = AsyncMock(return_value=PolicyDecision.ALLOW)
    mock_compliance = Mock()
    mock_compliance.log_event = AsyncMock(return_value={})
    mock_orchestrator = Mock()
    mock_identity = Mock()
    mock_metrics = Mock()
    mock_metrics.increment_counter = Mock()

    # Create service
    service = CubeService(
        db_pool=mock_db,
        policy_client=mock_policy,
        compliance_client=mock_compliance,
        orchestrator_client=mock_orchestrator,
        identity_client=mock_identity,
        metrics=mock_metrics
    )

    # Mock database response
    service._fetch_cube_from_db = AsyncMock(return_value={
        "cube_id": "test_cube_123",
        "owner_id": "owner_456",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "faces": {
            "product_details": {"data": {"name": "Test Product"}},
            "provenance": {"data": {}},
            "ownership": {"data": {}},
            "social_layer": {"data": {}},
            "esg_impact": {"data": {}},
            "lifecycle": {"data": {}}
        },
        "visibility_settings": {
            "product_details": "public",
            "provenance": "public",
            "ownership": "private",
            "social_layer": "public",
            "esg_impact": "public",
            "lifecycle": "authenticated"
        }
    })

    # Test
    cube = await service.get_cube("test_cube_123", "viewer_789", "req_001")

    # Assertions
    assert cube.cube_id == "test_cube_123"
    assert len(cube.faces) > 0
    # Policy should be called for each face
    assert mock_policy.can_view_face.call_count == 6
