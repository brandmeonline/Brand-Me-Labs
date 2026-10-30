"""W10 privacy registration for relationships, blocks, decisions, shares,
reports, notifications, rooms and followed houses.

Same pattern as persona/wardrobe: foundation ``register_data_category``
always, the privacy lane's ``DomainPrivacyHandler`` when present.

Cross-member rows: a deleted member's answers on a friend's decision are
erased (the decision keeps its closed tally, which holds no identities);
their membership in others' audiences and share recipient lists is removed;
notifications they caused for others lose the actor reference.
"""

from __future__ import annotations

from typing import Any, Dict, List

from brandme_core.domains import DataCategory as FoundationDataCategory, register_data_category
from brandme_core.domains.persona.kernel import NIL_MEMBER, STR, iso, json_value, query, run_read, run_txn
from brandme_core.domains.persona.privacy_guard import record_scope_refusal

DOMAIN = "social"
_M = {"m": STR}

CATEGORIES: Dict[str, Dict[str, Any]] = {
    "social.relationships": {
        "title": "Friend requests and friendships",
        "supplied_by": "member",
        "retention": "Until you or your friend remove it, or you delete your account",
        "on_edit": "Removing a friend ends shared access for both of you",
        "tables": ("Relationships",),
    },
    "social.blocks": {
        "title": "Members you blocked or muted",
        "supplied_by": "member",
        "retention": "Until you unblock or unmute them, or delete your account",
        "on_edit": "Unblocking does not restore a friendship; a muted member is never told",
        "tables": ("MemberBlocks", "MemberMutes"),
    },
    "social.decisions": {
        "title": "Decisions you asked, answers you gave and comments you wrote",
        "supplied_by": "member",
        "retention": "Until you delete them or your account; closed tallies keep counts only",
        "on_edit": "Answers can change until the deadline, never after",
        "tables": ("Decisions", "DecisionAudience", "DecisionResponses", "DecisionComments"),
    },
    "social.shares": {
        "title": "Shares you created and their previews",
        "supplied_by": "member",
        "retention": "Until they expire, you revoke them or you delete your account",
        "on_edit": "Revoking stops access and removes the preview; downloaded copies cannot be recalled",
        "tables": ("ShareGrants", "SharePreviews"),
    },
    "social.reports": {
        "title": "Reports you filed about content you saw",
        "supplied_by": "member",
        "retention": "Kept for moderation records; your identity is removed when you delete your account",
        "on_edit": "Reports cannot be edited; you can see their outcome",
        "tables": ("MemberReports",),
    },
    "social.notifications": {
        "title": "Your in-app notifications",
        "supplied_by": "system",
        "retention": "Until you delete your account",
        "on_edit": "Blocking withdraws unread notifications between you",
        "tables": ("Notifications",),
    },
    "social.rooms": {
        "title": "Rooms you own or joined, your posts there and your reactions",
        "supplied_by": "member",
        "retention": "Until you leave or delete them, or delete your account; rooms you own close with your account",
        "on_edit": "Withdrawing a post erases its text; leaving a room keeps your posts until you withdraw them",
        "tables": ("Rooms", "RoomMembers", "RoomPosts", "RoomReactions"),
    },
    "social.houses": {
        "title": "Houses you follow and whether each may see your standing",
        "supplied_by": "member",
        "retention": "Until you unfollow or delete your account",
        "on_edit": "Turning sharing off hides your tier from that house at once",
        "tables": ("MemberHouses",),
    },
}


def export_category(snap, member_id: str, category: str) -> List[Dict[str, Any]]:
    m = {"m": member_id}
    if category == "social.relationships":
        return [{"other_member_id": r[0], "relationship_id": r[1], "state": r[2], "created_at": iso(r[3]), "accepted_at": iso(r[4])}
                for r in query(snap, "SELECT other_member_id, relationship_id, state, created_at, accepted_at FROM Relationships "
                                     "WHERE member_id=@m ORDER BY other_member_id", m, _M)]
    if category == "social.blocks":
        return ([{"kind": "block", "blocked_member_id": r[0], "created_at": iso(r[1])}
                 for r in query(snap, "SELECT blocked_member_id, created_at FROM MemberBlocks WHERE member_id=@m ORDER BY blocked_member_id", m, _M)]
                + [{"kind": "mute", "muted_member_id": r[0], "created_at": iso(r[1])}
                   for r in query(snap, "SELECT muted_member_id, created_at FROM MemberMutes WHERE member_id=@m ORDER BY muted_member_id", m, _M)])
    if category == "social.decisions":
        asked = []
        for d in query(snap, "SELECT decision_id, subject_type, subject_id, prompt, discussion_mode, state, opened_at, closes_at, closed_at, "
                             "yes_count, pass_count, alternative_count, requester_outcome, why, duration_seconds FROM Decisions WHERE member_id=@m "
                             "ORDER BY created_at", m, _M):
            asked.append({"decision_id": d[0], "subject_type": d[1], "subject_id": d[2], "prompt": d[3], "discussion_mode": d[4], "state": d[5],
                          "opened_at": iso(d[6]), "closes_at": iso(d[7]), "closed_at": iso(d[8]),
                          "result": {"yes": d[9], "pass": d[10], "alternative": d[11]}, "requester_outcome": d[12], "why": d[13],
                          "duration_seconds": d[14]})
        answered = [{"decision_owner_ref": r[0], "decision_id": r[1], "choice": r[2], "alternative_ref": r[3], "note": r[4],
                     "submitted_at": iso(r[5]), "eligible": r[6]}
                    for r in query(snap, "SELECT member_id, decision_id, choice, alternative_ref, note, submitted_at, eligible FROM DecisionResponses"
                                         "@{FORCE_INDEX=DecisionResponsesByRespondent} WHERE respondent_id=@m ORDER BY submitted_at", m, _M)]
        commented = [{"decision_owner_ref": r[0], "decision_id": r[1], "comment_id": r[2], "body": r[3], "created_at": iso(r[4]),
                      "removed": r[5] is not None}
                     for r in query(snap, "SELECT member_id, decision_id, comment_id, body, created_at, removed_at FROM DecisionComments"
                                          "@{FORCE_INDEX=DecisionCommentsByAuthor} WHERE author_id=@m ORDER BY created_at", m, _M)]
        return [{"asked": asked, "answered": answered, "commented": commented}]
    if category == "social.shares":
        out = []
        for r in query(snap, "SELECT g.share_id, g.subject_type, g.subject_id, g.audience, g.allowed_fields, g.recipient_ids, g.expires_at, "
                             "g.revoked_at, p.preview FROM ShareGrants g LEFT JOIN SharePreviews p ON p.member_id=g.member_id AND p.share_id=g.share_id "
                             "WHERE g.member_id=@m ORDER BY g.created_at", m, _M):
            out.append({"share_id": r[0], "subject_type": r[1], "subject_id": r[2], "audience": r[3], "allowed_fields": list(r[4]),
                        "recipient_ids": list(r[5] or []), "expires_at": iso(r[6]), "revoked_at": iso(r[7]),
                        "preview": None if r[8] is None else json_value(r[8])})
        return out
    if category == "social.reports":
        return [{"report_id": r[0], "target_type": r[1], "target_ref": r[2], "reason": r[3], "note": r[4], "state": r[5], "action": r[6],
                 "created_at": iso(r[7]), "resolved_at": iso(r[8])}
                for r in query(snap, "SELECT report_id, target_type, target_ref, reason, note, state, action, created_at, resolved_at "
                                     "FROM MemberReports WHERE reporter_id=@m ORDER BY created_at", m, _M)]
    if category == "social.notifications":
        return [{"notification_id": r[0], "type": r[1], "subject_ref": r[2], "payload": json_value(r[3]), "created_at": iso(r[4]), "read_at": iso(r[5])}
                for r in query(snap, "SELECT notification_id, type, subject_ref, sanitized_payload, created_at, read_at FROM Notifications "
                                     "WHERE member_id=@m ORDER BY created_at", m, _M)]
    if category == "social.rooms":
        from .rooms import export_rooms

        return export_rooms(snap, member_id)
    if category == "social.houses":
        return [{"house_ref": r[0], "share_standing": r[1], "followed_at": iso(r[2])}
                for r in query(snap, "SELECT house_ref, share_standing, followed_at FROM MemberHouses WHERE member_id=@m ORDER BY house_ref", m, _M)]
    raise KeyError(category)


def delete_category(txn, member_id: str, category: str) -> int:
    m = {"m": member_id}
    if category == "social.relationships":
        return txn.execute_update("DELETE FROM Relationships WHERE member_id=@m OR other_member_id=@m", params=m, param_types=_M)
    if category == "social.blocks":
        n = txn.execute_update("DELETE FROM MemberBlocks WHERE member_id=@m OR blocked_member_id=@m", params=m, param_types=_M)
        return n + txn.execute_update("DELETE FROM MemberMutes WHERE member_id=@m OR muted_member_id=@m", params=m, param_types=_M)
    if category == "social.decisions":
        n = txn.execute_update("DELETE FROM DecisionResponses WHERE respondent_id=@m", params=m, param_types=_M)
        n += txn.execute_update("DELETE FROM DecisionComments WHERE author_id=@m", params=m, param_types=_M)
        n += txn.execute_update("DELETE FROM DecisionAudience WHERE recipient_id=@m", params=m, param_types=_M)
        return n + txn.execute_update("DELETE FROM Decisions WHERE member_id=@m", params=m, param_types=_M)  # audience/responses cascade
    if category == "social.shares":
        from .shares import purge_member_shares

        return purge_member_shares(txn, member_id)
    if category == "social.reports":
        # Anonymize, do not erase: moderation records stay attributable to the outcome, not the person.
        nil = {"m": member_id, "nil": NIL_MEMBER}
        nt = {"m": STR, "nil": STR}
        # The report's own id replaces the reporter (unique per row, so the
        # (reporter, target) unique index cannot collide; unlinkable to the person).
        n = txn.execute_update("UPDATE MemberReports SET reporter_id=report_id, note=NULL WHERE reporter_id=@m",
                               params={"m": member_id}, param_types={"m": STR})
        # Reports about this member keep their outcome; the member's id leaves both
        # the owner and the canonical ref ("member:<id>", ".../response:<id>").
        # The per-report replacement keeps the (reporter, target_ref) index unique.
        return n + txn.execute_update("UPDATE MemberReports SET target_owner_id=@nil, target_ref=REPLACE(target_ref, @m, CONCAT('deleted-', report_id)) "
                                      "WHERE target_owner_id=@m", params=nil, param_types=nt)
    if category == "social.notifications":
        n = txn.execute_update("DELETE FROM Notifications WHERE member_id=@m", params=m, param_types=_M)
        return n + txn.execute_update("UPDATE Notifications SET actor_member_id=NULL WHERE actor_member_id=@m", params=m, param_types=_M)
    if category == "social.rooms":
        from .rooms import delete_rooms

        return delete_rooms(txn, member_id)
    if category == "social.houses":
        return txn.execute_update("DELETE FROM MemberHouses WHERE member_id=@m", params=m, param_types=_M)
    raise KeyError(category)


for _key, _c in CATEGORIES.items():
    register_data_category(FoundationDataCategory(
        name=_key, domain=DOMAIN, description=_c["title"], supplied_by=_c["supplied_by"], visible_to="member only",
        retention=_c["retention"], tables=_c["tables"],
        export=(lambda k: lambda db, mid: run_read(db, lambda s: export_category(s, mid, k)))(_key),
        delete=(lambda k: lambda db, mid: run_txn(db, lambda t: delete_category(t, mid, k)))(_key),
    ))


def build_privacy_handler():
    """A fresh handler instance, or None when the privacy lane is absent."""
    try:
        from brandme_core.domains.privacy import deletion as pd
    except ImportError:
        return None

    class SocialPrivacyHandler:
        domain = DOMAIN

        def categories(self):
            return [
                pd.DataCategory(
                    key=k, domain=DOMAIN, title=c["title"],
                    supplied_by=pd.Supplier.SYSTEM if c["supplied_by"] == "system" else pd.Supplier.MEMBER,
                    visible_to=("member",), retention=c["retention"], on_edit=c["on_edit"],
                    on_delete=pd.OnDelete.ANONYMIZE if k == "social.reports" else pd.OnDelete.ERASE,
                )
                for k, c in CATEGORIES.items()
            ]

        def export(self, snapshot, ctx, category):
            return pd.ExportSection(category, export_category(snapshot, ctx.subject_ref, category))

        def delete(self, txn, ctx, category):
            return record_scope_refusal(pd, ctx, category) or pd.DeletionOutcome(category, delete_category(txn, ctx.subject_ref, category))

        def purge_derived(self, ctx, category):
            # Share previews live in Spanner and go with the grant. Projected recipient copies (Firestore) are
            # removed by the share.revoked / share.audience_changed events written in the deleting transaction.
            return pd.DeletionOutcome(category, 0, done=True, detail="projected share copies removed through the outbox")

        def reapply_tombstone(self, txn, tombstone):
            if tombstone.record_keys:
                return 0  # record-level deletions are refused by delete(); nothing to reapply
            return delete_category(txn, tombstone.subject_ref, tombstone.category)

    return SocialPrivacyHandler()


def _register_default():
    handler = build_privacy_handler()
    if handler is None:
        return None
    from brandme_core.domains.privacy import deletion as pd

    try:
        pd.register_domain(handler)
    except pd.PrivacyRegistryError:
        # Already registered (module re-import) or a lane-local stand-in owns the
        # keys (e.g. the privacy lane's test fixture); never register twice.
        return None
    return handler


PRIVACY_HANDLER = _register_default()
