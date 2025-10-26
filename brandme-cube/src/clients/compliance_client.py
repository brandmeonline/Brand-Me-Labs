"""Compliance Service Client"""

import httpx
from typing import Dict, Any, Optional
from brandme_core.logging import get_logger

logger = get_logger("cube.compliance_client")

class ComplianceClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient):
        self.base_url = base_url
        self.client = http_client

    async def log_event(
        self,
        cube_id: str,
        face_name: str,
        action: str,
        actor_id: str,
        policy_decision: str,
        context: Optional[Dict] = None,
        request_id: str = None
    ) -> Dict[str, Any]:
        """Log event to Compliance audit trail"""
        try:
            response = await self.client.post(
                f"{self.base_url}/audit/log",
                json={
                    "cube_id": cube_id,
                    "face_name": face_name,
                    "action": action,
                    "actor_id": actor_id,
                    "policy_decision": policy_decision,
                    "context": context or {}
                },
                headers={"X-Request-Id": request_id} if request_id else {},
                timeout=5.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    "compliance_log_failed",
                    status=response.status_code,
                    request_id=request_id
                )
                return {"error": "log_failed"}

        except Exception as e:
            logger.error(
                "compliance_unreachable",
                error=str(e),
                request_id=request_id
            )
            return {"error": str(e)}

    async def escalate(
        self,
        cube_id: str,
        face_name: str,
        actor_id: str,
        reason: str,
        request_id: str = None
    ) -> Dict[str, Any]:
        """Register escalation with Compliance"""
        try:
            response = await self.client.post(
                f"{self.base_url}/audit/escalate",
                json={
                    "cube_id": cube_id,
                    "face_name": face_name,
                    "actor_id": actor_id,
                    "reason": reason,
                    "escalated_to_human": True
                },
                headers={"X-Request-Id": request_id} if request_id else {},
                timeout=5.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    "escalation_failed",
                    status=response.status_code,
                    request_id=request_id
                )
                return {"escalation_id": None}

        except Exception as e:
            logger.error(
                "escalation_unreachable",
                error=str(e),
                request_id=request_id
            )
            return {"escalation_id": None}
