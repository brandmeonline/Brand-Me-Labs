"""
Points → in-app purchase credit, and nothing else (Ultra plan 02, item 5;
launch posture: not cashable).

* **Conversion** is the member's own act: scope ``rewards:write``, never an
  agent, with an Idempotency-Key. It takes whole hundreds of points, at least
  ``MIN_POINTS``, at ``RATES`` (dev default: 1 point = 1 US cent).
* **The ledger enforces "in-app only".** Converting writes a ``reserve``
  entry, so the points are held while the credit is outstanding. Applying the
  credit to an in-app order writes ``redeem`` (spent). Expiry writes
  ``release``, and the points come back (paying down any recovery debt
  first). The ledger has no kind that pays out, transfers or converts to money
  (V005 ``ck_re_kind``), and no route here takes an amount of money, a payout
  destination or another member.
* **A credit belongs to one member.** It is applied only by the in-app checkout
  (``apply_credit``, for the commerce lane to call inside its order
  transaction) and only for its own currency. It cannot be transferred.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    ValidationFailed,
    command,
    guard_write,
    idempotent_command,
    iso,
    member_active,
    new_id,
    processing_allowed,
    query,
    reject_non_finite,
    reject_unknown_keys,
    require_scope,
    require_strict_int,
    require_text,
    require_uuid,
    run_read,
    server_now,
    service_principal,
    stable_id,
)

from . import ledger

RATES: Dict[str, int] = {"USD": 1}  # minor units of credit per point
MIN_POINTS = 500
STEP = 100
MAX_POINTS = 100_000
CREDIT_TTL = timedelta(days=365)
COLS = ("member_id", "credit_id", "points", "amount_minor", "currency", "state", "applied_ref", "expires_at", "created_at", "settled_at", "version")


def _dto(c: Mapping[str, Any]) -> Dict[str, Any]:
    return {"credit_id": c["credit_id"], "points": c["points"], "amount": {"minor": c["amount_minor"], "currency": c["currency"]},
            "state": c["state"], "expires_at": iso(c["expires_at"]), "created_at": iso(c.get("created_at")), "settled_at": iso(c.get("settled_at")),
            "usable": "In-app purchases only; not cash, not transferable"}


def _credit(txn, member_id: str, credit_id: str) -> Optional[Dict[str, Any]]:
    rows = query(txn, f"SELECT {', '.join(COLS)} FROM PurchaseCredits WHERE member_id=@m AND credit_id=@c",
                 {"m": member_id, "c": credit_id}, {"m": STR, "c": STR})
    return dict(zip(COLS, rows[0])) if rows else None


class CreditService:
    def __init__(self, database):
        self.db = database

    def convert(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "rewards:write")
        if principal.delegation_id:
            raise DetailedInvalidTransition("only the member converts points", code="member_only")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_non_finite(body)
        reject_unknown_keys(body, ("points", "currency"), where="credit conversion")
        points = require_strict_int(body.get("points"), name="points", lo=MIN_POINTS, hi=MAX_POINTS)
        if points % STEP:
            raise ValidationFailed(f"convert whole hundreds of points (at least {MIN_POINTS})", extra={"field": "points"})
        currency = body.get("currency", "USD")
        if currency not in RATES:
            raise ValidationFailed(f"credit is available in {sorted(RATES)}", extra={"field": "currency"})
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, me):
                raise NotFound("member not found")
            guard_write(txn, me, "rewards.credits")
            guard_write(txn, me, "rewards.ledger")  # converting writes the ledger's reserve entry
            acct = ledger.load_account(txn, me)
            if acct.available < points:
                raise DetailedInvalidTransition("not enough available points", code="insufficient_points",
                                                extra={"available": acct.available, "points": points})
            now = server_now(txn)
            credit_id = new_id()
            acct = ledger.save_account(txn, replace(acct, available=acct.available - points, reserved=acct.reserved + points))
            ledger.insert_entry(txn, member_id=me, entry_id=stable_id("credit-reserve", credit_id), kind="reserve", state="posted", points=points,
                                available_delta=-points, reserved_delta=points, evidence_refs=[f"purchase_credit:{credit_id}"],
                                actor_ref=principal.actor_ref)
            c = {"member_id": me, "credit_id": credit_id, "points": points, "amount_minor": points * RATES[currency], "currency": currency,
                 "state": "available", "applied_ref": None, "expires_at": now + CREDIT_TTL, "settled_at": None, "version": 1}
            txn.insert("PurchaseCredits", columns=(*[k for k in COLS if k != "created_at"], "created_at"),
                       values=[[*(c[k] for k in COLS if k != "created_at"), COMMIT_TIMESTAMP]])
            return {**_dto({**c, "created_at": now}), "account": acct.dto()}

        response, _ = idempotent_command(self.db, principal, "credits.convert", idempotency_key, dict(body), tx)
        return response

    def mine(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")
        rows = run_read(self.db, lambda s: query(s, f"SELECT {', '.join(COLS)} FROM PurchaseCredits WHERE member_id=@m ORDER BY created_at DESC LIMIT 100",
                                                 {"m": principal.member_id}, {"m": STR}))
        return {"items": [_dto(dict(zip(COLS, r))) for r in rows], "rates": {k: {"minor_per_point": v} for k, v in RATES.items()},
                "min_points": MIN_POINTS, "step": STEP}

    def expire_due(self, *, limit: int = 200) -> int:
        """Return the points of credits past their expiry (jobs process)."""
        due = run_read(self.db, lambda s: query(s, "SELECT member_id, credit_id FROM PurchaseCredits@{FORCE_INDEX=PurchaseCreditsByExpiry} "
                                                   "WHERE state='available' AND expires_at <= CURRENT_TIMESTAMP() LIMIT @l",
                                                {"l": limit}, {"l": INT}))
        n = 0
        for member_id, credit_id in due:
            def tx(txn, ctx: CommandContext, member_id=member_id, credit_id=credit_id):
                c = _credit(txn, member_id, credit_id)
                if c is None or c["state"] != "available" or c["expires_at"] > server_now(txn):
                    return 0
                if not processing_allowed(txn, member_id, "rewards.credits"):
                    return 0  # deletion pending: the credit goes with the account
                _settle(txn, c, "expired", None, ctx.principal.actor_ref)
                return 1

            n += command(self.db, service_principal("rewards.credit-expiry"), tx)
        return n


def _backed(txn, member_id: str, credit_id: str) -> bool:
    """The credit's points are still held in the ledger. After the member deleted
    ``rewards.ledger`` they are not: the held points went with the ledger, and the
    credit stays theirs until it is used or expires, settling without ledger entries."""
    return bool(query(txn, "SELECT 1 FROM RewardEntries WHERE member_id=@m AND entry_id=@e",
                      {"m": member_id, "e": stable_id("credit-reserve", credit_id)}, {"m": STR, "e": STR}))


def _settle(txn, c: Mapping[str, Any], state: str, applied_ref: Optional[str], actor_ref: str, *, keep_row: bool = True) -> None:
    member, points, cid = c["member_id"], c["points"], c["credit_id"]
    if _backed(txn, member, cid):
        acct = ledger.load_account(txn, member)
        if state == "applied":
            acct = replace(acct, reserved=acct.reserved - points, spent_total=acct.spent_total + points)
            ledger.insert_entry(txn, member_id=member, entry_id=stable_id("credit-redeem", cid), kind="redeem", state="posted", points=points,
                                reserved_delta=-points, evidence_refs=[f"purchase_credit:{cid}", f"order:{applied_ref}"], actor_ref=actor_ref)
        else:
            # Released points pay down recovery debt first, as any credit to the account does.
            offset = min(points, acct.recovery_due)
            acct = replace(acct, reserved=acct.reserved - points, available=acct.available + points - offset, recovery_due=acct.recovery_due - offset)
            ledger.insert_entry(txn, member_id=member, entry_id=stable_id("credit-release", cid), kind="release", state="posted", points=points,
                                available_delta=points - offset, reserved_delta=-points, recovery_delta=-offset, outcome_reason=state,
                                evidence_refs=[f"purchase_credit:{cid}"], actor_ref=actor_ref)
        ledger.save_account(txn, acct)
    if not keep_row:
        return  # the caller deletes the credit in this transaction
    txn.update("PurchaseCredits", columns=("member_id", "credit_id", "state", "applied_ref", "settled_at", "version"),
               values=[(member, cid, state, applied_ref, COMMIT_TIMESTAMP, c["version"] + 1)])


def apply_credit(txn, *, member_id: str, credit_id: Any, order_ref: Any, currency: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """For the in-app checkout (commerce lane), inside its order transaction:
    spend one available, unexpired credit of this member in its own currency.
    Not wired yet; the commerce lane calls it when it adopts credits."""
    credit_id = require_uuid(credit_id, name="credit_id")
    order_ref = require_text(order_ref, name="order_ref", max_len=120)
    c = _credit(txn, member_id, credit_id)
    at = now or server_now(txn)
    if c is None:
        raise NotFound("credit not found")
    guard_write(txn, member_id, "rewards.credits")
    if c["state"] != "available" or c["expires_at"] <= at:
        raise DetailedInvalidTransition("this credit is no longer available", code="credit_unavailable", extra={"state": c["state"]})
    if c["currency"] != currency:
        raise DetailedInvalidTransition("this credit is in another currency", code="credit_currency_mismatch", extra={"currency": c["currency"]})
    _settle(txn, c, "applied", order_ref, "service:commerce.checkout")
    return {"credit_id": credit_id, "amount": {"minor": c["amount_minor"], "currency": c["currency"]}}


def export_credits(snap, member_id: str) -> List[Dict[str, Any]]:
    return [_dto(dict(zip(COLS, r))) for r in query(snap, f"SELECT {', '.join(COLS)} FROM PurchaseCredits WHERE member_id=@m ORDER BY created_at",
                                                    {"m": member_id}, {"m": STR})]


def release_outstanding(txn, member_id: str) -> int:
    """Privacy deletion of the credits category alone: return held points first
    (when the ledger is already gone, there is nothing to return)."""
    rows = query(txn, f"SELECT {', '.join(COLS)} FROM PurchaseCredits WHERE member_id=@m AND state='available'", {"m": member_id}, {"m": STR})
    for r in rows:
        _settle(txn, dict(zip(COLS, r)), "expired", None, "service:privacy", keep_row=False)
    return len(rows)
