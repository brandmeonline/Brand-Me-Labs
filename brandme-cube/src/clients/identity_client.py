"""Identity Service Client"""

import httpx
from typing import Dict, Any
from brandme_core.logging import get_logger

logger = get_logger("cube.identity_client")

class IdentityClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient):
        self.base_url = base_url
        self.client = http_client

    async def get_user_context(
        self,
        user_id: str,
        request_id: str = None
    ) -> Dict[str, Any]:
        """Get user context for policy decisions"""
        try:
            response = await self.client.get(
                f"{self.base_url}/user/{user_id}/context",
                headers={"X-Request-Id": request_id} if request_id else {},
                timeout=5.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {}

        except Exception as e:
            logger.error(
                "identity_unreachable",
                error=str(e),
                request_id=request_id
            )
            return {}
