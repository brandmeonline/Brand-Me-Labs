"""
Internal rewards routers (UNMOUNTED).

Member router: ch.03 §6 ``GET /rewards`` and ``POST /benefits/{id}/reservations``.
Lane additions (PD-09): ``GET /rewards/entries``, ``GET /benefits``,
``GET /rewards/reservations``, ``GET``/``POST /rewards/disputes``. There is
no member route that awards, edits or transfers points (BM-LOY-005).

Ops router (console-only, ``moderation:admin``; mount behind operator auth):
dispute queue and resolution, member ledger audit, linked reversal, reviewer
acceptance of contributions, benefit creation.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request

from brandme_core.domains.persona.http import PrincipalResolver, execute
from brandme_core.domains.persona.kernel import ValidationFailed, reject_unknown_keys, require_strict_int

from .benefits import BenefitService
from .service import RewardsService


def _limit(raw: Optional[str], default: int = 24) -> int:
    if raw is None:
        return default
    if not raw.isdigit():
        raise ValidationFailed("limit must be an integer", extra={"field": "limit"})
    return require_strict_int(int(raw), name="limit", lo=1, hi=100)


def create_rewards_router(rewards: RewardsService, benefits: BenefitService, resolve_principal: PrincipalResolver) -> APIRouter:
    r = APIRouter()

    @r.get("/rewards")
    async def summary(request: Request):
        return await execute(request, resolve_principal, rewards.summary)

    @r.get("/rewards/entries")
    async def entries(request: Request):
        q = request.query_params
        return await execute(request, resolve_principal, lambda p: rewards.entries(p, cursor=q.get("cursor"), limit=_limit(q.get("limit"))))

    @r.get("/rewards/reservations")
    async def reservations(request: Request):
        return await execute(request, resolve_principal, benefits.list_reservations)

    @r.get("/rewards/disputes")
    async def my_disputes(request: Request):
        return await execute(request, resolve_principal, rewards.my_disputes)

    @r.post("/rewards/disputes")
    async def open_dispute(request: Request):
        return await execute(request, resolve_principal, rewards.open_dispute, status=201, with_body=True)

    @r.get("/benefits")
    async def list_benefits(request: Request):
        return await execute(request, resolve_principal, benefits.list_benefits)

    @r.post("/benefits/{benefit_id}/reservations")
    async def reserve(request: Request, benefit_id: str):
        k = request.headers.get("idempotency-key")
        return await execute(request, resolve_principal, lambda p: benefits.reserve(p, benefit_id, k), status=201)

    return r


def create_rewards_ops_router(rewards: RewardsService, benefits: BenefitService, resolve_principal: PrincipalResolver) -> APIRouter:
    r = APIRouter(prefix="/ops")

    @r.get("/rewards/disputes")
    async def disputes(request: Request):
        q = request.query_params
        return await execute(request, resolve_principal, lambda p: rewards.list_disputes(p, state=q.get("state", "open"), limit=_limit(q.get("limit"), 50)))

    @r.post("/rewards/disputes/{dispute_id}/resolve")
    async def resolve(request: Request, dispute_id: str):
        return await execute(request, resolve_principal, lambda p, b: rewards.resolve_dispute(p, dispute_id, b), with_body=True)

    @r.get("/rewards/members/{member_id}/ledger")
    async def member_ledger(request: Request, member_id: str):
        return await execute(request, resolve_principal, lambda p: rewards.member_ledger(p, member_id))

    @r.post("/rewards/members/{member_id}/entries/{entry_id}/reverse")
    async def reverse(request: Request, member_id: str, entry_id: str):
        def run(p, b):
            if not isinstance(b, dict):
                raise ValidationFailed("body must be an object")
            reject_unknown_keys(b, ("reason", "evidence_ref"), where="reversal")
            return rewards.reverse_entry(p, member_id, entry_id, reason=b.get("reason"), evidence_ref=b.get("evidence_ref"))

        return await execute(request, resolve_principal, run, with_body=True)

    @r.post("/rewards/contributions")
    async def accept(request: Request):
        def run(p, b):
            if not isinstance(b, dict):
                raise ValidationFailed("body must be an object")
            reject_unknown_keys(b, ("member_ref", "kind", "contribution_ref", "evidence_ref"), where="contribution")
            return rewards.accept_contribution(p, b.get("member_ref"), kind=b.get("kind"), contribution_ref=b.get("contribution_ref"),
                                               evidence_ref=b.get("evidence_ref"))

        return await execute(request, resolve_principal, run, with_body=True)

    @r.post("/benefits")
    async def create_benefit(request: Request):
        return await execute(request, resolve_principal, benefits.create_benefit, status=201, with_body=True)

    return r
