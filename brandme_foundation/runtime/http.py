"""Correlation IDs and secret-safe structured request logging."""

from __future__ import annotations

import os
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from brandme_foundation.observability import _emit

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RuntimeRequestMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, role: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._role = role

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-correlation-id", "")
        request_id = supplied if _SAFE_ID.fullmatch(supplied) else str(uuid.uuid4())
        token = correlation_id.set(request_id)
        started = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-correlation-id"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", None)
            _emit({
                "event": "http.request.complete",
                "runtime_role": self._role,
                "correlation_id": request_id,
                "method": request.method,
                "path": route_template or "unmatched_route",
                "status_code": status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "revision": os.environ.get("K_REVISION", os.environ.get("GIT_SHA", "local")),
            })
            correlation_id.reset(token)
