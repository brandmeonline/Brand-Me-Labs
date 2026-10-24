"""Member reports and moderation (ch.01 §6.4; console moderation backend)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    Forbidden,
    NotFound,
    ValidationFailed,
    member_principal,
    run_read,
    run_txn,
)
from brandme_core.domains.social import deletion
from brandme_core.domains.social.clock import FixedTxnClock
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.notifications import NotificationService
from brandme_core.domains.social.relationships import RelationshipService, friendship_proposal_policy
from brandme_core.domains.social.reports import ReportService
from brandme_core.domains.social.shares import ShareService, ShareUnavailable
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
OPS = frozenset({"moderation:admin"})


def key():
    return "k-" + uuid.uuid4().hex


def person(db):
    return member_principal(insert_member(db), MEMBER_SCOPES)


@pytest.fixture
def world(spanner_db):
    rel = RelationshipService(spanner_db)
    a, b, c = person(spanner_db), person(spanner_db), person(spanner_db)
    for x, y in ((a, b), (a, c)):
        rel.accept(y, rel.request(x, y.member_id)["relationship_id"])
    item = WardrobeService(spanner_db).create_items(a, {"source": "manual", "title": "Hat", "category": "accessory"}, key())["items"][0]["id"]
    decisions = DecisionService(spanner_db, clock=FixedTxnClock(NOW))
    d = decisions.create(a, {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Hat?", "recipient_ids": [b.member_id, c.member_id],
                             "duration_seconds": 300, "discussion_mode": "open"}, key())
    decisions.respond(b, d["decision_id"], {"choice": "pass", "note": "rude remark"})
    return a, b, c, d, item, decisions


def test_report_visibility_and_dedupe(spanner_db, world):
    a, b, c, d, _, _ = world
    reports = ReportService(spanner_db)
    target = {"decision_id": d["decision_id"], "respondent_id": b.member_id}
    # Creator and fellow audience member can report the response; a stranger cannot even learn it exists.
    r1 = reports.report(a, {"target_type": "decision_response", "target": target, "reason": "harassment", "note": "insulting"})
    assert r1["state"] == "open" and r1["already_reported"] is False and "target_owner_id" not in r1
    assert reports.report(c, {"target_type": "decision_response", "target": target, "reason": "harassment"})["state"] == "open"
    with pytest.raises(NotFound):
        reports.report(person(spanner_db), {"target_type": "decision_response", "target": target, "reason": "spam"})
    again = reports.report(a, {"target_type": "decision_response", "target": target, "reason": "spam"})
    assert again["already_reported"] is True and again["report_id"] == r1["report_id"]
    for bad in ({"target_type": "post", "target": target, "reason": "spam"}, {"target_type": "member", "target": {}, "reason": "spam"},
                {"target_type": "member", "target": {"member_id": b.member_id}, "reason": "boring"}):
        with pytest.raises((ValidationFailed, NotFound)):
            reports.report(a, bad)
    # The reported member is not told who reported them, and sees no report.
    assert reports.my_reports(b)["items"] == []
    assert count(spanner_db, "SELECT COUNT(*) FROM Notifications WHERE member_id=@m AND type LIKE 'report%'", m=b.member_id) == 0


def test_moderation_removes_content_and_notifies_reporter(spanner_db, world):
    a, b, c, d, item, decisions = world
    reports = ReportService(spanner_db)
    ops = member_principal(insert_member(spanner_db), OPS)
    r = reports.report(a, {"target_type": "decision_response", "target": {"decision_id": d["decision_id"], "respondent_id": b.member_id},
                           "reason": "harassment"})
    with pytest.raises(Forbidden):  # members are not moderators
        reports.resolve(a, r["report_id"], {"decision": "dismiss", "note": "x"})
    with pytest.raises(Forbidden):  # nor can a moderator handle a report about themselves
        reports.resolve(member_principal(b.member_id, OPS), r["report_id"], {"decision": "dismiss", "note": "x"})
    queue = [x["report_id"] for x in reports.queue(ops)["items"]]
    assert r["report_id"] in queue
    out = reports.resolve(ops, r["report_id"], {"decision": "remove_content", "note": "Note removed for harassment"})
    assert (out["state"], out["action"], out["resolved_by"]) == ("actioned", "content_removed", ops.actor_ref)
    got = decisions.get(a, d["decision_id"])
    resp = next(x for x in got["responses"] if x["respondent_id"] == b.member_id)
    assert resp["note"] is None and resp["choice"] == "pass"  # the vote stays; the remark is gone
    assert reports.resolve(ops, r["report_id"], {"decision": "dismiss", "note": "again"})["state"] == "actioned"  # resolved once
    notes = NotificationService(spanner_db).list(a)["items"]
    assert any(n["type"] == "report_resolved" and n["payload"] == {"report_id": r["report_id"], "result": "actioned"} for n in notes)
    assert reports.my_reports(a)["items"][0]["state"] == "actioned"


def test_moderation_revokes_shares_and_declines_proposals(spanner_db, world):
    a, b, c, d, item, _ = world
    reports = ReportService(spanner_db)
    ops = member_principal(insert_member(spanner_db), OPS)
    shares = ShareService(spanner_db)
    s = shares.create(a, {"subject_type": "wardrobe_item", "subject_id": item, "audience": "selected_members", "allowed_fields": ["title"],
                          "recipient_ids": [b.member_id], "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, key())
    r = reports.report(b, {"target_type": "share", "target": {"share_id": s["share_id"]}, "reason": "privacy"})
    assert reports.resolve(ops, r["report_id"], {"decision": "remove_content", "note": "Revoked"})["action"] == "share_revoked"
    with pytest.raises(ShareUnavailable):
        shares.open_for_member(b, s["share_id"])
    # A proposal sent to a member can be reported by that member and declined by moderation.
    outfits = OutfitService(spanner_db, proposal_policy=friendship_proposal_policy)
    o = outfits.create_outfit(a, {"title": "Fri", "item_refs": [item]}, key())
    w = WardrobeService(spanner_db)
    other = w.create_items(a, {"source": "manual", "title": "Scarf", "category": "accessory"}, key())["items"][0]["id"]
    p = outfits.propose(b, o["outfit_id"], {"base_version": "1", "item_refs": [item, other], "notes": "spam link"}, key())
    r2 = reports.report(a, {"target_type": "outfit_proposal", "target": {"outfit_id": o["outfit_id"], "proposal_id": p["proposal_id"]},
                            "reason": "spam"})
    assert reports.resolve(ops, r2["report_id"], {"decision": "remove_content", "note": "Spam"})["action"] == "proposal_declined"
    props = {x["proposal_id"]: x for x in outfits.list_proposals(a, o["outfit_id"])}
    assert props[p["proposal_id"]]["state"] == "declined" and props[p["proposal_id"]]["notes"] is None
    # A member report can only be escalated (no account actions here).
    r3 = reports.report(a, {"target_type": "member", "target": {"member_id": c.member_id}, "reason": "spam"})
    with pytest.raises(DetailedInvalidTransition) as e:
        reports.resolve(ops, r3["report_id"], {"decision": "remove_content", "note": "x"})
    assert e.value.code == "nothing_to_remove"
    assert reports.resolve(ops, r3["report_id"], {"decision": "escalate", "note": "Sent to trust & safety"})["action"] == "escalated"


def test_reporter_deletion_anonymizes_reports(spanner_db, world):
    a, b, c, d, _, _ = world
    reports = ReportService(spanner_db)
    target = {"decision_id": d["decision_id"], "respondent_id": b.member_id}
    r1 = reports.report(a, {"target_type": "decision_response", "target": target, "reason": "spam", "note": "my words"})
    r2 = reports.report(c, {"target_type": "decision_response", "target": target, "reason": "spam"})
    assert run_read(spanner_db, lambda s: deletion.export_category(s, a.member_id, "social.reports"))[0]["note"] == "my words"
    for m in (a.member_id, c.member_id):  # two deleted reporters of the same target do not collide
        run_txn(spanner_db, lambda t, m=m: deletion.delete_category(t, m, "social.reports"))
    assert count(spanner_db, "SELECT COUNT(*) FROM MemberReports WHERE reporter_id=@a OR reporter_id=@c", a=a.member_id, c=c.member_id) == 0
    assert count(spanner_db, "SELECT COUNT(*) FROM MemberReports WHERE report_id=@r AND note IS NULL", r=r1["report_id"]) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM MemberReports WHERE report_id=@r", r=r2["report_id"]) == 1
