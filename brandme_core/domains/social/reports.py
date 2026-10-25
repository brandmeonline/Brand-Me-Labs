"""
Member reports and moderation (ch.01 §6.4: report/mute/block on every
member-generated post or comment; console "content moderation").

* A member can report only content they can actually see: a response on a
  decision they created or were invited to, a share sent to them, an outfit
  proposal sent to them, or a member they have a relationship row with
  (e.g. an unwanted friend request). One report per reporter and target;
  at most 20 new reports per reporter per UTC day.
* Reports never hide content automatically and never reveal the reporter
  to the reported member.
* Operators (``moderation:admin``, aal2 outside development, never self)
  resolve with: dismiss, remove content (redact a response note, revoke a
  share, decline and redact a proposal) or escalate (member conduct goes to
  the identity/compliance owners; no account action exists here). Every
  resolution is attributed and notifies the reporter.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    TS,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    RateLimited,
    ValidationFailed,
    command,
    guard_write,
    iso,
    member_active,
    new_id,
    query,
    reject_unknown_keys,
    require_not_self,
    require_operator,
    require_scope,
    require_strict_int,
    require_text,
    require_uuid,
    run_read,
    server_now,
)

from . import events as _events  # noqa: F401
from .notifications import blocked_between, notify
from .shares import revoke_grant

TARGETS = ("decision_response", "decision_comment", "room_post", "share", "outfit_proposal", "member")
REASONS = ("harassment", "spam", "hate", "sexual_content", "self_harm", "privacy", "other")
DAILY_LIMIT = 20
COLS = ("report_id", "reporter_id", "target_type", "target_ref", "target_owner_id", "reason", "note", "state", "action", "resolved_by",
        "resolution_note", "version", "created_at", "resolved_at")


def _dto(r: Mapping[str, Any], *, for_operator: bool) -> Dict[str, Any]:
    out = {k: (iso(v) if k in ("created_at", "resolved_at") else v) for k, v in r.items() if k != "version"}
    out["version"] = str(r["version"])
    if not for_operator:
        out.pop("target_owner_id", None)
        out.pop("resolved_by", None)
    return out


class ReportService:
    def __init__(self, database):
        self.db = database

    # ------------------------------------------------------------- targets

    def _resolve_target(self, txn, reporter: str, target_type: str, target: Mapping[str, Any]) -> Tuple[str, str]:
        """Return (canonical target_ref, content owner) if the reporter can see it; else NotFound."""
        if target_type == "decision_response":
            did = require_uuid(target.get("decision_id"), name="decision_id")
            respondent = require_uuid(target.get("respondent_id"), name="respondent_id")
            d = query(txn, "SELECT member_id FROM Decisions@{FORCE_INDEX=DecisionsById} WHERE decision_id=@d", {"d": did}, {"d": STR})
            if not d:
                raise NotFound("content not found")
            creator = d[0][0]
            sees = creator == reporter or query(txn, "SELECT 1 FROM DecisionAudience WHERE member_id=@c AND decision_id=@d AND recipient_id=@r AND NOT removed",
                                                {"c": creator, "d": did, "r": reporter}, {"c": STR, "d": STR, "r": STR})
            exists = query(txn, "SELECT 1 FROM DecisionResponses WHERE member_id=@c AND decision_id=@d AND respondent_id=@r",
                           {"c": creator, "d": did, "r": respondent}, {"c": STR, "d": STR, "r": STR})
            if not sees or not exists:
                raise NotFound("content not found")
            return f"decision:{did}/response:{respondent}", respondent
        if target_type == "decision_comment":
            did = require_uuid(target.get("decision_id"), name="decision_id")
            cid = require_uuid(target.get("comment_id"), name="comment_id")
            d = query(txn, "SELECT member_id FROM Decisions@{FORCE_INDEX=DecisionsById} WHERE decision_id=@d", {"d": did}, {"d": STR})
            if not d:
                raise NotFound("content not found")
            creator = d[0][0]
            sees = creator == reporter or query(txn, "SELECT 1 FROM DecisionAudience WHERE member_id=@c AND decision_id=@d AND recipient_id=@r AND NOT removed",
                                                {"c": creator, "d": did, "r": reporter}, {"c": STR, "d": STR, "r": STR})
            author = query(txn, "SELECT author_id FROM DecisionComments WHERE member_id=@c AND decision_id=@d AND comment_id=@k AND removed_at IS NULL",
                           {"c": creator, "d": did, "k": cid}, {"c": STR, "d": STR, "k": STR})
            if not sees or not author:
                raise NotFound("content not found")
            return f"decision:{did}/comment:{cid}", author[0][0]
        if target_type == "room_post":
            rid = require_uuid(target.get("room_id"), name="room_id")
            pid = require_uuid(target.get("post_id"), name="post_id")
            member = query(txn, "SELECT 1 FROM RoomMembers WHERE room_id=@r AND member_id=@m", {"r": rid, "m": reporter}, {"r": STR, "m": STR})
            author = query(txn, "SELECT author_id FROM RoomPosts WHERE room_id=@r AND post_id=@p AND removed_at IS NULL",
                           {"r": rid, "p": pid}, {"r": STR, "p": STR})
            if not member or not author:
                raise NotFound("content not found")
            return f"room:{rid}/post:{pid}", author[0][0]
        if target_type == "share":
            sid = require_uuid(target.get("share_id"), name="share_id")
            g = query(txn, "SELECT member_id, recipient_ids FROM ShareGrants@{FORCE_INDEX=ShareGrantsById} WHERE share_id=@s", {"s": sid}, {"s": STR})
            if not g or reporter not in (g[0][1] or []):
                raise NotFound("content not found")
            return f"share:{sid}", g[0][0]
        if target_type == "outfit_proposal":
            oid = require_uuid(target.get("outfit_id"), name="outfit_id")
            pid = require_uuid(target.get("proposal_id"), name="proposal_id")
            p = query(txn, "SELECT proposer_member_id FROM OutfitProposals WHERE member_id=@m AND outfit_id=@o AND proposal_id=@p",
                      {"m": reporter, "o": oid, "p": pid}, {"m": STR, "o": STR, "p": STR})
            if not p:
                raise NotFound("content not found")
            return f"outfit:{oid}/proposal:{pid}", p[0][0]
        other = require_uuid(target.get("member_id"), name="member_id")
        if other == reporter or not query(txn, "SELECT 1 FROM Relationships WHERE member_id=@a AND other_member_id=@b",
                                          {"a": reporter, "b": other}, {"a": STR, "b": STR}) and not blocked_between(txn, reporter, other):
            raise NotFound("member not found")
        return f"member:{other}", other

    # --------------------------------------------------------------- member

    def report(self, principal: Principal, body: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("target_type", "target", "reason", "note"), where="report")
        target_type, reason = body.get("target_type"), body.get("reason")
        if target_type not in TARGETS:
            raise ValidationFailed(f"target_type must be one of {TARGETS}", extra={"field": "target_type"})
        if reason not in REASONS:
            raise ValidationFailed(f"reason must be one of {REASONS}", extra={"field": "reason"})
        target = body.get("target")
        if not isinstance(target, Mapping):
            raise ValidationFailed("target must be an object", extra={"field": "target"})
        note = require_text(body["note"], name="note", max_len=500) if body.get("note") is not None else None
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, me):
                raise NotFound("member not found")
            guard_write(txn, me, "social.reports")
            ref, owner = self._resolve_target(txn, me, target_type, target)
            existing = query(txn, f"SELECT {', '.join(COLS)} FROM MemberReports@{{FORCE_INDEX=MemberReportsByReporterTarget}} "
                                  "WHERE reporter_id=@r AND target_ref=@t", {"r": me, "t": ref}, {"r": STR, "t": STR})
            if existing:
                return {**_dto(dict(zip(COLS, existing[0])), for_operator=False), "already_reported": True}
            now = server_now(txn)
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if query(txn, "SELECT COUNT(*) FROM MemberReports@{FORCE_INDEX=MemberReportsByReporterTarget} WHERE reporter_id=@r AND created_at >= @d",
                     {"r": me, "d": day}, {"r": STR, "d": TS})[0][0] >= DAILY_LIMIT:
                raise RateLimited("you have sent many reports today; we are reviewing them", extra={"limit": "daily_reports"})
            r = {"report_id": new_id(), "reporter_id": me, "target_type": target_type, "target_ref": ref, "target_owner_id": owner,
                 "reason": reason, "note": note, "state": "open", "action": None, "resolved_by": None, "resolution_note": None, "version": 1}
            txn.insert("MemberReports", columns=(*COLS[:-2], "created_at"), values=[[*(r[c] for c in COLS[:-2]), COMMIT_TIMESTAMP]])
            ctx.emit("moderation.report.opened", "1", "member_report", r["report_id"], 1,
                     {"report_id": r["report_id"], "target_type": target_type}, "restricted")
            return {**_dto({**r, "created_at": now, "resolved_at": None}, for_operator=False), "already_reported": False}

        return command(self.db, principal, tx)

    def my_reports(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "social:read")
        rows = run_read(self.db, lambda s: query(
            s, f"SELECT {', '.join(COLS)} FROM MemberReports@{{FORCE_INDEX=MemberReportsByReporterTarget}} WHERE reporter_id=@r ORDER BY created_at DESC LIMIT 100",
            {"r": principal.member_id}, {"r": STR}))
        return {"items": [_dto(dict(zip(COLS, r)), for_operator=False) for r in rows], "next_cursor": None}

    # ------------------------------------------------------------- operator

    def queue(self, operator: Principal, *, state: str = "open", limit: int = 50) -> Dict[str, Any]:
        require_operator(operator)
        if state not in ("open", "actioned", "dismissed"):
            raise ValidationFailed("unknown state", extra={"field": "state"})
        limit = require_strict_int(limit, name="limit", lo=1, hi=100)
        rows = run_read(self.db, lambda s: query(
            s, f"SELECT {', '.join(COLS)} FROM MemberReports@{{FORCE_INDEX=MemberReportsByState}} WHERE state=@s ORDER BY created_at LIMIT @n",
            {"s": state, "n": limit}, {"s": STR, "n": INT}))
        return {"items": [_dto(dict(zip(COLS, r)), for_operator=True) for r in rows], "next_cursor": None}

    def resolve(self, operator: Principal, report_id: Any, body: Any) -> Dict[str, Any]:
        require_operator(operator)
        report_id = require_uuid(report_id, name="report_id")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("decision", "note"), where="resolution")
        decision = body.get("decision")
        if decision not in ("dismiss", "remove_content", "escalate"):
            raise ValidationFailed("decision must be dismiss, remove_content or escalate", extra={"field": "decision"})
        note = require_text(body.get("note"), name="note", max_len=1000)

        def tx(txn, ctx: CommandContext):
            rows = query(txn, f"SELECT {', '.join(COLS)} FROM MemberReports WHERE report_id=@r", {"r": report_id}, {"r": STR})
            if not rows:
                raise NotFound("report not found")
            r = dict(zip(COLS, rows[0]))
            require_not_self(operator, r["reporter_id"])
            require_not_self(operator, r["target_owner_id"])
            if r["state"] != "open":
                return _dto(r, for_operator=True)
            action = {"dismiss": "none", "escalate": "escalated"}.get(decision) or self._remove(txn, ctx, r)
            state = "dismissed" if decision == "dismiss" else "actioned"
            txn.update("MemberReports", columns=("report_id", "state", "action", "resolved_by", "resolution_note", "version", "resolved_at"),
                       values=[(report_id, state, action, operator.actor_ref, note, r["version"] + 1, COMMIT_TIMESTAMP)])
            ev = ctx.emit("moderation.report.resolved", "1", "member_report", report_id, r["version"] + 1,
                          {"report_id": report_id, "state": state, "action": action}, "restricted")
            notify(txn, recipient_id=r["reporter_id"], event_id=ev.event_id, type_="report_resolved", actor_member_id=None,
                   subject_ref=f"report:{report_id}", payload={"report_id": report_id, "result": state})
            r.update(state=state, action=action, resolved_by=operator.actor_ref, resolution_note=note, version=r["version"] + 1)
            return _dto(r, for_operator=True)

        return command(self.db, operator, tx)

    def _remove(self, txn, ctx: CommandContext, r: Mapping[str, Any]) -> str:
        ref = r["target_ref"]
        if r["target_type"] == "decision_response":
            did, respondent = ref.split("/")[0].split(":")[1], ref.split("/")[1].split(":")[1]
            creator = query(txn, "SELECT member_id FROM Decisions@{FORCE_INDEX=DecisionsById} WHERE decision_id=@d", {"d": did}, {"d": STR})
            if creator:
                txn.execute_update("UPDATE DecisionResponses SET note = NULL WHERE member_id=@c AND decision_id=@d AND respondent_id=@r",
                                   params={"c": creator[0][0], "d": did, "r": respondent}, param_types={"c": STR, "d": STR, "r": STR})
            return "content_removed"
        if r["target_type"] == "decision_comment":
            did, cid = ref.split("/")[0].split(":")[1], ref.split("/")[1].split(":")[1]
            creator = query(txn, "SELECT member_id FROM Decisions@{FORCE_INDEX=DecisionsById} WHERE decision_id=@d", {"d": did}, {"d": STR})
            if creator:
                txn.execute_update("UPDATE DecisionComments SET body = '', removed_at = CURRENT_TIMESTAMP(), removed_reason = 'moderation' "
                                   "WHERE member_id=@c AND decision_id=@d AND comment_id=@k AND removed_at IS NULL",
                                   params={"c": creator[0][0], "d": did, "k": cid}, param_types={"c": STR, "d": STR, "k": STR})
            return "content_removed"
        if r["target_type"] == "room_post":
            rid, pid = ref.split("/")[0].split(":")[1], ref.split("/")[1].split(":")[1]
            txn.execute_update("UPDATE RoomPosts SET body = NULL, subject_type = NULL, subject_id = NULL, kind = 'note', "
                               "removed_at = CURRENT_TIMESTAMP(), removed_reason = 'moderation' WHERE room_id=@r AND post_id=@p AND removed_at IS NULL",
                               params={"r": rid, "p": pid}, param_types={"r": STR, "p": STR})
            return "content_removed"
        if r["target_type"] == "share":
            from .shares import GRANT_COLS

            sid = ref.split(":")[1]
            g = query(txn, f"SELECT {', '.join(GRANT_COLS)} FROM ShareGrants@{{FORCE_INDEX=ShareGrantsById}} WHERE share_id=@s", {"s": sid}, {"s": STR})
            if g:
                revoke_grant(txn, ctx, dict(zip(GRANT_COLS, g[0])))
            return "share_revoked"
        if r["target_type"] == "outfit_proposal":
            oid, pid = ref.split("/")[0].split(":")[1], ref.split("/")[1].split(":")[1]
            rows = query(txn, "SELECT p.member_id, p.state FROM OutfitProposals p JOIN Outfits@{FORCE_INDEX=OutfitsByOutfitId} o "
                              "ON o.member_id = p.member_id AND o.outfit_id = p.outfit_id WHERE o.outfit_id=@o AND p.proposal_id=@p",
                         {"o": oid, "p": pid}, {"o": STR, "p": STR})
            if rows:
                owner, state = rows[0]
                if state == "pending":
                    txn.update("OutfitProposals", columns=("member_id", "outfit_id", "proposal_id", "notes", "state", "decided_at"),
                               values=[(owner, oid, pid, None, "declined", COMMIT_TIMESTAMP)])
                else:
                    txn.update("OutfitProposals", columns=("member_id", "outfit_id", "proposal_id", "notes"), values=[(owner, oid, pid, None)])
            return "proposal_declined"
        raise DetailedInvalidTransition("member conduct has no content to remove here; escalate it", code="nothing_to_remove")


def report_status_for_member(snap, member_id: str, report_id: str) -> Optional[Dict[str, Any]]:
    rows = query(snap, f"SELECT {', '.join(COLS)} FROM MemberReports WHERE report_id=@r AND reporter_id=@m", {"r": report_id, "m": member_id},
                 {"r": STR, "m": STR})
    return _dto(dict(zip(COLS, rows[0])), for_operator=False) if rows else None
