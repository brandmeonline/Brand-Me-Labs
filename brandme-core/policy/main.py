from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core.logging import ensure_request_id, get_logger, redact_user_id
from consent_rules import get_scope
from region_rules import is_allowed


class PolicyCheckRequest(BaseModel):
    scanner_user_id: str
    garment_id: str
    region_code: str
    action: str


app = FastAPI()
logger = get_logger(__name__)
POLICY_VERSION = "policy_v1_us-east1"


@app.post("/policy/check")
async def policy_check(request: Request, payload: PolicyCheckRequest) -> JSONResponse:
    scope = get_scope(payload.scanner_user_id, payload.garment_id)
    allowed = is_allowed(payload.region_code, scope)

    if allowed is True:
        decision = "allow"
    elif allowed is False:
        decision = "deny"
    else:
        decision = "escalate"

    result = {
        "decision": decision,
        "resolved_scope": scope,
        "policy_version": POLICY_VERSION,
    }

    response = JSONResponse(result)
    request_id = ensure_request_id(request, response)

    logger.info(
        "Policy check completed",
        extra={
            "scanner_user_id": redact_user_id(payload.scanner_user_id),
            "decision": decision,
            "resolved_scope": scope,
            "region_code": payload.region_code,
            "request_id": request_id,
        },
    )

    if decision == "escalate":
        # TODO: if decision == "escalate", enqueue this event for human governance review
        pass

    # TODO: integrate real consent policy graph from DB
    # TODO: integrate per-region legal rules (GDPR-style)

    return response
