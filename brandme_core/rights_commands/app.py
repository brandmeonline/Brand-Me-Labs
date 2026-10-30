"""Private service boundary. Only the authenticated gateway supplies the principal.

The gateway verifies the member (session or OIDC), their scopes, CSRF for
cookie sessions and recent authentication, then calls this service with its
own credential and the resolved principal in headers. This service checks
scope and recent authentication again, so a misrouted request cannot skip them.
"""
from __future__ import annotations

import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from brandme_core.domains import DomainError
from brandme_core.domains.privacy.deletion import ProcessingFrozenError
from brandme_core.domains.rights import commands
from brandme_core.domains.rights.commands import ChainScope, RightsCommandError

from .config import CommandConfig

MAX_BODY_BYTES = 16 * 1024
#: Same window as My Data export and deletion (privacy.py REAUTH_WINDOW).
RECENT_AUTH = timedelta(minutes=10)
SCOPES = frozenset({"rights:read", "rights:transfer", "rights:reprint", "privacy:manage"})
REQUIRED_MIGRATIONS = set(range(1, 17)) - {3, 4, 5}  # V003–V005 are reserved and have no files


class Refused(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


def _uuid(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        raise Refused(400, "invalid_identifier")
    return str(UUID(value))


def _one(request: Request, name: str) -> str | None:
    values = request.headers.getlist(name)
    if len(values) > 1:
        raise Refused(401, "unauthenticated")
    return values[0] if values else None


def _principal(request: Request) -> tuple[str, frozenset[str], datetime | None]:
    subject = _one(request, "x-subject-ref")
    if not subject:
        raise Refused(401, "unauthenticated")
    scopes = frozenset((_one(request, "x-principal-scopes") or "").split())
    if not scopes <= SCOPES:
        raise Refused(401, "unauthenticated")
    raw = _one(request, "x-auth-time")
    auth_time = None
    if raw:
        try:
            auth_time = datetime.fromisoformat(raw)
        except ValueError:
            raise Refused(401, "unauthenticated") from None
        if auth_time.tzinfo is None:
            raise Refused(401, "unauthenticated")
    return _uuid(subject), scopes, auth_time


def _require(request: Request, scope: str, *, recent: bool = False) -> tuple[str, frozenset[str]]:
    subject, scopes, auth_time = request.state.principal
    if scope not in scopes:
        raise Refused(403, "forbidden")
    if recent:
        now = datetime.now(timezone.utc)
        if auth_time is None or now - auth_time > RECENT_AUTH or auth_time > now + timedelta(seconds=5):
            raise Refused(401, "reauth_required")
    return subject, scopes


async def _body(request: Request) -> Any:
    if (request.headers.get("content-type") or "").split(";")[0].strip() != "application/json":
        raise Refused(415, "unsupported_media_type")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise Refused(413, "request_too_large")
    try:
        return json.loads(raw)
    except ValueError:
        raise Refused(400, "invalid_request") from None


def _idempotency_key(request: Request) -> str:
    key = _one(request, "idempotency-key")
    if not key or not re.fullmatch(r"[A-Za-z0-9._~:-]{16,128}", key):
        raise Refused(400, "idempotency_key_required")
    return key


def verify_schema(database: Any) -> None:
    with database.snapshot(multi_use=True) as snap:
        applied = list(snap.execute_sql("SELECT version, state FROM SchemaMigrations ORDER BY version LIMIT 1000"))
        if not REQUIRED_MIGRATIONS <= {v for v, s in applied if s == "applied"} or any(s != "applied" for _, s in applied):
            raise Refused(503, "schema_unavailable")
        for sql in (
            "SELECT contract_address, invite_digest, offer_nonce, terms_digest, recipient_subject_ref FROM TransferIntents LIMIT 0",
            "SELECT controller_subject_ref, transferable, reprintable FROM RightsEntitlements LIMIT 0",
            "SELECT permissions, territory, allowance_id, quota_granted FROM LicenseGrants LIMIT 0",
            "SELECT issuer_id, territories, active FROM ManufacturerCapabilities LIMIT 0",
            "SELECT request_digest, response_body FROM IdempotencyRecords LIMIT 0",
            "SELECT subject_ref, category FROM ProcessingFreezes LIMIT 0",
        ):
            list(snap.execute_sql(sql))
        commands.assert_serving(snap)


def create_app(database: Any, config: CommandConfig) -> FastAPI:
    scope = ChainScope(config.network, config.contract)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.router.redirect_slashes = False

    @app.exception_handler(Refused)
    async def refused(_request, error):
        return JSONResponse({"error": error.code}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    @app.middleware("http")
    async def boundary(request: Request, call_next: Callable):
        try:
            if request.url.path != "/health":
                auth = request.headers.getlist("authorization")
                if len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), f"Bearer {config.token}".encode()):
                    raise Refused(401, "unauthenticated")
                request.state.principal = _principal(request)
            response = await call_next(request)
        except Refused as error:
            response = JSONResponse({"error": error.code}, status_code=error.status)
        except Exception:
            # Database errors can contain private values or credentials. Neither
            # relay nor log the exception text (including Uvicorn tracebacks).
            response = JSONResponse({"error": "dependency_unavailable"}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    async def run(fn: Callable[[], Any], status: int = 200) -> JSONResponse:
        try:
            result = await run_in_threadpool(fn)
        except ProcessingFrozenError:
            raise Refused(409, "processing_frozen") from None
        except (RightsCommandError, DomainError) as error:
            raise Refused(error.status, error.code) from None
        body, replayed = result if isinstance(result, tuple) else (result, False)
        response = JSONResponse(body, status_code=status)
        if replayed:
            response.headers["Idempotent-Replayed"] = "true"
        return response

    def ready() -> dict:
        verify_schema(database)
        return {"status": "ready", "environment": config.environment, "network": config.network}

    @app.get("/health")
    async def health():
        return await run(ready)

    @app.post("/rights/assets/{asset_id}/transfers")
    async def create_transfer(asset_id: str, request: Request):
        subject, scopes = _require(request, "rights:transfer", recent=True)
        body, key = await _body(request), _idempotency_key(request)
        ctx = commands.member_context(subject, scopes, config.environment)
        return await run(lambda: commands.create_transfer(database, ctx, scope, _uuid(asset_id), body, key), 201)

    @app.post("/rights/transfers/{intent_id}/accept")
    async def accept_transfer(intent_id: str, request: Request):
        subject, scopes = _require(request, "rights:transfer", recent=True)
        body, key = await _body(request), _idempotency_key(request)
        ctx = commands.member_context(subject, scopes, config.environment)
        return await run(lambda: commands.accept_transfer(database, ctx, scope, _uuid(intent_id), body, key))

    @app.get("/rights/transfers/{intent_id}")
    async def transfer_status(intent_id: str, request: Request):
        subject, _ = _require(request, "rights:read")
        return await run(lambda: commands.transfer_status(database, scope, subject, _uuid(intent_id)))

    @app.post("/rights/assets/{asset_id}/reprint-quotes")
    async def reprint_quote(asset_id: str, request: Request):
        subject, _ = _require(request, "rights:reprint")
        body = await _body(request)
        return await run(lambda: commands.reprint_quote(database, scope, subject, _uuid(asset_id), body))

    @app.post("/rights/challenges")
    async def challenge(request: Request):
        subject, _ = _require(request, "rights:read")
        body = await _body(request)
        return await run(lambda: commands.authorize_challenge(database, scope, subject, body), 201)

    return app
