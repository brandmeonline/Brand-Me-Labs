"""
Internal persona / recommendation / guest-migration router (UNMOUNTED).

Paths mirror the public ``/api/v1`` surface (ch.03 §6 and the foundation's
generated OpenAPI ``persona`` tag). Mount with::

    app.include_router(create_persona_router(service, guest, resolve_principal))

Contract flags honoured: ``If-Match`` on PATCH /me/persona, reset, restore,
contexts and adaptation; ``Idempotency-Key`` (16–128 chars) on suppress, reset,
snapshots, feedback and guest migration; cursor pagination on evidence.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Request

from .http import PrincipalResolver, execute
from .kernel import ValidationFailed, parse_iso, reject_unknown_keys, require_strict_int
from .onboarding import GuestMigrationService
from .service import PersonaService


def _limit(raw: Optional[str], default: int, hi: int) -> int:
    if raw is None:
        return default
    if not raw.isdigit():
        raise ValidationFailed("limit must be an integer", extra={"field": "limit"})
    return require_strict_int(int(raw), name="limit", lo=1, hi=hi)


def _profile_version(result: Any) -> Optional[str]:
    if isinstance(result, dict) and isinstance(result.get("profile"), dict):
        return result["profile"].get("version")
    return None


def create_persona_router(
    persona: PersonaService,
    guest: GuestMigrationService,
    resolve_principal: PrincipalResolver,
) -> APIRouter:
    r = APIRouter()

    @r.get("/me/persona")
    async def get_persona(request: Request):
        return await execute(request, resolve_principal, lambda p: persona.get(p), etag=_profile_version)

    @r.patch("/me/persona")
    async def patch_persona(request: Request):
        im = request.headers.get("if-match")
        return await execute(request, resolve_principal, lambda p, b: persona.patch(p, im, b), etag=_profile_version, with_body=True)

    @r.post("/me/persona/preview")
    async def preview_persona(request: Request):
        occasion = request.query_params.get("occasion")
        return await execute(request, resolve_principal, lambda p, b: persona.preview(p, b, occasion=occasion), with_body=True)

    @r.get("/me/persona/evidence")
    async def list_evidence(request: Request):
        q = request.query_params

        def run(p):
            return persona.list_evidence_page(p, cursor=q.get("cursor"), limit=_limit(q.get("limit"), 24, 100))

        return await execute(request, resolve_principal, run)

    @r.post("/me/persona/evidence/{evidence_id}/suppress")
    async def suppress_evidence(request: Request, evidence_id: str):
        key = request.headers.get("idempotency-key")

        def run(p):
            if key is None:
                raise ValidationFailed("Idempotency-Key is required", extra={"field": "Idempotency-Key"})
            return persona.suppress_evidence(p, evidence_id, idempotency_key=key)

        return await execute(request, resolve_principal, run, etag=_profile_version)

    @r.post("/me/persona/reset")
    async def reset(request: Request):
        im, key = request.headers.get("if-match"), request.headers.get("idempotency-key")

        def run(p, body):
            if not isinstance(body, dict):
                raise ValidationFailed("body must be an object")
            reject_unknown_keys(body, ("scope", "confirm"), where="reset")
            if key is None:
                raise ValidationFailed("Idempotency-Key is required", extra={"field": "Idempotency-Key"})
            return persona.reset(p, im, body.get("scope"), body.get("confirm"), idempotency_key=key)

        return await execute(request, resolve_principal, run, etag=_profile_version, with_body=True)

    @r.post("/me/persona/snapshots")
    async def create_snapshot(request: Request):
        key = request.headers.get("idempotency-key")

        def run(p, body):
            if not isinstance(body, dict):
                raise ValidationFailed("body must be an object")
            reject_unknown_keys(body, ("name",), where="snapshot")
            if key is None:
                raise ValidationFailed("Idempotency-Key is required", extra={"field": "Idempotency-Key"})
            return persona.create_snapshot(p, body.get("name"), idempotency_key=key)

        return await execute(request, resolve_principal, run, status=201, with_body=True)

    @r.get("/me/persona/snapshots/{snapshot_id}/diff")
    async def snapshot_diff(request: Request, snapshot_id: str):
        return await execute(request, resolve_principal, lambda p: persona.snapshot_diff(p, snapshot_id))

    @r.post("/me/persona/snapshots/{snapshot_id}/restore")
    async def restore_snapshot(request: Request, snapshot_id: str):
        im = request.headers.get("if-match")
        return await execute(
            request, resolve_principal, lambda p: persona.restore_snapshot(p, im, snapshot_id), etag=_profile_version
        )

    @r.post("/me/persona/contexts")
    async def add_context(request: Request):
        im = request.headers.get("if-match")

        def run(p, body):
            if not isinstance(body, dict):
                raise ValidationFailed("body must be an object")
            reject_unknown_keys(body, ("label", "axes", "starts_at", "ends_at"), where="context")
            return persona.add_context_override(
                p,
                im,
                body.get("label"),
                body.get("axes"),
                parse_iso(body.get("starts_at"), name="starts_at"),
                parse_iso(body.get("ends_at"), name="ends_at"),
            )

        return await execute(request, resolve_principal, run, status=201, etag=_profile_version, with_body=True)

    @r.patch("/me/persona/contexts/{override_id}")
    async def set_context(request: Request, override_id: str):
        im = request.headers.get("if-match")

        def run(p, body):
            if not isinstance(body, dict) or set(body) != {"enabled"} or not isinstance(body["enabled"], bool):
                raise ValidationFailed("body must be {\"enabled\": true|false}")
            return persona.set_context_override_enabled(p, im, override_id, body["enabled"])

        return await execute(request, resolve_principal, run, etag=_profile_version, with_body=True)

    @r.post("/me/persona/adaptations/{axis}/accept")
    async def accept_adaptation(request: Request, axis: str):
        im = request.headers.get("if-match")
        return await execute(request, resolve_principal, lambda p: persona.accept_adaptation(p, im, axis), etag=_profile_version)

    @r.get("/recommendations")
    async def recommendations(request: Request):
        q = request.query_params

        def run(p):
            out = persona.recommendations(p, occasion=q.get("occasion"), limit=_limit(q.get("limit"), 6, 24))
            out["next_cursor"] = None  # one ranked page; ranking is recomputed per request
            return out

        return await execute(request, resolve_principal, run)

    @r.post("/recommendations/{product_id}/feedback")
    async def recommendation_feedback(request: Request, product_id: str):
        key = request.headers.get("idempotency-key")

        def run(p, body):
            if not isinstance(body, dict):
                raise ValidationFailed("body must be an object")
            reject_unknown_keys(body, ("category", "signal"), where="feedback")
            return persona.record_feedback(p, product_id, body.get("category"), body.get("signal"), key)

        return await execute(request, resolve_principal, run, with_body=True)

    @r.post("/me/guest-migration")
    async def guest_migration(request: Request):
        key = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: guest.migrate(p, b, key), with_body=True)

    return r
