"""W10 privacy registration for rewards.

Points are application credits, not money, so the ledger is erased with the
account. A pending reservation's inventory unit is returned to the benefit
before the reservation is deleted. Operator identities on resolved disputes
are operator data and are not part of the member's export.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains import DataCategory as FoundationDataCategory, register_data_category
from brandme_core.domains.persona.kernel import STR, iso, query, run_read, run_txn, stable_id
from brandme_core.domains.persona.privacy_guard import record_scope_refusal

from . import ledger

DOMAIN = "rewards"
_M = {"m": STR}

CATEGORIES: Dict[str, Dict[str, Any]] = {
    "rewards.ledger": {
        "title": "Your points balance and every points entry, with the rule and evidence behind it",
        "supplied_by": "system",
        "retention": "Until you delete your account",
        "on_edit": "Corrections are new reasoned entries; history is never rewritten",
        "tables": ("RewardAccounts", "RewardEntries", "RewardFacts"),
    },
    "rewards.badges": {
        "title": "Badges you earned, with their criteria version and evidence",
        "supplied_by": "system",
        "retention": "Until you delete your account",
        "on_edit": "A badge is revoked only if its evidence is reversed",
        "tables": ("BadgeAwards",),
    },
    "rewards.redemptions": {
        "title": "Benefits you reserved and their fulfillment status",
        "supplied_by": "member",
        "retention": "Until you delete your account",
        "on_edit": "Failed or expired reservations return your points",
        "tables": ("BenefitReservations",),
    },
    "rewards.disputes": {
        "title": "Disputes you opened and how they were resolved",
        "supplied_by": "member",
        "retention": "Until you delete your account",
        "on_edit": "Resolved disputes keep their resolution note",
        "tables": ("RewardDisputes",),
    },
    "rewards.standings": {
        "title": "Your standing tier with each house, computed from your verified purchases",
        "supplied_by": "system",
        "retention": "Until the next daily recompute, or until you delete your account",
        "on_edit": "Tiers are recomputed, never edited; only the tier is kept, not counts or spend",
        "tables": ("HouseStandings",),
    },
}


def export_category(snap, member_id: str, category: str) -> List[Dict[str, Any]]:
    m = {"m": member_id}
    if category == "rewards.ledger":
        acct = query(snap, "SELECT available, reserved, gross_earned, reversed_total, spent_total, recovery_due FROM RewardAccounts WHERE member_id=@m", m, _M)
        cols = ("entry_id", "kind", "state", "rule_id", "rule_version", "cause_event_id", "qualifying_at", "points", "available_delta",
                "reserved_delta", "recovery_delta", "outcome_reason", "reverses_entry_id", "reservation_id", "evidence_refs", "reason", "created_at")
        entries = []
        for r in query(snap, f"SELECT {', '.join(cols)} FROM RewardEntries WHERE member_id=@m ORDER BY created_at, entry_id", m, _M):
            d = dict(zip(cols, r))
            d.update(qualifying_at=iso(d["qualifying_at"]), created_at=iso(d["created_at"]), evidence_refs=list(d["evidence_refs"]))
            entries.append(d)
        return [{"account": dict(zip(("available", "reserved", "gross_earned", "reversed", "spent", "recovery_due"), acct[0])) if acct else None,
                 "entries": entries}]
    if category == "rewards.badges":
        return [{"badge_id": r[0], "criteria_version": r[1], "evidence_refs": list(r[2]), "awarded_at": iso(r[3]), "revoked_at": iso(r[4])}
                for r in query(snap, "SELECT badge_id, criteria_version, evidence_refs, awarded_at, revoked_at FROM BadgeAwards WHERE member_id=@m "
                                     "ORDER BY badge_id", m, _M)]
    if category == "rewards.redemptions":
        return [{"reservation_id": r[0], "benefit_id": r[1], "cost_points": r[2], "state": r[3], "release_reason": r[4], "created_at": iso(r[5]),
                 "settled_at": iso(r[6])}
                for r in query(snap, "SELECT reservation_id, benefit_id, cost_points, state, release_reason, created_at, settled_at "
                                     "FROM BenefitReservations WHERE member_id=@m ORDER BY created_at", m, _M)]
    if category == "rewards.disputes":
        return [{"dispute_id": r[0], "entry_id": r[1], "category": r[2], "message": r[3], "state": r[4], "resolution_note": r[5],
                 "created_at": iso(r[6]), "resolved_at": iso(r[7])}
                for r in query(snap, "SELECT dispute_id, entry_id, category, message, state, resolution_note, created_at, resolved_at "
                                     "FROM RewardDisputes WHERE member_id=@m ORDER BY created_at", m, _M)]
    if category == "rewards.standings":
        return [{"house_ref": r[0], "tier": r[1], "computed_at": iso(r[2])}
                for r in query(snap, "SELECT house_ref, tier, computed_at FROM HouseStandings WHERE member_id=@m ORDER BY house_ref", m, _M)]
    raise KeyError(category)


def delete_category(txn, member_id: str, category: str) -> int:
    m = {"m": member_id}
    if category == "rewards.ledger":
        n = txn.execute_update("DELETE FROM RewardEntries WHERE member_id=@m", params=m, param_types=_M)
        n += txn.execute_update("DELETE FROM RewardFacts WHERE member_id=@m", params=m, param_types=_M)
        return n + txn.execute_update("DELETE FROM RewardAccounts WHERE member_id=@m", params=m, param_types=_M)
    if category == "rewards.badges":
        return txn.execute_update("DELETE FROM BadgeAwards WHERE member_id=@m", params=m, param_types=_M)
    if category == "rewards.redemptions":
        pending: Dict[str, int] = {}
        held = query(txn, "SELECT reservation_id, benefit_id, cost_points FROM BenefitReservations WHERE member_id=@m AND state='pending'", m, _M)
        for _rid, bid, _cost in held:
            pending[bid] = pending.get(bid, 0) + 1
        # Points a pending reservation holds go back to the member through a
        # release entry, as a failed fulfillment would. When the ledger category
        # was already deleted (account deletion) there is no balance to restore.
        if held and query(txn, "SELECT 1 FROM RewardAccounts WHERE member_id=@m", m, _M):
            acct = ledger.load_account(txn, member_id)
            total = sum(cost for _rid, _bid, cost in held)
            for rid, bid, cost in held:
                ledger.insert_entry(txn, member_id=member_id, entry_id=stable_id("reward-release", rid), kind="release", state="posted",
                                    points=cost, available_delta=cost, reserved_delta=-cost, reservation_id=rid,
                                    outcome_reason="privacy_deleted", evidence_refs=[f"benefit:{bid}"], actor_ref="service:privacy")
            ledger.save_account(txn, replace(acct, reserved=acct.reserved - total, available=acct.available + total))
        for bid, k in pending.items():
            cur = query(txn, "SELECT inventory_reserved, version FROM Benefits WHERE benefit_id=@b", {"b": bid}, {"b": STR})
            if cur:
                txn.update("Benefits", columns=("benefit_id", "inventory_reserved", "version", "updated_at"),
                           values=[(bid, max(0, cur[0][0] - k), cur[0][1] + 1, COMMIT_TIMESTAMP)])
        return txn.execute_update("DELETE FROM BenefitReservations WHERE member_id=@m", params=m, param_types=_M)
    if category == "rewards.disputes":
        return txn.execute_update("DELETE FROM RewardDisputes WHERE member_id=@m", params=m, param_types=_M)
    if category == "rewards.standings":
        return txn.execute_update("DELETE FROM HouseStandings WHERE member_id=@m", params=m, param_types=_M)
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

    class RewardsPrivacyHandler:
        domain = DOMAIN

        def categories(self):
            return [
                pd.DataCategory(
                    key=k, domain=DOMAIN, title=c["title"],
                    supplied_by=pd.Supplier.SYSTEM if c["supplied_by"] == "system" else pd.Supplier.MEMBER,
                    visible_to=("member",), retention=c["retention"], on_edit=c["on_edit"], on_delete=pd.OnDelete.ERASE,
                )
                for k, c in CATEGORIES.items()
            ]

        def export(self, snapshot, ctx, category):
            return pd.ExportSection(category, export_category(snapshot, ctx.subject_ref, category))

        def delete(self, txn, ctx, category):
            return record_scope_refusal(pd, ctx, category) or pd.DeletionOutcome(category, delete_category(txn, ctx.subject_ref, category))

        def purge_derived(self, ctx, category):
            return pd.DeletionOutcome(category, 0, done=True, detail="no derived stores outside Spanner")

        def reapply_tombstone(self, txn, tombstone):
            if tombstone.record_keys:
                return 0  # record-level deletions are refused by delete(); nothing to reapply
            return delete_category(txn, tombstone.subject_ref, tombstone.category)

    return RewardsPrivacyHandler()


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
