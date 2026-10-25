"""
Member-facing reads, member disputes and operator/reviewer commands.

No member-callable path awards points (BM-LOY-005). Points come only from
``RewardsConsumer`` (committed domain events), from a reviewer accepting an
evidenced contribution, from an approved repair workflow, or from an
operator correction tied to a dispute, always as a reasoned ledger entry.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    TS,
    CommandContext,
    DetailedInvalidTransition,
    Forbidden,
    NotFound,
    Principal,
    ServicePrincipal,
    ValidationFailed,
    command,
    decode_cursor,
    encode_cursor,
    guard_write,
    iso,
    member_active,
    new_id,
    query,
    reject_unknown_keys,
    require_scope,
    require_strict_int,
    require_text,
    require_uuid,
    run_read,
    server_now,
)

from . import badges, ledger
from .operators import require_not_self, require_operator
from .rules import BADGES, CLOSET_CURATOR_ITEMS, RULES, STYLE_COLLABORATOR_ACCEPTED, TRUSTED_EYE_RESPONSES

DISPUTE_CATEGORIES = ("missing_reward", "wrong_amount", "reversal", "reservation", "other")
MAX_OPEN_DISPUTES = 5
ENTRY_LIST_COLS = ("entry_id", "kind", "state", "rule_id", "rule_version", "points", "available_delta", "reserved_delta", "recovery_delta",
                   "outcome_reason", "reverses_entry_id", "reservation_id", "evidence_refs", "reason", "created_at")
DISPUTE_COLS = ("member_id", "dispute_id", "entry_id", "category", "message", "state", "resolution_note", "resolved_by",
                "correction_entry_id", "version", "created_at", "resolved_at")


def _entry_dto(r: Mapping[str, Any]) -> Dict[str, Any]:
    return {"entry_id": r["entry_id"], "kind": r["kind"], "state": r["state"], "rule_id": r["rule_id"],
            "rule_version": r["rule_version"], "points": r["points"], "available_change": r["available_delta"],
            "reserved_change": r["reserved_delta"], "recovery_due_change": r["recovery_delta"],
            "reason": r["outcome_reason"] or r["reason"], "reverses_entry_id": r["reverses_entry_id"],
            "reservation_id": r["reservation_id"], "evidence_refs": list(r["evidence_refs"]), "created_at": iso(r["created_at"])}


def _dispute_dto(r: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: (iso(v) if k in ("created_at", "resolved_at") else (str(v) if k == "version" else v)) for k, v in r.items()}


class RewardsService:
    def __init__(self, database, *, approved_repair_issuers: FrozenSet[str] = frozenset()):
        self.db = database
        # No approved repair workflow exists yet; repairs are refused until one is configured.
        self.approved_repair_issuers = frozenset(approved_repair_issuers)

    # ----------------------------------------------------------- member reads

    def _progress(self, s, member_id: str, earned: Dict[str, bool]) -> List[Dict[str, Any]]:
        f = ledger.facts(s, member_id)
        placed = query(s, "SELECT COUNT(*) FROM ClosetPlacements p JOIN WardrobeItems i ON i.member_id=p.member_id AND i.item_id=p.item_id "
                          "WHERE p.member_id=@m AND p.semantic_group IS NOT NULL AND i.collection='owned'", {"m": member_id}, {"m": STR})[0][0]
        counts = {
            "first_reflection": (int("profile_saved" in f), 1),
            "closet_curator": (min(placed, CLOSET_CURATOR_ITEMS), CLOSET_CURATOR_ITEMS),
            "trusted_eye": (min(len(ledger.active_entries(s, member_id, "friend_decision_response")), TRUSTED_EYE_RESPONSES), TRUSTED_EYE_RESPONSES),
            "style_collaborator": (min(len(ledger.active_entries(s, member_id, "styling_proposal_accepted")), STYLE_COLLABORATOR_ACCEPTED),
                                   STYLE_COLLABORATOR_ACCEPTED),
            "care_keeper": (min(len(ledger.active_entries(s, member_id, "verified_repair")), 1), 1),
            "material_story": (int("product_history_accepted" in f), 1),
        }
        return [{"badge_id": b, "current": c, "target": t} for b, (c, t) in counts.items() if not earned.get(b)]

    def summary(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")
        m = principal.member_id

        def read(s):
            acct = ledger.load_account(s, m)
            entries = self._entries(s, m, None, 24)
            bs = badges.member_badges(s, m)
            progress = self._progress(s, m, {b["badge_id"]: b["earned"] for b in bs})
            once = {r[0] for r in query(s, "SELECT rule_id FROM RewardEntries WHERE member_id=@m AND kind='credit' AND state='posted' "
                                           "AND rule_id IN ('meaningful_style_setup', 'first_owned_item')", {"m": m}, {"m": STR})}
            if "meaningful_style_setup" not in once:
                nxt = {"kind": "rule", "rule_id": "meaningful_style_setup", "points": 100, "text": RULES["meaningful_style_setup"].member_text}
            elif "first_owned_item" not in once:
                nxt = {"kind": "rule", "rule_id": "first_owned_item", "points": 25, "text": RULES["first_owned_item"].member_text}
            elif progress:
                p = max(progress, key=lambda x: (x["current"] / x["target"], -list(BADGES).index(x["badge_id"])))
                nxt = {"kind": "badge", **p, "text": BADGES[p["badge_id"]].criteria}
            else:
                nxt = None
            return {
                "account": acct.dto(),
                "points_are": "nontransferable application points; not currency, crypto or proof of authenticity",
                "entries": entries,
                "badges": bs,
                "badge_progress": progress,
                "next_milestone": nxt,
                # Launch table: only rules with a wired source. Referral and research ids stay
                # reserved in RULES (and refuse to settle) but are not advertised (check-in Q21).
                "rules": [{"rule_id": r.id, "version": r.version, "points": r.points, "cap_points": r.cap_points, "cap_window": r.cap_window,
                           "lifetime_max": r.lifetime_max, "available": True, "text": r.member_text} for r in RULES.values() if r.wired],
                "recovery_policy": "If awarded points are reversed after you spent them, the shortfall is shown as recovery due and "
                                   "offset from your future eligible awards. Spendable points never go below zero and are never a cash debt.",
            }

        return run_read(self.db, read)

    def _entries(self, s, member_id: str, cursor: Optional[str], limit: int) -> Dict[str, Any]:
        sql = f"SELECT {', '.join(ENTRY_LIST_COLS)} FROM RewardEntries WHERE member_id=@m "
        params: Dict[str, Any] = {"m": member_id, "n": limit + 1}
        types: Dict[str, Any] = {"m": STR, "n": INT}
        if cursor:
            t, i = decode_cursor(cursor, kinds=("ts", "id"))
            sql += "AND (created_at < @t OR (created_at = @t AND entry_id > @i)) "
            params.update(t=t, i=i)
            types.update(t=TS, i=STR)
        rows = query(s, sql + "ORDER BY created_at DESC, entry_id LIMIT @n", params, types)
        items = [_entry_dto(dict(zip(ENTRY_LIST_COLS, r))) for r in rows[:limit]]
        nxt = encode_cursor(rows[limit - 1][-1], rows[limit - 1][0]) if len(rows) > limit else None
        return {"items": items, "next_cursor": nxt}

    def entries(self, principal: Principal, *, cursor: Optional[str] = None, limit: int = 24) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")
        limit = require_strict_int(limit, name="limit", lo=1, hi=100)
        return run_read(self.db, lambda s: self._entries(s, principal.member_id, cursor, limit))

    # ------------------------------------------------------------- disputes

    def open_dispute(self, principal: Principal, body: Any) -> Dict[str, Any]:
        require_scope(principal, "rewards:write")
        if principal.delegation_id is not None:
            raise Forbidden("disputes are opened by the member")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("entry_id", "category", "message"), where="dispute")
        category = body.get("category")
        if category not in DISPUTE_CATEGORIES:
            raise ValidationFailed(f"category must be one of {DISPUTE_CATEGORIES}", extra={"field": "category"})
        entry_id = require_uuid(body["entry_id"], name="entry_id") if body.get("entry_id") is not None else None
        message = require_text(body.get("message"), name="message", max_len=1000)
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, m):
                raise NotFound("member not found")
            guard_write(txn, m, "rewards.disputes")
            if entry_id and ledger.entry(txn, m, entry_id) is None:
                raise NotFound("entry not found")
            open_n = query(txn, "SELECT COUNT(*) FROM RewardDisputes WHERE member_id=@m AND state='open'", {"m": m}, {"m": STR})[0][0]
            if open_n >= MAX_OPEN_DISPUTES:
                raise DetailedInvalidTransition("you already have several open disputes; we will answer those first", code="too_many_open_disputes")
            d = {"member_id": m, "dispute_id": new_id(), "entry_id": entry_id, "category": category, "message": message, "state": "open",
                 "resolution_note": None, "resolved_by": None, "correction_entry_id": None, "version": 1}
            txn.insert("RewardDisputes", columns=(*DISPUTE_COLS[:-2], "created_at"), values=[[*(d[c] for c in DISPUTE_COLS[:-2]), COMMIT_TIMESTAMP]])
            ctx.emit("reward.dispute.opened", "1", "reward_dispute", d["dispute_id"], 1, {"member_id": m, "dispute_id": d["dispute_id"]}, "member_private")
            return _dispute_dto({**d, "created_at": None, "resolved_at": None})

        return command(self.db, principal, tx)

    def my_disputes(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")
        rows = run_read(self.db, lambda s: query(s, f"SELECT {', '.join(DISPUTE_COLS)} FROM RewardDisputes WHERE member_id=@m ORDER BY created_at DESC",
                                                 {"m": principal.member_id}, {"m": STR}))
        return {"items": [_dispute_dto(dict(zip(DISPUTE_COLS, r))) for r in rows], "next_cursor": None}

    # ------------------------------------------------------------- operators

    def list_disputes(self, operator: Principal, *, state: str = "open", limit: int = 50) -> Dict[str, Any]:
        require_operator(operator)
        if state not in ("open", "resolved_correction", "resolved_no_change", "withdrawn"):
            raise ValidationFailed("unknown state", extra={"field": "state"})
        limit = require_strict_int(limit, name="limit", lo=1, hi=100)
        rows = run_read(self.db, lambda s: query(
            s, f"SELECT {', '.join(DISPUTE_COLS)} FROM RewardDisputes@{{FORCE_INDEX=RewardDisputesByState}} WHERE state=@s ORDER BY created_at LIMIT @n",
            {"s": state, "n": limit}, {"s": STR, "n": INT}))
        return {"items": [_dispute_dto(dict(zip(DISPUTE_COLS, r))) for r in rows], "next_cursor": None}

    def member_ledger(self, operator: Principal, member_id: Any) -> Dict[str, Any]:
        """Audit view for dispute handling: account, journal and reducer check."""
        require_operator(operator)
        member_id = require_uuid(member_id, name="member_id")
        require_not_self(operator, member_id)

        def read(s):
            return {"consistency": ledger.consistency(s, member_id), "entries": self._entries(s, member_id, None, 100)["items"]}

        return run_read(self.db, read)

    def resolve_dispute(self, operator: Principal, dispute_id: Any, body: Any) -> Dict[str, Any]:
        require_operator(operator)
        dispute_id = require_uuid(dispute_id, name="dispute_id")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("outcome", "signed_points", "note", "evidence_ref"), where="resolution")
        outcome = body.get("outcome")
        if outcome not in ("correction", "no_change"):
            raise ValidationFailed("outcome must be correction or no_change", extra={"field": "outcome"})
        note = require_text(body.get("note"), name="note", max_len=1000)
        evidence = require_text(body.get("evidence_ref"), name="evidence_ref", max_len=120)
        points = require_strict_int(body.get("signed_points"), name="signed_points", lo=-10_000, hi=10_000) if outcome == "correction" else 0
        if outcome == "correction" and points == 0:
            raise ValidationFailed("a correction moves at least one point", extra={"field": "signed_points"})

        def tx(txn, ctx: CommandContext):
            rows = query(txn, f"SELECT {', '.join(DISPUTE_COLS)} FROM RewardDisputes@{{FORCE_INDEX=RewardDisputesById}} WHERE dispute_id=@d",
                         {"d": dispute_id}, {"d": STR})
            if not rows:
                raise NotFound("dispute not found")
            d = dict(zip(DISPUTE_COLS, rows[0]))
            require_not_self(operator, d["member_id"])
            if d["state"] != "open":
                return _dispute_dto(d)
            # Any resolution writes member data: the dispute's outcome, and for a
            # correction of either sign a ledger entry (a debit on an already
            # deleted ledger would recreate the account).
            guard_write(txn, d["member_id"], "rewards.disputes")
            if points:
                guard_write(txn, d["member_id"], "rewards.ledger")
            corr = ledger.correction(txn, ctx, d["member_id"], dispute_id, points, note, [f"evidence:{evidence}"]) if points else None
            state = "resolved_correction" if corr else "resolved_no_change"
            txn.update("RewardDisputes", columns=("member_id", "dispute_id", "state", "resolution_note", "resolved_by", "correction_entry_id",
                                                  "version", "resolved_at"),
                       values=[(d["member_id"], dispute_id, state, note, operator.actor_ref, corr["entry_id"] if corr else None,
                                d["version"] + 1, COMMIT_TIMESTAMP)])
            ctx.emit("reward.dispute.resolved", "1", "reward_dispute", dispute_id, d["version"] + 1,
                     {"member_id": d["member_id"], "dispute_id": dispute_id, "state": state}, "member_private")
            return _dispute_dto({**d, "state": state, "resolution_note": note, "resolved_by": operator.actor_ref,
                                 "correction_entry_id": corr["entry_id"] if corr else None, "version": d["version"] + 1})

        return command(self.db, operator, tx)

    def reverse_entry(self, actor: Principal, member_id: Any, entry_id: Any, *, reason: str, evidence_ref: str) -> Dict[str, Any]:
        """Reverse a reward after a *verified* disqualifying event (operator or trusted worker)."""
        if not isinstance(actor, ServicePrincipal):
            require_operator(actor)
        member_id = require_uuid(member_id, name="member_id")
        entry_id = require_uuid(entry_id, name="entry_id")
        if not isinstance(actor, ServicePrincipal):
            require_not_self(actor, member_id)
        reason = require_text(reason, name="reason", max_len=500)
        evidence_ref = require_text(evidence_ref, name="evidence_ref", max_len=120)

        def tx(txn, ctx: CommandContext):
            out = ledger.reverse(txn, ctx, member_id, entry_id, reason, [f"evidence:{evidence_ref}"])
            if out["status"] == "reversed":
                out["badges"] = badges.evaluate(txn, ctx, member_id, badges.badges_for_rule(out.get("rule_id")), allow_revoke=True)
            return out

        return command(self.db, actor, tx)

    def accept_contribution(self, reviewer: Principal, member_id: Any, *, kind: str, contribution_ref: Any, evidence_ref: str) -> Dict[str, Any]:
        """Reviewer accepts an evidenced contribution: a catalog correction (50 points,
        250/ISO week) or a product-history contribution (Material Story badge)."""
        require_operator(reviewer)
        member_id = require_uuid(member_id, name="member_id")
        require_not_self(reviewer, member_id)
        if kind not in ("catalog_correction", "product_history"):
            raise ValidationFailed("kind must be catalog_correction or product_history", extra={"field": "kind"})
        ref = require_uuid(contribution_ref, name="contribution_ref")
        evidence_ref = require_text(evidence_ref, name="evidence_ref", max_len=120)

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, member_id):
                raise NotFound("member not found")
            guard_write(txn, member_id, "rewards.ledger")
            now = server_now(txn)
            if kind == "catalog_correction":
                out = ledger.credit(txn, ctx, member_id, RULES["catalog_correction_accepted"], f"contribution:{ref}", now,
                                    [f"contribution:{ref}", f"evidence:{evidence_ref}"])
                return {**out, "badges": {}}
            ledger.set_fact(txn, member_id, "product_history_accepted", f"contribution:{ref}", now)
            return {"status": "recorded", "badges": badges.evaluate(txn, ctx, member_id, ("material_story",))}

        return command(self.db, reviewer, tx)

    def record_verified_repair(self, workflow: ServicePrincipal, member_id: Any, *, repair_ref: Any, issuer_ref: str) -> Dict[str, Any]:
        """An approved repair workflow (service principal) confirms a completed repair."""
        if not isinstance(workflow, ServicePrincipal):
            raise Forbidden("repairs are confirmed by an approved repair workflow")
        if issuer_ref not in self.approved_repair_issuers:
            raise DetailedInvalidTransition("this repair issuer is not approved", code="repair_issuer_not_approved")
        member_id = require_uuid(member_id, name="member_id")
        ref = require_uuid(repair_ref, name="repair_ref")

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, member_id):
                raise NotFound("member not found")
            guard_write(txn, member_id, "rewards.ledger")
            out = ledger.credit(txn, ctx, member_id, RULES["verified_repair"], f"repair:{ref}", server_now(txn),
                                [f"repair:{ref}", f"issuer:{issuer_ref}"])
            return {**out, "badges": badges.evaluate(txn, ctx, member_id, ("care_keeper",))}

        return command(self.db, workflow, tx)
