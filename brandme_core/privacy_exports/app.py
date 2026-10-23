"""Private export API. The gateway supplies only verified member/auth evidence."""
import hmac
import json

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from brandme_core.read_api.app import _uuid
from brandme_core.read_api.reads import ReadError
from .service import ExportService


def create_app(database, config, store):
    service = ExportService(database, config, store)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.router.redirect_slashes = False

    @app.exception_handler(ReadError)
    async def expected_error(_request, error):
        return JSONResponse({"error": error.code}, status_code=error.status)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        try:
            if request.query_params:
                raise ReadError(400, "invalid_query")
            if request.url.path != "/health":
                auth = request.headers.getlist("authorization")
                subjects = request.headers.getlist("x-subject-ref")
                if (len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), f"Bearer {config.token}".encode())
                        or len(subjects) != 1):
                    raise ReadError(401, "unauthenticated")
                request.state.subject = _uuid(subjects[0])
            response = await call_next(request)
        except ReadError as error:
            response = JSONResponse({"error": error.code}, status_code=error.status)
        except Exception:
            response = JSONResponse({"error": "dependency_unavailable"}, status_code=503)
        response.headers.update({"Cache-Control": "private, no-store", "Vary": "Authorization, X-Subject-Ref",
                                 "X-Content-Type-Options": "nosniff"})
        return response

    @app.get("/health")
    def health():
        service.capability()
        return {"status": "ready", "full_account": False}

    @app.get("/capability")
    def capability():
        return service.capability()

    @app.post("/exports", status_code=202)
    async def request_export(request: Request):
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 4096:
                raise ReadError(413, "request_too_large")
            data.extend(chunk)
        try:
            def closed_object(pairs):
                if len(dict(pairs)) != len(pairs):
                    raise ValueError()
                return dict(pairs)
            body = json.loads(data, object_pairs_hook=closed_object)
            if not isinstance(body, dict) or set(body) != {"categories", "reauth_at"}:
                raise ValueError()
        except (ValueError, UnicodeError):
            raise ReadError(400, "invalid_request") from None
        keys = request.headers.getlist("idempotency-key")
        if len(keys) != 1:
            raise ReadError(400, "idempotency_key_required")
        return await run_in_threadpool(service.request, request.state.subject, body["categories"], keys[0], body["reauth_at"])

    @app.get("/exports/{job_id}")
    def status(job_id: str, request: Request):
        return service.status(request.state.subject, _uuid(job_id))

    @app.get("/exports/{job_id}/download")
    def download(job_id: str, request: Request):
        job_id = _uuid(job_id)
        reauth = request.headers.getlist("x-reauth-at")
        if len(reauth) != 1:
            raise ReadError(401, "reauth_required")
        data, digest = service.download(request.state.subject, job_id, reauth[0])
        return Response(data, media_type="application/json", headers={"X-Export-SHA256": digest,
                        "Content-Disposition": f'attachment; filename="brandme-rights-{job_id}.json"'})

    return app
