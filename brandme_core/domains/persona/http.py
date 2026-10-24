"""
Shared FastAPI plumbing for this lane's internal domain routers.

Routers here are UNMOUNTED: the brain service (or the integrator) includes
them and supplies ``resolve_principal(request) -> Principal | None``. The
gateway is the identity boundary (ch.03 §3). How it hands the verified
principal to Python (signed assertion vs relay) is not yet fixed by the
foundation lane (proposal PD-07), so it is injected rather than invented here.
Identity is never read from the body or query.

Every response carries ``X-Request-Id``, ``X-Brandme-Environment`` and
``Cache-Control: private, no-store``. Errors are ``application/problem+json``.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Callable, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from brandme_core.events import EventValidationError

from .kernel import DomainError, Principal, ValidationFailed, problem_body

PrincipalResolver = Callable[[Request], Optional[Principal]]
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    incoming = request.headers.get("x-request-id", "")
    rid = incoming if UUID_RE.match(incoming) else str(uuid.uuid4())
    request.state.request_id = rid
    return rid


def _headers(request: Request, environment: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {"X-Request-Id": request_id(request), "X-Brandme-Environment": environment, "Cache-Control": "private, no-store"}
    if extra:
        h.update(extra)
    return h


def problem(request: Request, err: DomainError, environment: str) -> JSONResponse:
    body = problem_body(err, instance=request.url.path[:256], request_id=request_id(request))
    return JSONResponse(body, status_code=err.status, media_type="application/problem+json", headers=_headers(request, environment))


def _unauthenticated(request: Request, environment: str) -> JSONResponse:
    err = DomainError("A valid session or bearer token is required.", code="unauthenticated")
    err.status = 401
    return problem(request, err, environment)


def _reject_constant(name: str) -> Any:
    # Python's json accepts NaN/Infinity/-Infinity by default; JSON does not.
    raise ValueError(f"non-finite number {name}")


def _parse_json(raw: bytes) -> Any:
    import json

    if not raw:
        return {}
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except ValueError:
        raise ValidationFailed("Request body is not valid JSON (non-finite numbers are not allowed).") from None


async def execute(
    request: Request,
    resolve_principal: PrincipalResolver,
    fn: Callable[..., Any],
    *,
    status: int = 200,
    etag: Optional[Callable[[Any], Optional[str]]] = None,
    with_body: bool = False,
) -> Response:
    """Resolve the principal, run the blocking domain call off the event loop,
    and map domain errors to problem+json. With ``with_body`` the parsed JSON
    body is passed as the second argument."""
    principal = resolve_principal(request)
    environment = principal.environment if principal else "development"
    if principal is None:
        return _unauthenticated(request, environment)
    raw = await request.body() if with_body else b""
    try:
        if with_body:
            body = _parse_json(raw)
            result = await run_in_threadpool(fn, principal, body)
        else:
            result = await run_in_threadpool(fn, principal)
    except DomainError as err:
        return problem(request, err, environment)
    except EventValidationError:
        err = DomainError("The change could not be recorded.", code="event_contract_violation")
        err.status = 500
        return problem(request, err, environment)
    extra = {}
    if etag is not None:
        tag = etag(result)
        if tag is not None:
            extra["ETag"] = f'"{tag}"'
    if status == 204:
        return Response(status_code=204, headers=_headers(request, environment, extra))
    return JSONResponse(result, status_code=status, headers=_headers(request, environment, extra))
