"""Disclosure facets at the API layer (Ultra plan 03 item 12), on the Spanner
emulator and through the mounted domain app.

The locked stranger-scan default: strangers see identity, house, maker and story
at most; price, ownership and logistics appear only when the owner unfolds them,
and only to friends; never-shown columns appear at no level, on any surface."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from brandme_core.domains.persona import app as domain_app
from brandme_core.domains.persona.kernel import member_principal, query, run_read, run_txn
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.social.shares import OUTFIT_ITEM_FIELDS, SHAREABLE_FIELDS
from brandme_core.domains.wardrobe import disclosure as d
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.domains.wardrobe.visibility import shown_piece
from test_persona_harness import MEMBER_SCOPES, insert_member, spanner_db  # noqa: F401

PRODUCT = str(uuid.uuid4())
# A distinctive value for every column that must not reach a stranger.
SECRETS = {
    "price_minor": 987654, "source_ref": "src-SECRET-1", "receipt_line_ref": "rcpt-SECRET-2", "tag_serial_hash": "f" * 63 + "e",
    "size_label": "XS-SECRET-3", "care_notes": "care-SECRET-4", "user_notes": "note-SECRET-5", "variant_ref": "variant-SECRET-6",
    "care_state": "in_repair", "unit_index": 424242,
}


class Houses:
    """Catalog port stand-in: the one test product belongs to one house."""

    def houses_of(self, snap, product_ids):
        return {p: "atelier-disclosure" for p in product_ids if p == PRODUCT}


def key():
    return "k-" + uuid.uuid4().hex


def test_every_wardrobe_column_is_classified(spanner_db):
    cols = run_read(spanner_db, lambda s: {r[0] for r in query(
        s, "SELECT column_name FROM information_schema.columns WHERE table_schema='' AND table_name='WardrobeItems'", {}, {})})
    assert cols == set(d.COLUMNS), "classify every WardrobeItems column in wardrobe/disclosure.py (a facet, NEVER or META)"


def test_the_locked_default_is_the_classification():
    assert d.STRANGER_FACETS == {"identity", "house", "maker", "story"}
    assert d.UNFOLD_FACETS == {"price", "ownership", "logistics"} and set(d.FACETS) == d.STRANGER_FACETS | d.UNFOLD_FACETS
    for key_, facet, cols, _ in d.PROJECTION:
        assert {d.COLUMNS[c] for c in cols} == {facet}, f"{key_} reads outside its facet"
    for detail in d.LEVELS:
        assert d.facets_for(detail, "members") <= d.STRANGER_FACETS
        assert d.facets_for(detail, None) == frozenset()
    assert d.facets_for("full", "friends") == set(d.FACETS) and d.facets_for("story", "friends") == d.STRANGER_FACETS
    assert d.facets_for("piece", "members") == {"identity", "house", "maker"}
    # Second wall: whatever detail a row holds, a stranger's view is cut to the stranger facets.
    row = {c: None for c in d.READ_COLUMNS} | {"item_id": "i", "visible_detail": "full", "title": "t", "claim_level": "tag_verified",
                                              "price_minor": 1, "created_at": datetime(2020, 1, 1), "care_state": "clean"}
    assert set(shown_piece(row, {}, "members")) == {"item_id", "detail"} | d.keys_of(d.STRANGER_FACETS)
    assert set(shown_piece(row, {}, "friends")) == {"item_id", "detail"} | d.keys_of(frozenset(d.FACETS))
    assert shown_piece(row, {}, None) == {"item_id": "i", "detail": "full"}
    # A link share reaches anyone, so it may carry only what a stranger may see.
    assert set(SHAREABLE_FIELDS["wardrobe_item"]) <= d.keys_of(d.STRANGER_FACETS)
    assert set(OUTFIT_ITEM_FIELDS) <= d.keys_of(d.STRANGER_FACETS)


@pytest.fixture
def world(spanner_db):
    db = spanner_db
    owner, friend, stranger = (insert_member(db) for _ in range(3))
    rel = RelationshipService(db)
    rel.accept(member_principal(friend, MEMBER_SCOPES), rel.request(member_principal(owner, MEMBER_SCOPES), friend)["relationship_id"])
    me = member_principal(owner, MEMBER_SCOPES)
    piece = WardrobeService(db).create_items(me, {"source": "manual", "title": "Waxed field jacket", "category": "outerwear",
                                                  "materials": ["waxed cotton"], "colors": ["olive"]}, key())["items"][0]["id"]
    run_txn(db, lambda t: t.update("WardrobeItems", columns=("member_id", "item_id", "product_id", *SECRETS),
                                   values=[(owner, piece, PRODUCT, *SECRETS.values())]))
    by_member = {}

    def resolve(request):
        m = request.headers.get("x-test-member")  # TEST-ONLY resolver; production uses the gateway's assertion
        return member_principal(m, MEMBER_SCOPES) if m else None

    client = TestClient(domain_app.create_app(db, resolve_principal=resolve, catalog=Houses()))
    as_ = {name: (lambda m: (lambda method, path, **kw: client.request(method, path, headers={"x-test-member": m}, **kw)))(m)
           for name, m in (("owner", owner), ("friend", friend), ("stranger", stranger))}
    by_member.update(owner=owner, piece=piece)
    return as_, by_member


def _leaks(body) -> set:
    text = json.dumps(body)
    return {k for k, v in SECRETS.items() if str(v) in text}


def test_strangers_see_the_locked_default_and_nothing_else(world):
    as_, w = world
    owner, piece = w["owner"], w["piece"]
    put = as_["owner"]("PUT", f"/wardrobe/items/{piece}/visibility", json={"visibility": "members", "detail": "story", "showcase_note": "Ten winters"})
    assert put.status_code == 200, put.text
    for viewer in ("stranger", "friend"):
        items = as_[viewer]("GET", f"/members/{owner}/closet").json()["items"]
        assert len(items) == 1 and set(items[0]) == {"item_id", "detail"} | d.keys_of(d.STRANGER_FACETS)
        assert items[0]["house_ref"] == "atelier-disclosure" and items[0]["materials"] == ["waxed cotton"]
        assert items[0]["showcase_note"] == "Ten winters" and not _leaks(items)
    # Strangers can never be given an unfold.
    assert as_["owner"]("PUT", f"/wardrobe/items/{piece}/visibility", json={"visibility": "members", "detail": "full"}).status_code == 422


def test_unfold_reaches_friends_only_and_never_shown_columns_never_appear(world):
    as_, w = world
    owner, piece = w["owner"], w["piece"]
    assert as_["owner"]("PUT", f"/wardrobe/items/{piece}/visibility", json={"visibility": "friends", "detail": "full"}).status_code == 200
    friend = as_["friend"]("GET", f"/members/{owner}/closet").json()["items"]
    assert set(friend[0]) == {"item_id", "detail"} | d.keys_of(frozenset(d.FACETS))
    assert friend[0]["price"]["minor"] == SECRETS["price_minor"] and friend[0]["care_state"] == "in_repair"
    assert _leaks(friend) == {"price_minor", "care_state"}  # exactly the unfolded facets; never-shown columns stay out
    assert as_["stranger"]("GET", f"/members/{owner}/closet").json()["items"] == []
    # The persona card's highlights follow the same rule.
    assert as_["owner"]("PUT", "/me/persona/card", json={"highlight_item_ids": [piece], "audience": "members"}).status_code == 200
    card = as_["stranger"]("GET", f"/members/{owner}/card").json()
    assert card["card"]["highlights"] == [] and not _leaks(card)
    as_["owner"]("PUT", f"/wardrobe/items/{piece}/visibility", json={"visibility": "members", "detail": "piece"})
    card = as_["stranger"]("GET", f"/members/{owner}/card").json()
    assert [set(h) for h in card["card"]["highlights"]] == [{"item_id", "detail"} | d.keys_of(d.LEVELS["piece"])] and not _leaks(card)
