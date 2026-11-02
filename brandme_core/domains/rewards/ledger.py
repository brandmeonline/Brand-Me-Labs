"""
Ledger primitives. Every function runs inside the caller's read/write
transaction, so the entry, the account reducer and the emitted event commit
together (or not at all).

Accounting (contracts/reward-rules.json ``accounting``):
* ``available`` and ``reserved`` never go negative (also CHECK constraints).
* A credit first pays down ``recovery_due``, then adds to ``available``.
* A reversal is a new linked entry. It takes what it can from ``available``
  and records the rest as ``recovery_due``; spendable points stay >= 0.
* Lifetime earned shown to members is ``gross_earned - reversed_total``;
  gross and reversed history are kept separately.
* Cause uniqueness: a credit's ``entry_id`` is derived from the cause key
  (member, rule, rule version, qualifying event), or from (member, rule,
  version) for lifetime-once rules, so a duplicate collides on the primary
  key inside the settling transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    STR_ARRAY,
    TS,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    query,
    stable_id,
)

from . import events as _events  # noqa: F401
from .rules import Rule, cap_window, utc

ACCOUNT_FIELDS = ("available", "reserved", "gross_earned", "reversed_total", "spent_total", "recovery_due", "version")
ENTRY_COLS = ("member_id", "entry_id", "kind", "state", "rule_id", "rule_version", "cause_event_id", "qualifying_at", "points",
              "available_delta", "reserved_delta", "recovery_delta", "outcome_reason", "reverses_entry_id", "reservation_id",
              "evidence_refs", "actor_ref", "reason")


@dataclass(frozen=True)
class Account:
    member_id: str
    available: int = 0
    reserved: int = 0
    gross_earned: int = 0
    reversed_total: int = 0
    spent_total: int = 0
    recovery_due: int = 0
    version: int = 0

    @property
    def lifetime_earned(self) -> int:
        return self.gross_earned - self.reversed_total

    def dto(self) -> Dict[str, Any]:
        return {"available": self.available, "reserved": self.reserved, "lifetime_earned": self.lifetime_earned,
                "gross_earned": self.gross_earned, "reversed": self.reversed_total, "spent": self.spent_total,
                "recovery_due": self.recovery_due, "version": str(self.version)}


def load_account(txn, member_id: str) -> Account:
    pending = getattr(txn, "_bm_rewards_pending", None)
    if pending and member_id in pending.get("accounts", {}):
        return pending["accounts"][member_id]
    rows = query(txn, f"SELECT {', '.join(ACCOUNT_FIELDS)} FROM RewardAccounts WHERE member_id=@m", {"m": member_id}, {"m": STR})
    return Account(member_id, *rows[0]) if rows else Account(member_id)


def save_account(txn, a: Account) -> Account:
    if a.available < 0 or a.reserved < 0 or a.recovery_due < 0:
        raise AssertionError(f"ledger invariant violated: {a}")  # the CHECK constraints would refuse it too
    a = replace(a, version=a.version + 1)
    txn.insert_or_update("RewardAccounts", columns=("member_id", *ACCOUNT_FIELDS, "updated_at"),
                         values=[(a.member_id, *(getattr(a, f) for f in ACCOUNT_FIELDS), COMMIT_TIMESTAMP)])
    _pending(txn)["accounts"][a.member_id] = a
    return a


def entry(txn, member_id: str, entry_id: str) -> Optional[Dict[str, Any]]:
    for e in getattr(txn, "_bm_rewards_pending", {"entries": []})["entries"]:
        if e["member_id"] == member_id and e["entry_id"] == entry_id:
            return e
    rows = query(txn, f"SELECT {', '.join(ENTRY_COLS)} FROM RewardEntries WHERE member_id=@m AND entry_id=@e",
                 {"m": member_id, "e": entry_id}, {"m": STR, "e": STR})
    return dict(zip(ENTRY_COLS, rows[0])) if rows else None


def _pending(txn) -> Dict[str, Any]:
    """Rows this transaction has buffered. Spanner reads inside a read/write
    transaction do not see its own buffered mutations, so later checks in the
    same transaction (badges, multi-fact rules) merge these in."""
    p = getattr(txn, "_bm_rewards_pending", None)
    if p is None:
        p = {"entries": [], "facts": {}, "accounts": {}}
        setattr(txn, "_bm_rewards_pending", p)
    return p


def insert_entry(txn, **row: Any) -> Dict[str, Any]:
    full = {c: row.get(c) for c in ENTRY_COLS}
    full["evidence_refs"] = list(row.get("evidence_refs") or [])
    for k in ("points", "available_delta", "reserved_delta", "recovery_delta"):
        full[k] = int(full[k] or 0)
    txn.insert("RewardEntries", columns=(*ENTRY_COLS, "created_at"), values=[[*(full[c] for c in ENTRY_COLS), COMMIT_TIMESTAMP]])
    _pending(txn)["entries"].append(full)
    return full


def credit_entry_id(member_id: str, rule: Rule, cause_event_id: str) -> str:
    key = "once" if rule.lifetime_max == 1 else cause_event_id
    return stable_id("reward-credit", member_id, rule.id, str(rule.version), key)


def _buffered_credits(txn, member_id: str, rule_id: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Posted credits this transaction has buffered but its reads cannot see yet."""
    return [e for e in getattr(txn, "_bm_rewards_pending", {"entries": []})["entries"]
            if e["member_id"] == member_id and e["rule_id"] == rule_id and e["kind"] == "credit" and e["state"] == "posted"
            and start <= e["qualifying_at"] < end]


def _window_used(txn, member_id: str, rule: Rule, at: datetime) -> int:
    start, end = cap_window(rule.cap_window, at)
    stored = query(txn, "SELECT COALESCE(SUM(points), 0) FROM RewardEntries WHERE member_id=@m AND rule_id=@r AND rule_version=@v "
                        "AND kind='credit' AND state='posted' AND qualifying_at >= @s AND qualifying_at < @e",
                   {"m": member_id, "r": rule.id, "v": rule.version, "s": start, "e": end},
                   {"m": STR, "r": STR, "v": INT, "s": TS, "e": TS})[0][0]
    return stored + sum(e["points"] for e in _buffered_credits(txn, member_id, rule.id, start, end) if e["rule_version"] == rule.version)


def _pair_awards(txn, member_id: str, rule: Rule, at: datetime, pair_ref: str) -> int:
    start, end = cap_window("calendar_day", at)
    stored = query(txn, "SELECT COUNT(*) FROM RewardEntries WHERE member_id=@m AND rule_id=@r AND kind='credit' AND state='posted' "
                        "AND qualifying_at >= @s AND qualifying_at < @e AND @p IN UNNEST(evidence_refs)",
                   {"m": member_id, "r": rule.id, "s": start, "e": end, "p": pair_ref},
                   {"m": STR, "r": STR, "s": TS, "e": TS, "p": STR})[0][0]
    return stored + sum(1 for e in _buffered_credits(txn, member_id, rule.id, start, end) if pair_ref in e["evidence_refs"])


def credit(txn, ctx: CommandContext, member_id: str, rule: Rule, cause_event_id: str, qualifying_at: datetime,
           evidence_refs: Sequence[str], *, exclusion: Optional[str] = None, pair_ref: Optional[str] = None,
           pair_limit: Optional[int] = None) -> Dict[str, Any]:
    """Settle one rule cause for one member. Returns the outcome; a duplicate
    cause returns ``duplicate_cause`` and changes nothing."""
    if not rule.wired or rule.points is None:
        raise DetailedInvalidTransition(f"rule {rule.id} has no wired source", code="rule_not_available")
    entry_id = credit_entry_id(member_id, rule, cause_event_id)
    if entry(txn, member_id, entry_id) is not None:
        return {"status": "duplicate_cause", "entry_id": entry_id, "member_id": member_id}
    at = utc(qualifying_at)
    acct = load_account(txn, member_id)
    state, reason, points = "posted", None, rule.points
    if exclusion:
        state, reason, points = "excluded", exclusion, 0
    elif pair_ref and pair_limit is not None and _pair_awards(txn, member_id, rule, at, pair_ref) >= pair_limit:
        state, reason, points = "excluded", "collusive_repeated_acceptance", 0
    elif rule.cap_points is not None and _window_used(txn, member_id, rule, at) + rule.points > rule.cap_points:
        state, reason, points = "capped", "cap_reached", 0
    offset = min(points, acct.recovery_due)
    acct = replace(acct, available=acct.available + points - offset, recovery_due=acct.recovery_due - offset,
                   gross_earned=acct.gross_earned + points)
    refs = list(evidence_refs) + ([pair_ref] if pair_ref else [])
    insert_entry(txn, member_id=member_id, entry_id=entry_id, kind="credit", state=state, rule_id=rule.id, rule_version=rule.version,
                 cause_event_id=cause_event_id, qualifying_at=at, points=points, available_delta=points - offset,
                 recovery_delta=-offset, outcome_reason=reason, evidence_refs=refs, actor_ref=ctx.principal.actor_ref)
    acct = save_account(txn, acct)
    ctx.emit("reward.posted", "1", "reward_account", member_id, acct.version,
             {"member_id": member_id, "entry_id": entry_id, "kind": "credit", "rule_id": rule.id, "rule_version": rule.version,
              "points": points, "state": state}, "member_private")
    return {"status": state, "entry_id": entry_id, "member_id": member_id, "points": points, "recovery_offset": offset,
            "reason": reason}


def reverse(txn, ctx: CommandContext, member_id: str, entry_id: str, reason: str, evidence_refs: Sequence[str]) -> Dict[str, Any]:
    """Linked reversal of a posted credit/correction. Idempotent per original entry."""
    orig = entry(txn, member_id, entry_id)
    if orig is None:
        raise NotFound("entry not found")
    rev_id = stable_id("reward-reversal", member_id, entry_id)
    existing = entry(txn, member_id, rev_id)
    if existing is not None:
        return {"status": "already_reversed", "entry_id": rev_id, "points": existing["points"], "recovery_due_added": existing["recovery_delta"]}
    awarded = orig["kind"] == "credit" or (orig["kind"] == "correction" and orig["outcome_reason"] == "credit")
    if not awarded or orig["state"] != "posted" or orig["points"] <= 0:
        raise DetailedInvalidTransition("only a posted award can be reversed", code="not_reversible")
    p = orig["points"]
    acct = load_account(txn, member_id)
    take = min(p, acct.available)
    acct = replace(acct, available=acct.available - take, recovery_due=acct.recovery_due + (p - take), reversed_total=acct.reversed_total + p)
    insert_entry(txn, member_id=member_id, entry_id=rev_id, kind="reversal", state="posted", rule_id=orig["rule_id"],
                 rule_version=orig["rule_version"], points=p, available_delta=-take, recovery_delta=p - take,
                 reverses_entry_id=entry_id, evidence_refs=list(evidence_refs), actor_ref=ctx.principal.actor_ref, reason=reason[:500])
    acct = save_account(txn, acct)
    ctx.emit("reward.reversed", "1", "reward_account", member_id, acct.version,
             {"member_id": member_id, "entry_id": rev_id, "reverses_entry_id": entry_id, "points": p, "recovery_due_added": p - take},
             "member_private")
    return {"status": "reversed", "entry_id": rev_id, "points": p, "recovery_due_added": p - take, "rule_id": orig["rule_id"]}


def correction(txn, ctx: CommandContext, member_id: str, dispute_id: str, signed_points: int, reason: str,
               evidence_refs: Sequence[str]) -> Dict[str, Any]:
    """Operator correction: a reasoned ledger entry, never a balance edit."""
    entry_id = stable_id("reward-correction", member_id, dispute_id)
    if entry(txn, member_id, entry_id) is not None:
        return {"status": "duplicate_cause", "entry_id": entry_id}
    acct = load_account(txn, member_id)
    p = abs(signed_points)
    if signed_points > 0:
        offset = min(p, acct.recovery_due)
        acct = replace(acct, available=acct.available + p - offset, recovery_due=acct.recovery_due - offset, gross_earned=acct.gross_earned + p)
        deltas = (p - offset, -offset)
    else:
        take = min(p, acct.available)
        acct = replace(acct, available=acct.available - take, recovery_due=acct.recovery_due + p - take, reversed_total=acct.reversed_total + p)
        deltas = (-take, p - take)
    insert_entry(txn, member_id=member_id, entry_id=entry_id, kind="correction", state="posted", points=p,
                 available_delta=deltas[0], recovery_delta=deltas[1], outcome_reason="credit" if signed_points > 0 else "debit",
                 evidence_refs=[f"dispute:{dispute_id}", *evidence_refs], actor_ref=ctx.principal.actor_ref, reason=reason[:500])
    acct = save_account(txn, acct)
    ctx.emit("reward.posted", "1", "reward_account", member_id, acct.version,
             {"member_id": member_id, "entry_id": entry_id, "kind": "correction", "rule_id": None, "rule_version": None,
              "points": p, "state": "posted"}, "member_private")
    return {"status": "posted", "entry_id": entry_id, "signed_points": signed_points}


def set_fact(txn, member_id: str, fact: str, event_id: str, occurred_at: datetime) -> bool:
    if fact in facts(txn, member_id):
        return False
    txn.insert("RewardFacts", columns=("member_id", "fact", "event_id", "occurred_at", "created_at"),
               values=[(member_id, fact, event_id, utc(occurred_at), COMMIT_TIMESTAMP)])
    _pending(txn)["facts"][(member_id, fact)] = {"event_id": event_id, "occurred_at": utc(occurred_at)}
    return True


def facts(txn, member_id: str) -> Dict[str, Dict[str, Any]]:
    out = {r[0]: {"event_id": r[1], "occurred_at": r[2]} for r in query(
        txn, "SELECT fact, event_id, occurred_at FROM RewardFacts WHERE member_id=@m", {"m": member_id}, {"m": STR})}
    for (m, f), v in getattr(txn, "_bm_rewards_pending", {"facts": {}})["facts"].items():
        if m == member_id:
            out.setdefault(f, v)
    return out


def consistency(txn, member_id: str) -> Dict[str, Any]:
    """Reducer check: the account equals the sum of its journal."""
    s = query(txn, "SELECT COALESCE(SUM(available_delta),0), COALESCE(SUM(reserved_delta),0), COALESCE(SUM(recovery_delta),0) "
                   "FROM RewardEntries WHERE member_id=@m", {"m": member_id}, {"m": STR})[0]
    a = load_account(txn, member_id)
    return {"ok": (a.available, a.reserved, a.recovery_due) == tuple(s), "account": a.dto(), "journal": list(s)}


def active_entries(txn, member_id: str, rule_id: str, states: Sequence[str] = ("posted", "capped")) -> List[Dict[str, Any]]:
    """Credits for a rule that were not reversed (badge evidence)."""
    rows = query(txn, "SELECT e.entry_id, e.evidence_refs FROM RewardEntries e WHERE e.member_id=@m AND e.rule_id=@r AND e.kind='credit' "
                      "AND e.state IN UNNEST(@s) AND NOT EXISTS (SELECT 1 FROM RewardEntries v WHERE v.member_id=e.member_id "
                      "AND v.kind='reversal' AND v.reverses_entry_id=e.entry_id) ORDER BY e.qualifying_at, e.entry_id",
                 {"m": member_id, "r": rule_id, "s": list(states)},
                 {"m": STR, "r": STR, "s": STR_ARRAY})
    out = [{"entry_id": r[0], "evidence_refs": list(r[1])} for r in rows]
    pend = getattr(txn, "_bm_rewards_pending", {"entries": []})["entries"]
    reversed_now = {e["reverses_entry_id"] for e in pend if e["member_id"] == member_id and e["kind"] == "reversal"}
    out += [{"entry_id": e["entry_id"], "evidence_refs": list(e["evidence_refs"])} for e in pend
            if e["member_id"] == member_id and e["kind"] == "credit" and e["rule_id"] == rule_id and e["state"] in states]
    return [e for e in out if e["entry_id"] not in reversed_now]
