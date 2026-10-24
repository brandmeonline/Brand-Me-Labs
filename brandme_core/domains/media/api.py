"""
Internal media / try-on router (UNMOUNTED).

ch.03 §6: ``POST /media/uploads``, ``GET /media/jobs/{id}``,
``POST /try-on/jobs``, ``DELETE /try-on/jobs/{id}``. Lane additions (PD-09):
``POST /media/uploads/{id}/complete``, ``GET /try-on/capabilities``,
``GET /try-on/jobs/{id}``, ``GET /try-on/jobs/{id}/result`` (protected
retrieval, private no-store), ``POST /try-on/jobs/{id}/save``,
``GET /try-on/consents``, ``DELETE /try-on/consents/{id}``.
Workers (dispatch, collect, expiry, purge) are not HTTP routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from brandme_core.domains.persona.http import PrincipalResolver, _headers, execute, problem
from brandme_core.domains.persona.kernel import DomainError

from .service import MediaService


def create_media_router(media: MediaService, resolve_principal: PrincipalResolver) -> APIRouter:
    r = APIRouter()

    @r.post("/media/uploads")
    async def create_upload(request: Request):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: media.create_upload(p, b, k), status=201, with_body=True)

    @r.post("/media/uploads/{media_id}/complete")
    async def complete(request: Request, media_id: str):
        return await execute(request, resolve_principal, lambda p: media.complete_upload(p, media_id))

    @r.get("/media/jobs/{media_id}")
    async def media_job(request: Request, media_id: str):
        return await execute(request, resolve_principal, lambda p: media.get_media_job(p, media_id))

    @r.get("/try-on/capabilities")
    async def capabilities(request: Request):
        return await execute(request, resolve_principal, media.capabilities)

    @r.post("/try-on/jobs")
    async def create_job(request: Request):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: media.create_job(p, b, k), status=202, with_body=True)

    @r.get("/try-on/jobs/{job_id}")
    async def get_job(request: Request, job_id: str):
        return await execute(request, resolve_principal, lambda p: media.get_job(p, job_id))

    @r.get("/try-on/jobs/{job_id}/result")
    async def result(request: Request, job_id: str):
        principal = resolve_principal(request)
        environment = principal.environment if principal else "development"
        if principal is None:
            err = DomainError("A valid session or bearer token is required.", code="unauthenticated")
            err.status = 401
            return problem(request, err, environment)
        try:
            ctype, data = await run_in_threadpool(media.result, principal, job_id)
        except DomainError as err:
            return problem(request, err, environment)
        return Response(content=data, media_type=ctype, headers=_headers(request, environment, {"Content-Disposition": "inline"}))

    @r.post("/try-on/jobs/{job_id}/save")
    async def save(request: Request, job_id: str):
        return await execute(request, resolve_principal, lambda p: media.save_job(p, job_id))

    @r.delete("/try-on/jobs/{job_id}")
    async def delete(request: Request, job_id: str):
        return await execute(request, resolve_principal, lambda p: media.delete_job(p, job_id), status=204)

    @r.get("/try-on/consents")
    async def consents(request: Request):
        return await execute(request, resolve_principal, media.list_consents)

    @r.delete("/try-on/consents/{consent_id}")
    async def revoke(request: Request, consent_id: str):
        return await execute(request, resolve_principal, lambda p: media.revoke_consent(p, consent_id))

    return r
