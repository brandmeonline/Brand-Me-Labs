"""HTTP contract of the unmounted wardrobe router + guest-migration sections."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import brandme_core.domains.wardrobe  # noqa: F401  (registers guest sections)
from brandme_core.domains.persona.api import create_persona_router
from brandme_core.domains.persona.kernel import FixedClock, member_principal
from brandme_core.domains.persona.onboarding import GuestMigrationService
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.wardrobe.api import create_wardrobe_router
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.rooms import ROOMS
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
SHIRT = "a4036cb0-7ab2-54b5-9238-ee5ffb378771"


def resolve(request):
    mid = request.headers.get("x-test-member")
    return member_principal(mid, MEMBER_SCOPES) if mid else None


@pytest.fixture
def client(spanner_db):
    w = WardrobeService(spanner_db, clock=FixedClock(NOW))
    persona = PersonaService(spanner_db, clock=FixedClock(NOW), wardrobe_source=w.wardrobe_refs)
    app = FastAPI()
    app.include_router(create_wardrobe_router(w, OutfitService(spanner_db, clock=FixedClock(NOW)), resolve))
    app.include_router(create_persona_router(persona, GuestMigrationService(spanner_db, persona), resolve))
    return TestClient(app)


def h(mid, **kw):
    return {"x-test-member": mid, **{k.replace("_", "-"): v for k, v in kw.items()}}


def key():
    return "k-" + uuid.uuid4().hex


def test_create_place_and_reject_non_finite_json(client, spanner_db):
    mid = insert_member(spanner_db)
    r = client.post("/wardrobe/items", json={"source": "manual", "title": "Shirt", "category": "top"}, headers=h(mid, idempotency_key=key()))
    assert r.status_code == 201
    item = r.json()["items"][0]["id"]
    g = ROOMS["walnut_atelier"].groups["rail.left"]
    raw = ('{"room_template_id":"walnut_atelier","semantic_group":"rail.left","slot_id":"0","position_meters":[NaN,1.75,-0.65],'
           '"rotation_quaternion":[0,0,0,1],"uniform_scale":1,"asset_revision":"original-shelves-v2"}')
    bad = client.put(f"/closet/placements/{item}", content=raw.encode(), headers={**h(mid, if_match='"0"'), "content-type": "application/json"})
    assert bad.status_code == 422 and bad.headers["content-type"].startswith("application/problem+json")
    inf = client.put(f"/closet/placements/{item}", content=raw.replace("NaN", "Infinity").encode(), headers={**h(mid, if_match='"0"'), "content-type": "application/json"})
    assert inf.status_code == 422
    ok = client.put(f"/closet/placements/{item}", json={"room_template_id": "walnut_atelier", "semantic_group": "rail.left", "slot_id": "0",
                                                        "position_meters": list(g.slot_position("0")), "rotation_quaternion": [0, 0, 0, 1],
                                                        "uniform_scale": 1, "asset_revision": "original-shelves-v2"}, headers=h(mid, if_match='"0"'))
    assert ok.status_code == 200 and ok.headers["etag"] == '"1"'
    stale = client.put(f"/closet/placements/{item}", json={"room_template_id": "walnut_atelier", "semantic_group": None, "asset_revision": "original-shelves-v2"},
                       headers=h(mid, if_match='"0"'))
    assert stale.status_code == 409 and stale.json()["current_placement"]["slot_id"] == "0"
    assert client.get("/closet/layout", headers=h(mid)).json()["placements"][0]["wardrobe_item_id"] == item


def test_guest_migration_moves_profile_room_and_saved_products_atomically(client, spanner_db):
    mid = insert_member(spanner_db)
    body = {
        "guest_namespace_id": "guest-" + uuid.uuid4().hex,
        "persona": {"declared": {"expression": {"value": 72, "locked": True}}},
        "saved_look": True,
        "sections": {
            "closet_theme": {"room_template_id": "garden_studio"},
            "saved_products": [{"product_id": SHIRT, "title": "Field Linen Overshirt", "category": "top", "variant_ref": "v-M"}],
        },
    }
    first = client.post("/me/guest-migration", json=body, headers=h(mid, idempotency_key=key())).json()
    assert first["status"] == "migrated"
    assert first["sections"] == {"closet_theme": {"closet_theme": "garden_studio"}, "saved_products": {"saved_products_added": 1, "already_saved": 0}}
    again = client.post("/me/guest-migration", json=body, headers=h(mid, idempotency_key=key())).json()
    assert again["status"] == "already_migrated"
    items = client.get("/wardrobe/items", headers=h(mid)).json()["items"]
    assert [(i["collection"], i["acquisition_source"], i["product_id"]) for i in items] == [("want", "guest", SHIRT)]
    assert client.get("/closet/layout", headers=h(mid)).json()["room_template_id"] == "garden_studio"
    # A failing section rolls back the whole migration (persona included).
    other = insert_member(spanner_db)
    broken = {**body, "guest_namespace_id": "guest-" + uuid.uuid4().hex,
              "sections": {"saved_products": [{"product_id": SHIRT, "title": "x", "category": "hat"}]}}
    r = client.post("/me/guest-migration", json=broken, headers=h(other, idempotency_key=key()))
    assert r.status_code == 422
    assert client.get("/me/persona", headers=h(other)).json()["exists"] is False
    assert count(spanner_db, "SELECT COUNT(*) FROM WardrobeItems WHERE member_id=@m", m=other) == 0
