"""Policy Service Client"""

import httpx
from brandme_core.logging import get_logger

logger = get_logger("cube.policy_client")

class PolicyClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient):
        self.base_url = base_url
        self.client = http_client

    async def can_view_face(
        self,
        viewer_id: str,
        owner_id: str,
        cube_id: str,
        face_name: str,
        request_id: str
    ) -> str:
        """
        Call Policy service to check if viewer can see face
        Returns: "allow", "escalate", or "deny"
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/policy/canViewFace",
                json={
                    "viewer_id": viewer_id,
                    "owner_id": owner_id,
                    "cube_id": cube_id,
                    "face_name": face_name
                },
                headers={"X-Request-Id": request_id},
                timeout=5.0
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("decision", "escalate")
            else:
                # Fail-safe: If policy is down, escalate
                logger.error(
                    "policy_service_error",
                    status=response.status_code,
                    request_id=request_id
                )
                return "escalate"

        except Exception as e:
            logger.error(
                "policy_service_unreachable",
                error=str(e),
                request_id=request_id
            )
            return "escalate"

    async def can_transfer_ownership(
        self,
        from_owner_id: str,
        to_owner_id: str,
        cube_id: str,
        price: float = None,
        request_id: str = None
    ) -> str:
        """Call Policy for ownership transfer check"""
        try:
            response = await self.client.post(
                f"{self.base_url}/policy/canTransferOwnership",
                json={
                    "from_owner_id": from_owner_id,
                    "to_owner_id": to_owner_id,
                    "cube_id": cube_id,
                    "price": price
                },
                headers={"X-Request-Id": request_id} if request_id else {},
                timeout=5.0
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("decision", "escalate")
            else:
                return "escalate"

        except Exception:
            return "escalate"
