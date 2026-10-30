"""Least-disclosure, revocable shares (BM-SOC-010, BM-SOC-011)."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    FixedClock,
    NotFound,
    ValidationFailed,
    member_principal,
    run_txn,
    server_now,
)
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.social.notifications import NotificationService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.social.shares import ShareService, ShareUnavailable, token_hash
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

# Never in any share payload, whatever the request asked for.
FORBIDDEN = ("price", "size", "measure", "address", "receipt", "tag_serial", "owner", "member_id", "asset_instance",
             "wallet", "chain", "variant_ref", "source_ref", "user_notes", "care_notes", "worn", "collection", "Secret")


def key():
    return "k-" + uuid.uuid4().hex


def later(**kw):
    return (datetime.now(timezone.utc) + timedelta(**kw)).isoformat()


def person(db):
    return member_principal(insert_member(db), MEMBER_SCOPES)


@pytest.fixture
def closet(spanner_db):
    owner = person(spanner_db)
    w = WardrobeService(spanner_db)

    def add(title, category, **extra):
        return w.create_items(owner, {"source": "manual", "title": title, "category": category, **extra}, key())["items"][0]["id"]

    shirt = add("Linen shirt", "top", size_label="M", user_notes="Secret note", colors=["white"])
    trousers = add("Chinos", "bottom", size_label="32/34", colors=["khaki"])
    private = add("Private jacket", "outerwear")  # in the closet, never in the outfit
    outfits = OutfitService(spanner_db)
    outfit = outfits.create_outfit(owner, {"title": "Summer lunch", "item_refs": [shirt, trousers], "occasion": "garden party"}, key())
    return owner, w, outfits, outfit["outfit_id"], (shirt, trousers, private)


def assert_clean(obj):
    text = json.dumps(obj)
    for word in FORBIDDEN:
        assert word not in text, f"{word!r} leaked: {text}"


def test_outfit_preview_discloses_only_requested_fields_of_the_outfit(spanner_db, closet):
    """BM-SOC-010."""
    owner, _, _, outfit_id, (shirt, trousers, private) = closet
    shares = ShareService(spanner_db)
    s = shares.create(owner, {"subject_type": "outfit_version", "subject_id": outfit_id, "audience": "unlisted",
                              "allowed_fields": ["title", "items"], "recipient_ids": [], "expires_at": later(days=7)}, key())
    assert s["token"] and len(s["token"]) >= 40 and s["subject_version"] == "1"
    # Anonymous viewer, through the link.
    view = shares.open_by_token(s["token"])
    assert view["fields"] == {"title": "Summer lunch", "items": [
        {"position": 0, "title": "Linen shirt", "category": "top", "color_family": view["fields"]["items"][0]["color_family"], "colors": ["white"]},
        {"position": 1, "title": "Chinos", "category": "bottom", "color_family": view["fields"]["items"][1]["color_family"], "colors": ["khaki"]},
    ]}
    assert_clean(view)
    for ident in (owner.member_id, shirt, trousers, private, "Private jacket", "garden party"):
        assert ident not in json.dumps(view)  # no owner id, closet ids, rest of closet or unrequested occasion
    # Only the hash of the token is stored.
    assert count(spanner_db, "SELECT COUNT(*) FROM ShareGrants WHERE token_hash=@h", h=token_hash(s["token"])) == 1
    with spanner_db.snapshot() as snap:
        stored = json.dumps([list(r) for r in snap.execute_sql("SELECT * FROM ShareGrants")], default=str)
    assert s["token"] not in stored
    with spanner_db.snapshot() as snap:
        idem = json.dumps([list(r) for r in snap.execute_sql("SELECT * FROM IdempotencyRecords")], default=str)
    assert s["token"] not in idem


def test_refuses_fields_outside_the_allowlist(spanner_db, closet):
    owner, _, _, outfit_id, (shirt, _, _) = closet
    shares = ShareService(spanner_db)
    base = {"subject_type": "wardrobe_item", "subject_id": shirt, "audience": "public", "recipient_ids": [], "expires_at": later(days=1)}
    for bad in (["title", "size_label"], ["price_minor"], ["user_notes"], ["member_id"], ["tag_serial_hash"], ["receipt_line_ref"]):
        with pytest.raises(ValidationFailed) as e:
            shares.create(owner, {**base, "allowed_fields": bad}, key())
        assert e.value.extra["refused_fields"] and "title" not in e.value.extra["refused_fields"]
    for bad_type in ("closet_capsule", "badge"):
        with pytest.raises(ValidationFailed) as e:
            shares.create(owner, {**base, "subject_type": bad_type, "allowed_fields": ["title"]}, key())
        assert e.value.extra["code"] == "unsupported_subject_type"
    with pytest.raises(ValidationFailed):  # selected_members needs recipients
        shares.create(owner, {**base, "audience": "selected_members", "allowed_fields": ["title"]}, key())
    with pytest.raises(ValidationFailed):  # expiry too far away
        shares.create(owner, {**base, "allowed_fields": ["title"], "expires_at": later(days=400)}, key())
    with pytest.raises(ValidationFailed):  # someone else's item
        shares.create(person(spanner_db), {**base, "allowed_fields": ["title"]}, key())
    ok = shares.create(owner, {**base, "allowed_fields": ["title", "colors"]}, key())
    assert ok["preview"] == {"title": "Linen shirt", "colors": ["white"]}


def test_revocation_purges_cached_preview_and_blocks_access(spanner_db, closet):
    """BM-SOC-011."""
    owner, _, _, outfit_id, _ = closet
    rel = RelationshipService(spanner_db)
    friend = person(spanner_db)
    rel.accept(friend, rel.request(owner, friend.member_id)["relationship_id"])
    shares = ShareService(spanner_db)
    k = key()
    req = {"subject_type": "outfit_version", "subject_id": outfit_id, "audience": "selected_members",
           "allowed_fields": ["title"], "recipient_ids": [friend.member_id], "expires_at": later(days=1)}
    s = shares.create(owner, req, k)
    # Idempotent replay returns the grant but never the token again.
    replay = shares.create(owner, req, k)
    assert replay["share_id"] == s["share_id"] and replay["token"] is None and replay["token_already_issued"] is True
    assert count(spanner_db, "SELECT COUNT(*) FROM ShareGrants WHERE subject_id=@o", o=outfit_id) == 1
    # Access: the selected friend (by id or link), never an anonymous or unrelated viewer.
    assert shares.open_for_member(friend, s["share_id"])["fields"] == {"title": "Summer lunch"}
    assert shares.open_by_token(s["token"], friend)["fields"] == {"title": "Summer lunch"}
    for viewer in (None, person(spanner_db)):
        with pytest.raises(NotFound):
            shares.open_by_token(s["token"], viewer)
    assert count(spanner_db, "SELECT COUNT(*) FROM SharePreviews WHERE share_id=@s", s=s["share_id"]) == 1
    assert [n["type"] for n in NotificationService(spanner_db).list(friend)["items"]].count("share_received") == 1

    out = shares.revoke(owner, s["share_id"])
    assert out["state"] == "revoked" and out["revoked_at"]
    assert count(spanner_db, "SELECT COUNT(*) FROM SharePreviews WHERE share_id=@s", s=s["share_id"]) == 0
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@s AND event_type='share.revoked'", s=s["share_id"]) == 1
    for call in (lambda: shares.open_for_member(friend, s["share_id"]), lambda: shares.open_by_token(s["token"], friend)):
        with pytest.raises(ShareUnavailable) as e:
            call()
        assert e.value.status == 410 and e.value.extra == {"reason": "revoked"}
    assert "share_received" not in [n["type"] for n in NotificationService(spanner_db).list(friend)["items"]]
    assert shares.revoke(owner, s["share_id"])["state"] == "revoked"  # idempotent, one event
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@s AND event_type='share.revoked'", s=s["share_id"]) == 1
    with pytest.raises(NotFound):  # only the owner can revoke
        shares.revoke(friend, s["share_id"])


def test_expiry_removed_subject_and_unfriending(spanner_db, closet):
    owner, w, outfits, outfit_id, (shirt, _, _) = closet
    shares = ShareService(spanner_db)
    s = shares.create(owner, {"subject_type": "wardrobe_item", "subject_id": shirt, "audience": "public",
                              "allowed_fields": ["title"], "recipient_ids": [], "expires_at": later(minutes=10)}, key())
    assert shares.open_by_token(s["token"])["fields"] == {"title": "Linen shirt"}

    def expire(t):
        t.execute_update("UPDATE ShareGrants SET expires_at=@e WHERE member_id=@m AND share_id=@s",
                         params={"e": server_now(t) - timedelta(microseconds=1), "m": owner.member_id, "s": s["share_id"]},
                         param_types={"e": param_types.TIMESTAMP, "m": param_types.STRING, "s": param_types.STRING})

    run_txn(spanner_db, expire)
    with pytest.raises(ShareUnavailable) as e:
        shares.open_by_token(s["token"])
    assert e.value.extra == {"reason": "expired"}
    assert shares.list(owner)["items"][0]["state"] == "expired"
    # Archiving the item makes an existing share unavailable (current permissions apply).
    s2 = shares.create(owner, {"subject_type": "wardrobe_item", "subject_id": shirt, "audience": "public",
                               "allowed_fields": ["title"], "recipient_ids": [], "expires_at": later(days=1)}, key())
    item = w.get_item(owner, shirt)
    w.archive_item(owner, shirt, f'"{item["version"]}"')
    with pytest.raises(ShareUnavailable) as e:
        shares.open_by_token(s2["token"])
    assert e.value.extra == {"reason": "removed"}
    # Unknown/garbled tokens look like nothing at all.
    for t in ("x" * 43, "short", "é" * 20, None):
        with pytest.raises(NotFound):
            shares.open_by_token(t)
    # Selected-member shares end with the friendship.
    rel = RelationshipService(spanner_db)
    friend = person(spanner_db)
    rel.accept(friend, rel.request(owner, friend.member_id)["relationship_id"])
    s3 = shares.create(owner, {"subject_type": "outfit_version", "subject_id": outfit_id, "audience": "selected_members",
                               "allowed_fields": ["title"], "recipient_ids": [friend.member_id], "expires_at": later(days=1)}, key())
    assert shares.open_for_member(friend, s3["share_id"])
    rel.remove(owner, friend.member_id)
    with pytest.raises(NotFound):
        shares.open_for_member(friend, s3["share_id"])
    with pytest.raises(DetailedInvalidTransition) as e:  # and new shares cannot target non-friends
        shares.create(owner, {"subject_type": "outfit_version", "subject_id": outfit_id, "audience": "selected_members",
                              "allowed_fields": ["title"], "recipient_ids": [friend.member_id], "expires_at": later(days=1)}, key())
    assert e.value.code == "ineligible_recipients"


def test_a_recipient_whose_share_deletion_is_pending_cannot_be_added(spanner_db, closet):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    owner, _, _, outfit_id, _ = closet
    rel = RelationshipService(spanner_db)
    a, b = person(spanner_db), person(spanner_db)
    for f in (a, b):
        rel.accept(f, rel.request(owner, f.member_id)["relationship_id"])
    run_txn(spanner_db, lambda t: t.insert("ProcessingFreezes", columns=("subject_ref", "category", "reason", "deletion_job_id", "created_at"),
                                           values=[(b.member_id, "social.shares", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP)]))
    body = {"subject_type": "outfit_version", "subject_id": outfit_id, "audience": "selected_members", "allowed_fields": ["title"],
            "expires_at": later(days=1)}
    with pytest.raises(DetailedInvalidTransition) as e:
        ShareService(spanner_db).create(owner, {**body, "recipient_ids": [a.member_id, b.member_id]}, key())
    assert e.value.code == "ineligible_recipients" and e.value.extra["ineligible_recipient_ids"] == [b.member_id]
    assert count(spanner_db, "SELECT COUNT(*) FROM ShareGrants WHERE member_id=@m", m=owner.member_id) == 0
    assert ShareService(spanner_db).create(owner, {**body, "recipient_ids": [a.member_id]}, key())["recipient_ids"] == [a.member_id]


def test_persona_snapshot_share_has_declared_axes_only(spanner_db):
    owner = person(spanner_db)
    persona = PersonaService(spanner_db, clock=FixedClock(datetime(2026, 10, 5, 12, tzinfo=timezone.utc)))
    persona.patch(owner, '"0"', {"changes": [{"axis": "expression", "value": 78, "locked": False}], "client_revision": "share-test"})
    snap = persona.create_snapshot(owner, "Autumn")
    shares = ShareService(spanner_db)
    s = shares.create(owner, {"subject_type": "persona_snapshot", "subject_id": snap["snapshot_id"], "audience": "unlisted",
                              "allowed_fields": ["saved_name", "summary", "declared_axes"], "recipient_ids": [],
                              "expires_at": later(days=1)}, key())
    fields = shares.open_by_token(s["token"])["fields"]
    assert fields["saved_name"] == "Autumn" and set(fields) == {"saved_name", "summary", "declared_axes"}
    assert all(v is not None for v in fields["declared_axes"].values())
    with pytest.raises(ValidationFailed):
        shares.create(owner, {"subject_type": "persona_snapshot", "subject_id": snap["snapshot_id"], "audience": "unlisted",
                              "allowed_fields": ["effective_axes"], "recipient_ids": [], "expires_at": later(days=1)}, key())


def test_pd11_override_makes_gone_shares_indistinguishable(spanner_db, closet, monkeypatch):
    from brandme_core.domains.social import policy

    owner, _, _, _, (shirt, _, _) = closet
    shares = ShareService(spanner_db)
    s = shares.create(owner, {"subject_type": "wardrobe_item", "subject_id": shirt, "audience": "public",
                              "allowed_fields": ["title"], "recipient_ids": [], "expires_at": later(days=1)}, key())
    shares.revoke(owner, s["share_id"])
    with pytest.raises(ShareUnavailable):
        shares.open_by_token(s["token"])
    monkeypatch.setattr(policy, "SHARE_GONE_STATUS", 404)
    with pytest.raises(NotFound) as e:
        shares.open_by_token(s["token"])
    assert not isinstance(e.value, ShareUnavailable) and str(e.value) == "share not found"


def test_deleting_shared_source_data_revokes_shares_and_their_previews(spanner_db, closet):
    from brandme_core.domains.persona import deletion as persona_deletion
    from brandme_core.domains.wardrobe import deletion as wardrobe_deletion

    owner, _, _, outfit_id, (shirt, _, _) = closet
    shares = ShareService(spanner_db)
    item_share = shares.create(owner, {"subject_type": "wardrobe_item", "subject_id": shirt, "audience": "public", "allowed_fields": ["title"],
                                       "recipient_ids": [], "expires_at": later(days=1)}, key())
    outfit_share = shares.create(owner, {"subject_type": "outfit_version", "subject_id": outfit_id, "audience": "unlisted",
                                         "allowed_fields": ["title", "items"], "recipient_ids": [], "expires_at": later(days=1)}, key())
    assert shares.open_by_token(outfit_share["token"])["fields"]["items"]
    run_txn(spanner_db, lambda t: wardrobe_deletion.delete_category(t, owner.member_id, "wardrobe.items"))
    for s in (item_share, outfit_share):
        with pytest.raises(ShareUnavailable) as e:
            shares.open_by_token(s["token"])
        assert e.value.extra == {"reason": "revoked"}
    assert count(spanner_db, "SELECT COUNT(*) FROM SharePreviews WHERE member_id=@m", m=owner.member_id) == 0

    persona = PersonaService(spanner_db, clock=FixedClock(datetime(2026, 10, 5, 12, tzinfo=timezone.utc)))
    persona.patch(owner, '"0"', {"changes": [{"axis": "expression", "value": 78, "locked": False}], "client_revision": "del"})
    snap = persona.create_snapshot(owner, "Autumn")
    snap_share = shares.create(owner, {"subject_type": "persona_snapshot", "subject_id": snap["snapshot_id"], "audience": "unlisted",
                                       "allowed_fields": ["declared_axes"], "recipient_ids": [], "expires_at": later(days=1)}, key())
    run_txn(spanner_db, lambda t: persona_deletion.delete_category(t, owner.member_id, "persona.snapshots"))
    with pytest.raises(ShareUnavailable):
        shares.open_by_token(snap_share["token"])
    assert count(spanner_db, "SELECT COUNT(*) FROM SharePreviews WHERE member_id=@m", m=owner.member_id) == 0
