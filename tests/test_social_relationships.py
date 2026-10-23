"""Friendships, blocks and notifications (BM-SOC-001, BM-SOC-009)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.persona.kernel import DetailedInvalidTransition, Forbidden, NotFound, ValidationFailed, member_principal
from brandme_core.domains.social.clock import FixedTxnClock
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.notifications import NotificationService
from brandme_core.domains.social.relationships import RelationshipService, friendship_proposal_policy
from brandme_core.domains.social.shares import ShareService
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def key():
    return "k-" + uuid.uuid4().hex


def person(db):
    return member_principal(insert_member(db), MEMBER_SCOPES)


def befriend(rel, a, b):
    rid = rel.request(a, b.member_id)["relationship_id"]
    rel.accept(b, rid)
    return rid


def test_only_the_intended_recipient_can_accept(spanner_db):
    rel = RelationshipService(spanner_db)
    a, b, c = person(spanner_db), person(spanner_db), person(spanner_db)
    out = rel.request(a, b.member_id)
    rid = out["relationship_id"]
    assert out["state"] == "requested_out"
    # The requester cannot accept their own request, and a third party cannot either.
    for who in (a, c):
        with pytest.raises(NotFound):
            rel.accept(who, rid)
    assert rel.list(b)["items"][0]["state"] == "requested_in"
    # B's request back is redirected to accepting A's request.
    with pytest.raises(DetailedInvalidTransition) as e:
        rel.request(b, a.member_id)
    assert e.value.code == "request_pending_from_them"
    assert rel.accept(b, rid) == {"relationship_id": rid, "state": "accepted"}
    assert rel.accept(b, rid)["state"] == "accepted"  # idempotent
    assert [i["state"] for i in rel.list(a)["items"]] == ["accepted"]
    # C sees nothing of A and B's circle.
    assert rel.list(c)["items"] == []
    # Notifications: B got the request, A got the acceptance; ids/enums only.
    n_b = NotificationService(spanner_db).list(b)["items"]
    assert [n["type"] for n in n_b] == ["friend_request"] and n_b[0]["payload"] == {"relationship_id": rid}
    assert [n["type"] for n in NotificationService(spanner_db).list(a)["items"]] == ["friend_accepted"]


def test_request_guards(spanner_db):
    rel = RelationshipService(spanner_db)
    a = person(spanner_db)
    with pytest.raises(DetailedInvalidTransition):
        rel.request(a, a.member_id)
    with pytest.raises(NotFound):  # unknown member looks like any other unreachable member
        rel.request(a, str(uuid.uuid4()))
    with pytest.raises(NotFound):
        rel.request(a, insert_member(spanner_db, account_state="suspended"))
    with pytest.raises(ValidationFailed):
        rel.request(a, "not-a-uuid")
    reader = member_principal(a.member_id, {"social:read"})
    with pytest.raises(Forbidden):
        rel.request(reader, str(uuid.uuid4()))


def test_friendship_policy_gates_outfit_proposals(spanner_db):
    rel = RelationshipService(spanner_db)
    owner, friend = person(spanner_db), person(spanner_db)
    w = WardrobeService(spanner_db)
    items = [w.create_items(owner, {"source": "manual", "title": t, "category": c}, key())["items"][0]["id"]
             for t, c in (("Shirt", "top"), ("Trousers", "bottom"))]
    outfits = OutfitService(spanner_db, proposal_policy=friendship_proposal_policy)
    oid = outfits.create_outfit(owner, {"title": "Fri", "item_refs": items[:1]}, key())["outfit_id"]
    with pytest.raises(NotFound):
        outfits.propose(friend, oid, {"base_version": "1", "item_refs": items}, key())
    befriend(rel, owner, friend)
    assert outfits.propose(friend, oid, {"base_version": "1", "item_refs": items}, key())["state"] == "pending"
    rel.block(owner, friend.member_id)
    with pytest.raises(NotFound):
        outfits.propose(friend, oid, {"base_version": "1", "item_refs": items[::-1], "layer_order": items}, key())


def test_block_revokes_friendship_decisions_shares_and_pending_notifications(spanner_db):
    """BM-SOC-009."""
    rel = RelationshipService(spanner_db)
    clock = FixedTxnClock(NOW)
    decisions = DecisionService(spanner_db, clock=clock)
    shares = ShareService(spanner_db)
    notes = NotificationService(spanner_db)
    a, b, c = person(spanner_db), person(spanner_db), person(spanner_db)
    befriend(rel, a, b)
    befriend(rel, a, c)
    w = WardrobeService(spanner_db)
    item = w.create_items(a, {"source": "manual", "title": "Coat", "category": "outerwear"}, key())["items"][0]["id"]
    d = decisions.create(a, {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Keep this coat?",
                             "recipient_ids": [b.member_id, c.member_id], "duration_seconds": 300,
                             "discussion_mode": "open"}, key())
    s = shares.create(a, {"subject_type": "wardrobe_item", "subject_id": item, "audience": "selected_members",
                          "allowed_fields": ["title"], "recipient_ids": [b.member_id, c.member_id],
                          "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, key())
    assert shares.open_for_member(b, s["share_id"])["fields"] == {"title": "Coat"}
    assert decisions.get(b, d["decision_id"])["decision_id"] == d["decision_id"]
    assert {n["type"] for n in notes.list(b)["items"]} >= {"decision_request", "share_received"}

    out = rel.block(b, a.member_id)
    assert out["blocked"] and out["audience_removals"] == 1 and out["share_removals"] == 1
    assert out["notifications_withdrawn"] >= 2
    # Pending notifications from A to B are gone; B's own earlier read state is irrelevant.
    assert [n for n in notes.list(b)["items"] if n["type"] in ("decision_request", "share_received")] == []
    # Friendship, decision access and share access are revoked for both directions.
    assert rel.list(a)["items"][0]["member_id"] == c.member_id and len(rel.list(a)["items"]) == 1
    with pytest.raises(NotFound):
        decisions.get(b, d["decision_id"])
    with pytest.raises(NotFound):
        decisions.respond(b, d["decision_id"], {"choice": "yes"})
    with pytest.raises(NotFound):
        shares.open_for_member(b, s["share_id"])
    with pytest.raises(NotFound):
        rel.request(a, b.member_id)
    # C is unaffected.
    assert decisions.respond(c, d["decision_id"], {"choice": "pass"})["revision"] == 1
    assert shares.open_for_member(c, s["share_id"])["fields"] == {"title": "Coat"}
    # A new decision cannot include B; the creator sees B as ineligible.
    with pytest.raises(DetailedInvalidTransition) as e:
        decisions.create(a, {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Again?",
                             "recipient_ids": [b.member_id], "duration_seconds": 300, "discussion_mode": "open"}, key())
    assert e.value.code == "ineligible_recipients"
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE event_type='member.blocked' AND aggregate_id=@b", b=b.member_id) == 1
    # Blocking twice is a no-op; unblocking does not restore friendship.
    assert rel.block(b, a.member_id)["already"] is True
    rel.unblock(b, a.member_id)
    assert all(i["member_id"] != b.member_id for i in rel.list(a)["items"])


def test_notifications_mark_read_only_touches_own_rows(spanner_db):
    rel = RelationshipService(spanner_db)
    notes = NotificationService(spanner_db)
    a, b = person(spanner_db), person(spanner_db)
    rel.request(a, b.member_id)
    nid = notes.list(b)["items"][0]["notification_id"]
    assert notes.mark_read(a, [nid]) == {"marked_read": 0}
    assert notes.mark_read(b, [nid]) == {"marked_read": 1}
    assert notes.list(b)["items"][0]["read_at"] is not None
    with pytest.raises(ValidationFailed):
        notes.mark_read(b, [])
