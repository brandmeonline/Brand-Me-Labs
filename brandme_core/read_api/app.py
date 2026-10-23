"""Private service boundary. Only the authenticated gateway supplies subject IDs."""
from __future__ import annotations

import hmac
import re
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from .config import ReadConfig
from .reads import ReadError, ReadService

MAX_RESPONSE_BYTES = 512 * 1024


def _uuid(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
            raise ValueError()
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ReadError(400, "invalid_identifier") from None


def _page(request, *, entitlement=False):
    keys = [k for k, _ in request.query_params.multi_items()]
    if len(keys) != len(set(keys)) or set(keys) - {"cursor", "limit"}:
        raise ReadError(400, "invalid_query")
    cursor = request.query_params.get("cursor", "")
    if cursor:
        if entitlement:
            if not re.fullmatch(r"[0-9a-f]{64}", cursor):
                raise ReadError(400, "invalid_cursor")
        else:
            cursor = _uuid(cursor)
    raw_limit = request.query_params.get("limit", "24")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", raw_limit) or int(raw_limit) > 100:
        raise ReadError(400, "invalid_limit")
    return cursor, int(raw_limit)


def _no_query(request):
    if request.query_params:
        raise ReadError(400, "invalid_query")


def _response(body):
    response = JSONResponse(body)
    if len(response.body) > MAX_RESPONSE_BYTES:
        raise ReadError(503, "response_too_large")
    return response


def create_app(database, config: ReadConfig):
    service = ReadService(database, config)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.router.redirect_slashes = False

    @app.exception_handler(ReadError)
    async def read_error(_request, error):
        return JSONResponse({"error": error.code}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        try:
            if request.url.path != "/health":
                token = (config.rights_token if request.url.path.startswith("/rights/") else
                         config.privacy_token if request.url.path.startswith("/privacy/") else None)
                auth = request.headers.getlist("authorization")
                if token is None or len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), f"Bearer {token}".encode()):
                    raise ReadError(401, "unauthenticated")
                subjects = request.headers.getlist("x-subject-ref")
                public_passport = request.method == "GET" and re.fullmatch(r"/rights/assets/[^/]+/passport", request.url.path)
                if len(subjects) > 1 or not public_passport and not subjects:
                    raise ReadError(401, "unauthenticated")
                request.state.subject = _uuid(subjects[0]) if subjects else None
            response = await call_next(request)
        except ReadError as error:
            response = JSONResponse({"error": error.code}, status_code=error.status)
        except Exception:
            # Database errors can contain private values/credentials. Neither
            # relay nor log the exception text (including Uvicorn tracebacks).
            response = JSONResponse({"error": "dependency_unavailable"}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Authorization, X-Subject-Ref"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health():
        return _response(service.ready())

    @app.get("/rights/entitlements")
    def entitlements(request: Request):
        return _response(service.entitlements(request.state.subject, *_page(request, entitlement=True)))

    @app.get("/rights/reprint-jobs/{job_id}")
    def reprint(job_id: str, request: Request):
        _no_query(request)
        return _response(service.reprint(request.state.subject, _uuid(job_id)))

    @app.get("/rights/assets/{asset_id}/passport")
    def passport(asset_id: str, request: Request):
        return _response(service.passport(request.state.subject, _uuid(asset_id), *_page(request)))

    @app.get("/privacy/inventory")
    def inventory(request: Request):
        _no_query(request)
        return _response(service.inventory())

    @app.get("/privacy/deletion/{job_id}")
    def deletion(job_id: str, request: Request):
        _no_query(request)
        return _response(service.deletion(request.state.subject, _uuid(job_id)))

    @app.api_route("/privacy/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
    @app.api_route("/rights/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
    def commands_unavailable(path: str):
        raise ReadError(503, "capability_unavailable")

    return app
