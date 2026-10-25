"""Small-group rooms (Ultra plan 02 item 7) on the Spanner emulator: invite-only
among friends, at most 12 people, pieces and notes with yes/maybe/no reactions,
blocking honoured, reportable posts, archive."""

from __future__ import annotations

import uuid

import pytest

from brandme_core.domains.persona.kernel import DetailedInvalidTransition, NotFound, RateLimited, ValidationFailed, member_principal
from brandme_core.domains.social.notifications import NotificationService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.social.reports import ReportService
from brandme_core.domains.social.rooms import MAX_MEMBERS, RoomService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

OPS = frozenset({"moderation:admin"})


def key():
    return "k-" + uuid.uuid4().hex


def person(db):
    return member_principal(insert_member(db), MEMBER_SCOPES)


def test_rooms_are_small_private_and_among_friends(spanner_db):
    db = spanner_db
    bride, a, b, stranger = (person(db) for _ in range(4))
    rel = RelationshipService(db)
    for f in (a, b):
        rel.accept(f, rel.request(bride, f.member_id)["relationship_id"])
    rooms = RoomService(db)
    with pytest.raises(DetailedInvalidTransition) as e:
        rooms.create(bride, {"title": "Bridesmaids", "member_ids": [a.member_id, stranger.member_id]}, key())
    assert e.value.code == "not_addable" and e.value.extra["member_ids"] == [stranger.member_id]
    for bad in ({"title": ""}, {"title": "x" * 81}, {"title": "R", "member_ids": [a.member_id, a.member_id]},
                {"title": "R", "member_ids": [str(uuid.uuid4()) for _ in range(MAX_MEMBERS)]}, {"title": "R", "public": True}):
        with pytest.raises(ValidationFailed):
            rooms.create(bride, bad, key())
    with pytest.raises(DetailedInvalidTransition) as e:
        rooms.create(member_principal(bride.member_id, MEMBER_SCOPES, delegation_id=str(uuid.uuid4())), {"title": "R"}, key())
    assert e.value.code == "member_only"

    k = key()
    room = rooms.create(bride, {"title": "Bridesmaids' gowns", "purpose": "Pick by Friday", "member_ids": [a.member_id]}, k)
    assert rooms.create(bride, {"title": "Bridesmaids' gowns", "purpose": "Pick by Friday", "member_ids": [a.member_id]}, k) == room
    rid = room["room_id"]
    assert [n["type"] for n in NotificationService(db).list(a)["items"]].count("room_added") == 1
    with pytest.raises(NotFound):
        rooms.get(stranger, rid)  # outsiders cannot tell the room exists
    with pytest.raises(NotFound):
        rooms.add_member(a, rid, b.member_id)  # only the owner adds
    rooms.add_member(bride, rid, b.member_id)
    assert set(rooms.get(b, rid)["member_ids"]) == {bride.member_id, a.member_id, b.member_id}
    assert {r["room_id"] for r in rooms.mine(b)["items"]} == {rid}

    # Pieces and notes, with one changeable reaction each.
    gown = WardrobeService(db).create_items(a, {"source": "manual", "title": "Sage slip dress", "category": "dress"}, key())["items"][0]["id"]
    with pytest.raises(ValidationFailed):
        rooms.post(b, rid, {"kind": "piece", "subject_type": "wardrobe_item", "subject_id": gown}, key())  # not b's piece
    post = rooms.post(a, rid, {"kind": "piece", "subject_type": "wardrobe_item", "subject_id": gown, "body": "Mine fits; same colour?"}, key())
    note = rooms.post(bride, rid, {"kind": "note", "body": "Sage or dusty blue?"}, key())
    with pytest.raises(ValidationFailed):
        rooms.post(b, rid, {"kind": "note"}, key())
    rooms.react(b, rid, post["post_id"], {"reaction": "maybe"})
    rooms.react(b, rid, post["post_id"], {"reaction": "yes"})
    rooms.react(bride, rid, post["post_id"], {"reaction": "yes"})
    view = {p["post_id"]: p for p in rooms.get(b, rid)["posts"]}
    assert view[post["post_id"]]["reactions"] == {"yes": 2, "maybe": 0, "no": 0} and view[post["post_id"]]["my_reaction"] == "yes"
    with pytest.raises(ValidationFailed):
        rooms.react(b, rid, post["post_id"], {"reaction": "love"})

    # Blocking wins inside the room.
    rel.block(b, a.member_id)
    seen_by_b = rooms.get(b, rid)
    assert post["post_id"] not in {p["post_id"] for p in seen_by_b["posts"]} and a.member_id not in seen_by_b["member_ids"]
    assert rooms.get(bride, rid)["posts"][1]["reactions"]["yes"] == 2  # others still see b's reaction
    with pytest.raises(NotFound):
        rooms.react(b, rid, post["post_id"], {"reaction": "no"})

    # Reports and withdrawal.
    report = ReportService(db).report(bride, {"target_type": "room_post", "target": {"room_id": rid, "post_id": post["post_id"]}, "reason": "spam"})
    with pytest.raises(NotFound):
        ReportService(db).report(stranger, {"target_type": "room_post", "target": {"room_id": rid, "post_id": post["post_id"]}, "reason": "spam"})
    ReportService(db).resolve(member_principal(insert_member(db), OPS), report["report_id"],
                              {"decision": "remove_content", "note": "Off topic"})
    assert {p["post_id"]: p["removed"] for p in rooms.get(bride, rid)["posts"]}[post["post_id"]] is True
    rooms.withdraw(bride, rid, note["post_id"])
    assert count(db, "SELECT COUNT(*) FROM RoomPosts WHERE post_id=@p AND body IS NULL AND removed_reason='author'", p=note["post_id"]) == 1
    with pytest.raises(NotFound):
        rooms.withdraw(a, rid, note["post_id"])  # only the author

    # Leaving, removal and archive.
    with pytest.raises(DetailedInvalidTransition) as e:
        rooms.remove_member(bride, rid, bride.member_id)
    assert e.value.code == "owner_cannot_leave"
    rooms.remove_member(b, rid, b.member_id)
    with pytest.raises(NotFound):
        rooms.get(b, rid)
    rooms.archive(bride, rid)
    with pytest.raises(DetailedInvalidTransition) as e:
        rooms.post(a, rid, {"kind": "note", "body": "late"}, key())
    assert e.value.code == "room_archived"
    assert rooms.get(a, rid)["state"] == "archived"


def test_room_limits(spanner_db):
    db = spanner_db
    owner = person(db)
    rel = RelationshipService(db)
    friends = [person(db) for _ in range(MAX_MEMBERS)]
    for f in friends:
        rel.accept(f, rel.request(owner, f.member_id)["relationship_id"])
    rooms = RoomService(db)
    rid = rooms.create(owner, {"title": "Full house", "member_ids": [f.member_id for f in friends[:MAX_MEMBERS - 1]]}, key())["room_id"]
    with pytest.raises(RateLimited):
        rooms.add_member(owner, rid, friends[-1].member_id)
