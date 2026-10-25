"""
Internal social router (UNMOUNTED).

ch.03 §6 inventory: ``POST /decisions``, ``POST /decisions/{id}/responses``,
``POST /shares``, ``DELETE /shares/{id}``. Lane additions (proposal PD-09):
relationships, blocks, mutes, decision read/list/open-draft/close/cancel/outcome,
share list/member-open/link-resolve and notifications.

``POST /shares/resolve`` takes the link token in the body (not the path) so it
does not land in access logs, and is the only route here that accepts an
anonymous caller.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from brandme_core.domains.persona.http import PrincipalResolver, _headers, _parse_json, execute, problem
from brandme_core.domains.persona.kernel import DomainError, ValidationFailed

from .decisions import DecisionService
from .flow import FlowService
from .houses import HouseService
from .notifications import NotificationService
from .relationships import RelationshipService
from .reports import ReportService
from .rooms import RoomService
from .shares import ShareService


def _single(b, key: str):
    if not isinstance(b, dict) or set(b) != {key}:
        raise ValidationFailed(f'body must be {{"{key}": ...}}')
    return b[key]


def create_social_router(relationships: RelationshipService, decisions: DecisionService, shares: ShareService,
                         notifications: NotificationService, resolve_principal: PrincipalResolver,
                         reports: Optional[ReportService] = None) -> APIRouter:
    r = APIRouter()

    # -------------------------------------------------------- relationships
    @r.get("/relationships")
    async def list_relationships(request: Request):
        return await execute(request, resolve_principal, relationships.list)

    @r.post("/relationships")
    async def request_relationship(request: Request):
        return await execute(request, resolve_principal, lambda p, b: relationships.request(p, _single(b, "target_member_id")),
                             status=201, with_body=True)

    @r.post("/relationships/{relationship_id}/accept")
    async def accept_relationship(request: Request, relationship_id: str):
        return await execute(request, resolve_principal, lambda p: relationships.accept(p, relationship_id))

    @r.delete("/relationships/{member_id}")
    async def remove_relationship(request: Request, member_id: str):
        return await execute(request, resolve_principal, lambda p: relationships.remove(p, member_id))

    @r.post("/blocks")
    async def block(request: Request):
        return await execute(request, resolve_principal, lambda p, b: relationships.block(p, _single(b, "target_member_id")), with_body=True)

    @r.delete("/blocks/{member_id}")
    async def unblock(request: Request, member_id: str):
        return await execute(request, resolve_principal, lambda p: relationships.unblock(p, member_id))

    @r.get("/mutes")
    async def list_mutes(request: Request):
        return await execute(request, resolve_principal, relationships.list_mutes)

    @r.post("/mutes")
    async def mute(request: Request):
        return await execute(request, resolve_principal, lambda p, b: relationships.mute(p, _single(b, "target_member_id")), with_body=True)

    @r.delete("/mutes/{member_id}")
    async def unmute(request: Request, member_id: str):
        return await execute(request, resolve_principal, lambda p: relationships.unmute(p, member_id))

    # ------------------------------------------------------------ decisions
    @r.get("/decisions")
    async def list_decisions(request: Request):
        role = request.query_params.get("role", "invited")
        return await execute(request, resolve_principal, lambda p: decisions.list(p, role=role))

    @r.post("/decisions")
    async def create_decision(request: Request):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: decisions.create(p, b, k), status=201, with_body=True)

    @r.get("/decisions/{decision_id}")
    async def get_decision(request: Request, decision_id: str):
        return await execute(request, resolve_principal, lambda p: decisions.get(p, decision_id))

    @r.post("/decisions/{decision_id}/open")
    async def open_draft(request: Request, decision_id: str):
        return await execute(request, resolve_principal, lambda p: decisions.open_draft(p, decision_id))

    @r.post("/decisions/{decision_id}/responses")
    async def respond(request: Request, decision_id: str):
        return await execute(request, resolve_principal, lambda p, b: decisions.respond(p, decision_id, b), with_body=True)

    @r.post("/decisions/{decision_id}/close")
    async def close(request: Request, decision_id: str):
        return await execute(request, resolve_principal, lambda p: decisions.close(p, decision_id))

    @r.post("/decisions/{decision_id}/cancel")
    async def cancel(request: Request, decision_id: str):
        return await execute(request, resolve_principal, lambda p: decisions.cancel(p, decision_id))

    @r.get("/decisions/{decision_id}/comments")
    async def decision_comments(request: Request, decision_id: str):
        return await execute(request, resolve_principal, lambda p: decisions.comments(p, decision_id))

    @r.post("/decisions/{decision_id}/comments")
    async def add_decision_comment(request: Request, decision_id: str):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: decisions.add_comment(p, decision_id, b, k), status=201, with_body=True)

    @r.delete("/decisions/{decision_id}/comments/{comment_id}")
    async def remove_decision_comment(request: Request, decision_id: str, comment_id: str):
        return await execute(request, resolve_principal, lambda p: decisions.remove_comment(p, decision_id, comment_id))

    @r.put("/decisions/{decision_id}/outcome")
    async def outcome(request: Request, decision_id: str):
        return await execute(request, resolve_principal, lambda p, b: decisions.record_outcome(p, decision_id, _single(b, "outcome")),
                             with_body=True)

    # --------------------------------------------------------------- shares
    @r.get("/shares")
    async def list_shares(request: Request):
        return await execute(request, resolve_principal, shares.list)

    @r.post("/shares")
    async def create_share(request: Request):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: shares.create(p, b, k), status=201, with_body=True)

    @r.delete("/shares/{share_id}")
    async def revoke_share(request: Request, share_id: str):
        return await execute(request, resolve_principal, lambda p: shares.revoke(p, share_id))

    @r.get("/shares/{share_id}")
    async def open_share(request: Request, share_id: str):
        return await execute(request, resolve_principal, lambda p: shares.open_for_member(p, share_id))

    @r.post("/shares/resolve")
    async def resolve_share(request: Request):
        principal = resolve_principal(request)
        environment = principal.environment if principal else "development"
        try:
            token = _single(_parse_json(await request.body()), "token")
            result = await run_in_threadpool(shares.open_by_token, token, principal)
        except DomainError as err:
            return problem(request, err, environment)
        return JSONResponse(result, headers=_headers(request, environment))

    # -------------------------------------------------------- notifications
    @r.get("/notifications")
    async def list_notifications(request: Request):
        q = request.query_params
        limit: Optional[str] = q.get("limit")

        def run(p):
            if limit is not None and not limit.isdigit():
                raise ValidationFailed("limit must be an integer", extra={"field": "limit"})
            return notifications.list(p, cursor=q.get("cursor"), limit=int(limit) if limit else 24)

        return await execute(request, resolve_principal, run)

    @r.post("/notifications/read")
    async def mark_read(request: Request):
        return await execute(request, resolve_principal, lambda p, b: notifications.mark_read(p, _single(b, "ids")), with_body=True)

    # -------------------------------------------------------------- reports
    if reports is not None:
        @r.post("/reports")
        async def report(request: Request):
            return await execute(request, resolve_principal, reports.report, status=201, with_body=True)

        @r.get("/reports")
        async def my_reports(request: Request):
            return await execute(request, resolve_principal, reports.my_reports)

    return r


def create_flow_router(flow: FlowService, houses: HouseService, resolve_principal: PrincipalResolver) -> APIRouter:
    """Home = Flow, and the houses that feed it (Ultra plan 02, item 3)."""
    r = APIRouter()

    @r.get("/flow")
    async def home(request: Request):
        q = request.query_params
        limit = q.get("limit")

        def run(p):
            if limit is not None and not limit.isdigit():
                raise ValidationFailed("limit must be an integer", extra={"field": "limit"})
            return flow.flow(p, limit=int(limit) if limit else 24, cursor=q.get("cursor"))

        return await execute(request, resolve_principal, run)

    @r.get("/houses")
    async def my_houses(request: Request):
        return await execute(request, resolve_principal, houses.list)

    @r.put("/houses/{house_ref}/follow")
    async def follow(request: Request, house_ref: str):
        return await execute(request, resolve_principal, lambda p, b: houses.follow(p, house_ref, b), with_body=True)

    @r.delete("/houses/{house_ref}/follow")
    async def unfollow(request: Request, house_ref: str):
        return await execute(request, resolve_principal, lambda p: houses.unfollow(p, house_ref))

    return r


def create_rooms_router(rooms: RoomService, resolve_principal: PrincipalResolver) -> APIRouter:
    """Small-group rooms (Ultra plan 02, item 7)."""
    r = APIRouter()

    @r.get("/rooms")
    async def my_rooms(request: Request):
        return await execute(request, resolve_principal, rooms.mine)

    @r.post("/rooms")
    async def open_room(request: Request):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: rooms.create(p, b, k), status=201, with_body=True)

    @r.get("/rooms/{room_id}")
    async def room(request: Request, room_id: str):
        return await execute(request, resolve_principal, lambda p: rooms.get(p, room_id))

    @r.post("/rooms/{room_id}/archive")
    async def archive_room(request: Request, room_id: str):
        return await execute(request, resolve_principal, lambda p: rooms.archive(p, room_id))

    @r.post("/rooms/{room_id}/members")
    async def add_member(request: Request, room_id: str):
        return await execute(request, resolve_principal, lambda p, b: rooms.add_member(p, room_id, _single(b, "member_id")), with_body=True)

    @r.delete("/rooms/{room_id}/members/{member_id}")
    async def remove_member(request: Request, room_id: str, member_id: str):
        return await execute(request, resolve_principal, lambda p: rooms.remove_member(p, room_id, member_id))

    @r.post("/rooms/{room_id}/posts")
    async def post(request: Request, room_id: str):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: rooms.post(p, room_id, b, k), status=201, with_body=True)

    @r.put("/rooms/{room_id}/posts/{post_id}/reaction")
    async def react(request: Request, room_id: str, post_id: str):
        return await execute(request, resolve_principal, lambda p, b: rooms.react(p, room_id, post_id, b), with_body=True)

    @r.delete("/rooms/{room_id}/posts/{post_id}")
    async def withdraw(request: Request, room_id: str, post_id: str):
        return await execute(request, resolve_principal, lambda p: rooms.withdraw(p, room_id, post_id))

    return r


def create_moderation_ops_router(reports: ReportService, resolve_principal: PrincipalResolver) -> APIRouter:
    """Console-only (``moderation:admin``); mount behind operator auth."""
    r = APIRouter(prefix="/ops")

    @r.get("/moderation/reports")
    async def queue(request: Request):
        q = request.query_params
        limit = q.get("limit")

        def run(p):
            if limit is not None and not limit.isdigit():
                raise ValidationFailed("limit must be an integer", extra={"field": "limit"})
            return reports.queue(p, state=q.get("state", "open"), limit=int(limit) if limit else 50)

        return await execute(request, resolve_principal, run)

    @r.post("/moderation/reports/{report_id}/resolve")
    async def resolve(request: Request, report_id: str):
        return await execute(request, resolve_principal, lambda p, b: reports.resolve(p, report_id, b), with_body=True)

    return r
