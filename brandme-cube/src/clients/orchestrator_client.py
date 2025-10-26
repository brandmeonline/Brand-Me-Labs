"""Orchestrator Service Client"""

import httpx
from typing import Dict, Any
from brandme_core.logging import get_logger

logger = get_logger("cube.orchestrator_client")

class OrchestratorClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient):
        self.base_url = base_url
        self.client = http_client

    async def execute_transfer_ownership(
        self,
        cube_id: str,
        from_owner_id: str,
        to_owner_id: str,
        transfer_method: str,
        price: float = None,
        request_id: str = None
    ) -> Dict[str, Any]:
        """Execute ownership transfer workflow"""
        try:
            response = await self.client.post(
                f"{self.base_url}/execute/transfer_ownership",
                json={
                    "cube_id": cube_id,
                    "from_owner_id": from_owner_id,
                    "to_owner_id": to_owner_id,
                    "transfer_method": transfer_method,
                    "price": price
                },
                headers={"X-Request-Id": request_id} if request_id else {},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Orchestrator returned {response.status_code}")

        except Exception as e:
            logger.error(
                "orchestrator_transfer_failed",
                error=str(e),
                request_id=request_id
            )
            raise
