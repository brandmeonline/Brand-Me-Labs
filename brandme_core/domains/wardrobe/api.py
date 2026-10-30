"""
Internal wardrobe / closet / outfits / packing router (UNMOUNTED).

Mirrors the ch.03 §6 inventory: ``/wardrobe/items``, ``/closet/layout``,
``/closet/layout/theme``, ``/closet/placements/{itemId}``,
``/closet/placements/batch``, ``/outfits``, ``/outfits/{id}/versions``,
``/outfits/{id}/proposals``. Lane additions (proposal PD-09): unarchive,
duplicate resolution, worn log, proposal accept/decline and packing lists.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request

from brandme_core.domains.persona.http import PrincipalResolver, execute
from brandme_core.domains.persona.kernel import ValidationFailed, require_strict_int

from .outfits import OutfitService
from .service import WardrobeService


def _limit(raw: Optional[str], default: int = 24) -> int:
    if raw is None:
        return default
    if not raw.isdigit():
        raise ValidationFailed("limit must be an integer", extra={"field": "limit"})
    return require_strict_int(int(raw), name="limit", lo=1, hi=100)


def _version(result) -> Optional[str]:
    return result.get("version") if isinstance(result, dict) else None


def create_wardrobe_router(wardrobe: WardrobeService, outfits: OutfitService, resolve_principal: PrincipalResolver) -> APIRouter:
    r = APIRouter()
    H = lambda req, name: req.headers.get(name)  # noqa: E731

    # ---------------------------------------------------------------- items
    @r.get("/wardrobe/items")
    async def list_items(request: Request):
        q = request.query_params
        return await execute(request, resolve_principal, lambda p: wardrobe.list_items(
            p, collection=q.get("collection"), category=q.get("category"), q=q.get("q"), cursor=q.get("cursor"), limit=_limit(q.get("limit"))))

    @r.post("/wardrobe/items")
    async def create_items(request: Request):
        k = H(request, "idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: wardrobe.create_items(p, b, k), status=201, with_body=True)

    @r.get("/wardrobe/items/{item_id}")
    async def get_item(request: Request, item_id: str):
        return await execute(request, resolve_principal, lambda p: wardrobe.get_item(p, item_id), etag=_version)

    @r.patch("/wardrobe/items/{item_id}")
    async def patch_item(request: Request, item_id: str):
        im = H(request, "if-match")
        return await execute(request, resolve_principal, lambda p, b: wardrobe.patch_item(p, item_id, im, b), etag=_version, with_body=True)

    @r.post("/wardrobe/items/{item_id}/archive")
    async def archive(request: Request, item_id: str):
        im = H(request, "if-match")
        return await execute(request, resolve_principal, lambda p: wardrobe.archive_item(p, item_id, im), etag=_version)

    @r.post("/wardrobe/items/{item_id}/unarchive")
    async def unarchive(request: Request, item_id: str):
        im = H(request, "if-match")
        return await execute(request, resolve_principal, lambda p: wardrobe.archive_item(p, item_id, im, archive=False), etag=_version)

    @r.post("/wardrobe/items/{item_id}/duplicates/{other_id}")
    async def resolve_duplicate(request: Request, item_id: str, other_id: str):
        def run(p, b):
            if not isinstance(b, dict) or set(b) != {"action"}:
                raise ValidationFailed('body must be {"action": "merge" | "keep_both"}')
            return wardrobe.resolve_duplicate(p, item_id, other_id, b["action"])

        return await execute(request, resolve_principal, run, with_body=True)

    @r.post("/wardrobe/items/{item_id}/worn")
    async def worn(request: Request, item_id: str):
        k = H(request, "idempotency-key")
        return await execute(request, resolve_principal, lambda p: wardrobe.record_worn(p, item_id, k))

    # --------------------------------------------------------------- closet
    @r.get("/closet/layout")
    async def layout(request: Request):
        return await execute(request, resolve_principal, lambda p: wardrobe.get_layout(p), etag=_version)

    @r.put("/closet/layout/theme")
    async def theme(request: Request):
        im = H(request, "if-match")
        preview = request.query_params.get("preview") == "true"

        def run(p, b):
            if not isinstance(b, dict) or set(b) != {"room_template_id"}:
                raise ValidationFailed('body must be {"room_template_id": ...}')
            return wardrobe.set_theme(p, im, b["room_template_id"], preview=preview)

        return await execute(request, resolve_principal, run, with_body=True)

    @r.put("/closet/placements/{item_id}")
    async def put_placement(request: Request, item_id: str):
        im = H(request, "if-match")
        return await execute(request, resolve_principal, lambda p, b: wardrobe.put_placement(p, item_id, im, b), etag=_version, with_body=True)

    @r.post("/closet/placements/batch")
    async def batch(request: Request):
        k = H(request, "idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: wardrobe.batch_placements(p, b, k), with_body=True)

    # -------------------------------------------------------------- outfits
    @r.get("/outfits")
    async def list_outfits(request: Request):
        q = request.query_params
        return await execute(request, resolve_principal, lambda p: outfits.list_outfits(p, cursor=q.get("cursor"), limit=_limit(q.get("limit"))))

    @r.post("/outfits")
    async def create_outfit(request: Request):
        k = H(request, "idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: outfits.create_outfit(p, b, k), status=201, with_body=True)

    @r.get("/outfits/{outfit_id}")
    async def get_outfit(request: Request, outfit_id: str):
        return await execute(request, resolve_principal, lambda p: outfits.get_outfit(p, outfit_id))

    @r.post("/outfits/{outfit_id}/versions")
    async def new_version(request: Request, outfit_id: str):
        im = H(request, "if-match")
        return await execute(request, resolve_principal, lambda p, b: outfits.create_version(p, outfit_id, im, b), status=201, with_body=True)

    @r.get("/outfits/{outfit_id}/proposals")
    async def list_proposals(request: Request, outfit_id: str):
        return await execute(request, resolve_principal, lambda p: {"items": outfits.list_proposals(p, outfit_id), "next_cursor": None})

    @r.post("/outfits/{outfit_id}/proposals")
    async def propose(request: Request, outfit_id: str):
        k = H(request, "idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: outfits.propose(p, outfit_id, b, k), status=201, with_body=True)

    @r.post("/outfits/{outfit_id}/proposals/{proposal_id}/{decision}")
    async def decide(request: Request, outfit_id: str, proposal_id: str, decision: str):
        im = H(request, "if-match")
        return await execute(request, resolve_principal, lambda p: outfits.decide_proposal(p, outfit_id, proposal_id, decision, im))

    # -------------------------------------------------------------- packing
    @r.post("/packing-lists")
    async def create_packing(request: Request):
        k = H(request, "idempotency-key")
        return await execute(request, resolve_principal, lambda p, b: outfits.create_packing_list(p, b, k), status=201, with_body=True)

    @r.get("/packing-lists/{list_id}")
    async def get_packing(request: Request, list_id: str):
        return await execute(request, resolve_principal, lambda p: outfits.get_packing_list(p, list_id), etag=_version)

    @r.patch("/packing-lists/{list_id}/entries/{entry_id}")
    async def set_entry(request: Request, list_id: str, entry_id: str):
        im = H(request, "if-match")

        def run(p, b):
            if not isinstance(b, dict) or set(b) != {"state"}:
                raise ValidationFailed('body must be {"state": ...}')
            return outfits.set_packing_entry_state(p, list_id, entry_id, b["state"], im)

        return await execute(request, resolve_principal, run, etag=_version, with_body=True)

    return r
