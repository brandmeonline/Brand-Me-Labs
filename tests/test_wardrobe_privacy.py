"""Wardrobe W10 categories: export/delete per category; a deleted proposer is
anonymized in a friend's outfit history instead of erasing the friend's data."""

import uuid
from datetime import datetime, timezone

import pytest

from brandme_core.domains import data_categories
from brandme_core.domains.persona.kernel import NIL_MEMBER, FixedClock, member_principal
from brandme_core.domains.persona.privacy_guard import guard_enforced
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
CATS = {"wardrobe.items", "wardrobe.closet", "wardrobe.outfits", "wardrobe.proposals_authored", "wardrobe.packing"}


def key():
    return "k-" + uuid.uuid4().hex


def test_categories_registered():
    assert {c.name for c in data_categories() if c.domain == "wardrobe"} == CATS


def test_proposer_deletion_anonymizes_attribution_and_owner_keeps_history(spanner_db):
    owner = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    friend = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    w = WardrobeService(spanner_db, clock=FixedClock(NOW))
    o = OutfitService(spanner_db, clock=FixedClock(NOW), proposal_policy=lambda *_: True)
    items = [w.create_items(owner, {"source": "manual", "title": t, "category": "top"}, key())["items"][0]["id"] for t in ("A", "B")]
    outfit = o.create_outfit(owner, {"title": "Look", "item_refs": items[:1]}, key())
    prop = o.propose(friend, outfit["outfit_id"], {"base_version": "1", "item_refs": items, "notes": "add B"}, key())
    o.decide_proposal(owner, outfit["outfit_id"], prop["proposal_id"], "accept", '"1"')
    cats = {c.name: c for c in data_categories() if c.domain == "wardrobe"}
    authored = list(cats["wardrobe.proposals_authored"].export(spanner_db, friend.member_id))
    assert [a["proposal_id"] for a in authored] == [prop["proposal_id"]]
    cats["wardrobe.proposals_authored"].delete(spanner_db, friend.member_id)
    history = o.get_outfit(owner, outfit["outfit_id"])
    assert [v["author_member_id"] for v in history["versions"]] == [owner.member_id, NIL_MEMBER]
    assert history["versions"][1]["item_refs"] == items  # the owner's outfit is intact
    assert list(cats["wardrobe.proposals_authored"].export(spanner_db, friend.member_id)) == []
    cats["wardrobe.items"].delete(spanner_db, owner.member_id)
    assert count(spanner_db, "SELECT COUNT(*) FROM WardrobeItems WHERE member_id=@m", m=owner.member_id) == 0


@pytest.mark.skipif(not guard_enforced(), reason="privacy lane not on this branch; freeze check NOT RUN")
def test_frozen_member_cannot_add_items(spanner_db):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    from brandme_core.domains.persona.kernel import DetailedInvalidTransition, run_txn

    me = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    run_txn(spanner_db, lambda t: t.insert("ProcessingFreezes", columns=("subject_ref", "category", "reason", "deletion_job_id", "created_at"),
                                           values=[(me.member_id, "*", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP)]))
    with pytest.raises(DetailedInvalidTransition) as e:
        WardrobeService(spanner_db).create_items(me, {"source": "manual", "title": "x", "category": "top"}, key())
    assert e.value.code == "processing_frozen"
