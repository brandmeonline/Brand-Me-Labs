"""Social privacy categories (W10 export/delete) and the unmounted HTTP router."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brandme_core.domains import data_categories
from brandme_core.domains.persona.kernel import member_principal, run_read, run_txn
from brandme_core.domains.persona.privacy_guard import guard_enforced
from brandme_core.domains.social import deletion
from brandme_core.domains.social.api import create_social_router
from brandme_core.domains.social.clock import FixedTxnClock
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.notifications import NotificationService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.social.shares import ShareService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def key():
    return "k-" + uuid.uuid4().hex


def person(db):
    return member_principal(insert_member(db), MEMBER_SCOPES)


def later(**kw):
    return (datetime.now(timezone.utc) + timedelta(**kw)).isoformat()


def test_categories_registered_with_foundation():
    names = {c.name for c in data_categories() if c.domain == "social"}
    assert names == set(deletion.CATEGORIES)


def test_export_then_delete_member_social_data(spanner_db):
    rel = RelationshipService(spanner_db)
    clock = FixedTxnClock(NOW)
    decisions = DecisionService(spanner_db, clock=clock)
    shares = ShareService(spanner_db)
    gone, friend, other = person(spanner_db), person(spanner_db), person(spanner_db)
    for a, b in ((gone, friend), (friend, other), (gone, other)):
        rel.accept(b, rel.request(a, b.member_id)["relationship_id"])
    rel.block(gone, insert_member(spanner_db))
    w = WardrobeService(spanner_db)
    g_item = w.create_items(gone, {"source": "manual", "title": "Hat", "category": "accessory"}, key())["items"][0]["id"]
    f_item = w.create_items(friend, {"source": "manual", "title": "Scarf", "category": "accessory"}, key())["items"][0]["id"]
    mine = decisions.create(gone, {"subject_type": "wardrobe_item", "subject_id": g_item, "prompt": "Hat?", "recipient_ids": [friend.member_id],
                                   "duration_seconds": 300, "discussion_mode": "open"}, key())
    theirs = decisions.create(friend, {"subject_type": "wardrobe_item", "subject_id": f_item, "prompt": "Scarf?",
                                       "recipient_ids": [gone.member_id, other.member_id], "duration_seconds": 300, "discussion_mode": "open"}, key())
    decisions.respond(gone, theirs["decision_id"], {"choice": "yes", "note": "Nice"})
    decisions.respond(other, theirs["decision_id"], {"choice": "pass"})
    clock.set(NOW + timedelta(seconds=300))
    decisions.close_due()
    shares.create(gone, {"subject_type": "wardrobe_item", "subject_id": g_item, "audience": "unlisted", "allowed_fields": ["title"],
                         "recipient_ids": [], "expires_at": later(days=1)}, key())
    fshare = shares.create(friend, {"subject_type": "wardrobe_item", "subject_id": f_item, "audience": "selected_members",
                                    "allowed_fields": ["title"], "recipient_ids": [gone.member_id, other.member_id], "expires_at": later(days=1)}, key())

    exported = {c: run_read(spanner_db, lambda s, c=c: deletion.export_category(s, gone.member_id, c)) for c in deletion.CATEGORIES}
    assert {r["other_member_id"] for r in exported["social.relationships"]} == {friend.member_id, other.member_id}
    assert len(exported["social.blocks"]) == 1
    assert [d["decision_id"] for d in exported["social.decisions"][0]["asked"]] == [mine["decision_id"]]
    assert [(a["decision_id"], a["choice"], a["note"]) for a in exported["social.decisions"][0]["answered"]] == [(theirs["decision_id"], "yes", "Nice")]
    assert exported["social.shares"][0]["preview"] == {"title": "Hat"}
    assert {n["type"] for n in exported["social.notifications"]} >= {"friend_accepted", "decision_request", "decision_closed", "share_received"}

    for c in deletion.CATEGORIES:
        run_txn(spanner_db, lambda t, c=c: deletion.delete_category(t, gone.member_id, c))
    m = gone.member_id
    for sql in ("SELECT COUNT(*) FROM Relationships WHERE member_id=@m OR other_member_id=@m",
                "SELECT COUNT(*) FROM MemberBlocks WHERE member_id=@m OR blocked_member_id=@m",
                "SELECT COUNT(*) FROM Decisions WHERE member_id=@m",
                "SELECT COUNT(*) FROM DecisionResponses WHERE respondent_id=@m",
                "SELECT COUNT(*) FROM DecisionAudience WHERE recipient_id=@m",
                "SELECT COUNT(*) FROM ShareGrants WHERE member_id=@m OR @m IN UNNEST(recipient_ids)",
                "SELECT COUNT(*) FROM SharePreviews WHERE member_id=@m",
                "SELECT COUNT(*) FROM Notifications WHERE member_id=@m OR actor_member_id=@m"):
        assert count(spanner_db, sql, m=m) == 0, sql
    # The friend's closed decision keeps its count-only tally and the other respondent.
    got = decisions.get(friend, theirs["decision_id"])
    assert got["result"]["yes"] == 1 and [r["respondent_id"] for r in got["responses"]] == [other.member_id]
    # The friend's share still works for the remaining recipient.
    assert shares.open_for_member(other, fshare["share_id"])["fields"] == {"title": "Scarf"}
    # Idempotent: a second pass deletes nothing.
    assert sum(run_txn(spanner_db, lambda t, c=c: deletion.delete_category(t, m, c)) for c in deletion.CATEGORIES) == 0


def resolve(request):
    mid = request.headers.get("x-test-member")
    return member_principal(mid, MEMBER_SCOPES) if mid else None


@pytest.fixture
def client(spanner_db):
    app = FastAPI()
    app.include_router(create_social_router(RelationshipService(spanner_db), DecisionService(spanner_db), ShareService(spanner_db),
                                            NotificationService(spanner_db), resolve))
    return TestClient(app)


def h(mid, **kw):
    return {"x-test-member": mid, **kw}


def test_http_flow(spanner_db, client):
    a, b = insert_member(spanner_db), insert_member(spanner_db)
    assert client.get("/relationships").status_code == 401
    r = client.post("/relationships", json={"target_member_id": b}, headers=h(a))
    assert r.status_code == 201 and r.headers["cache-control"] == "private, no-store"
    assert client.post("/relationships", json={"target_member_id": b, "as": a}, headers=h(a)).status_code == 422
    rid = r.json()["relationship_id"]
    assert client.post(f"/relationships/{rid}/accept", headers=h(a)).status_code == 404
    assert client.post(f"/relationships/{rid}/accept", headers=h(b)).json()["state"] == "accepted"
    item = WardrobeService(spanner_db).create_items(member_principal(a, MEMBER_SCOPES),
                                                    {"source": "manual", "title": "Boots", "category": "shoes"}, key())["items"][0]["id"]
    body = {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "These?", "recipient_ids": [b],
            "duration_seconds": 300, "discussion_mode": "open"}
    assert client.post("/decisions", json=body, headers=h(a)).status_code == 400  # Idempotency-Key required
    d = client.post("/decisions", json=body, headers=h(a, **{"Idempotency-Key": key()}))
    assert d.status_code == 201, d.text
    did = d.json()["decision_id"]
    nan = client.post(f"/decisions/{did}/responses", content=b'{"choice": NaN}', headers=h(b, **{"content-type": "application/json"}))
    assert nan.status_code == 422 and nan.headers["content-type"] == "application/problem+json"
    assert client.post(f"/decisions/{did}/responses", json={"choice": "yes"}, headers=h(b)).json()["revision"] == 1
    stranger = insert_member(spanner_db)
    assert client.get(f"/decisions/{did}", headers=h(stranger)).status_code == 404
    assert client.get("/decisions?role=invited", headers=h(b)).json()["items"][0]["decision_id"] == did

    s = client.post("/shares", json={"subject_type": "wardrobe_item", "subject_id": item, "audience": "unlisted", "allowed_fields": ["title"],
                                     "recipient_ids": [], "expires_at": later(days=2)}, headers=h(a, **{"Idempotency-Key": key()}))
    assert s.status_code == 201, s.text
    token, sid = s.json()["token"], s.json()["share_id"]
    anon = client.post("/shares/resolve", json={"token": token})  # no session: allowed for link shares
    assert anon.status_code == 200 and anon.json()["fields"] == {"title": "Boots"}
    assert client.get(f"/shares/{sid}", headers=h(b)).status_code == 404  # link shares need the token
    assert client.delete(f"/shares/{sid}", headers=h(b)).status_code == 404
    assert client.delete(f"/shares/{sid}", headers=h(a)).json()["state"] == "revoked"
    gone = client.post("/shares/resolve", json={"token": token})
    assert gone.status_code == 410 and gone.json()["code"] == "share_unavailable" and gone.json()["reason"] == "revoked"
    assert client.post("/shares/resolve", json={"token": "x" * 43}).status_code == 404

    notes = client.get("/notifications", headers=h(a)).json()["items"]
    assert {n["type"] for n in notes} >= {"friend_accepted", "decision_response"}
    assert client.post("/notifications/read", json={"ids": [notes[0]["notification_id"]]}, headers=h(a)).json() == {"marked_read": 1}
    assert client.post("/blocks", json={"target_member_id": b}, headers=h(a)).json()["blocked"] is True


@pytest.mark.skipif(not guard_enforced(), reason="privacy lane not on this branch; freeze/registration check NOT RUN")
def test_privacy_lane_handler_and_freeze(spanner_db):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    from brandme_core.domains.persona.kernel import DetailedInvalidTransition

    assert deletion.PRIVACY_HANDLER is not None
    assert {c.key for c in deletion.PRIVACY_HANDLER.categories()} == set(deletion.CATEGORIES)
    me = person(spanner_db)
    item = WardrobeService(spanner_db).create_items(me, {"source": "manual", "title": "Cap", "category": "accessory"}, key())["items"][0]["id"]
    run_txn(spanner_db, lambda t: t.insert("ProcessingFreezes", columns=("subject_ref", "category", "reason", "deletion_job_id", "created_at"),
                                           values=[(me.member_id, "*", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP)]))
    with pytest.raises(DetailedInvalidTransition) as e:
        ShareService(spanner_db).create(me, {"subject_type": "wardrobe_item", "subject_id": item, "audience": "unlisted",
                                             "allowed_fields": ["title"], "recipient_ids": [], "expires_at": later(days=1)}, key())
    assert e.value.code == "processing_frozen"
