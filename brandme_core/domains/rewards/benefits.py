"""
Benefit redemption (ch.01 §7.4; BM-LOY-007/008).

* Reserve: in one transaction, check the benefit (active, funded if partner,
  not past ``available_until`` by server time, inventory left) and the
  member's available points, then move points available → reserved, take one
  unit of inventory and write a ``pending`` reservation plus a ``reserve``
  ledger entry. Two reservations racing the same points serialize; the loser
  sees ``insufficient_points``. Available points never go negative.
* The pending reservation is the durable fulfillment work item. A worker
  (``run_fulfillment``) calls the fulfiller outside any transaction, then
  records the outcome with ``settle``. Success moves reserved → spent
  (``redeem`` entry); failure or expiry returns reserved → available
  (``release`` entry) and frees the inventory. Settlement happens once:
  a reservation that is no longer pending is returned unchanged.
* Core data controls, accessibility, deletion and ordinary wardrobe access are
  never benefits; nothing here gates them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable, Dict, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    TS,
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
    parse_iso,
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
from .operators import require_operator

BENEFIT_COLS = ("benefit_id", "kind", "title", "description", "cost_points", "inventory_total", "inventory_reserved", "inventory_fulfilled",
                "funded", "sponsor", "active", "available_until", "reservation_ttl_seconds", "version")
RES_COLS = ("member_id", "reservation_id", "benefit_id", "cost_points", "state", "expires_at", "release_reason", "version", "created_at", "settled_at")
KINDS = ("room_finish", "composition_template", "partner")


def _benefit(txn, benefit_id: str) -> Optional[Dict[str, Any]]:
    rows = query(txn, f"SELECT {', '.join(BENEFIT_COLS)} FROM Benefits WHERE benefit_id=@b", {"b": benefit_id}, {"b": STR})
    return dict(zip(BENEFIT_COLS, rows[0])) if rows else None


def _benefit_dto(b: Mapping[str, Any], now) -> Dict[str, Any]:
    left = b["inventory_total"] - b["inventory_reserved"] - b["inventory_fulfilled"]
    expired = b["available_until"] is not None and b["available_until"] <= now
    return {"benefit_id": b["benefit_id"], "kind": b["kind"], "title": b["title"], "description": b["description"],
            "cost_points": b["cost_points"], "remaining": left, "sponsor": b["sponsor"], "available_until": iso(b["available_until"]),
            "available": bool(b["active"]) and not expired and left > 0}


def _res_dto(r: Mapping[str, Any]) -> Dict[str, Any]:
    return {"reservation_id": r["reservation_id"], "benefit_id": r["benefit_id"], "cost_points": r["cost_points"], "state": r["state"],
            "expires_at": iso(r["expires_at"]), "release_reason": r["release_reason"], "created_at": iso(r.get("created_at")),
            "settled_at": iso(r.get("settled_at")), "version": str(r["version"])}


class BenefitService:
    def __init__(self, database):
        self.db = database

    # ------------------------------------------------------------- operator

    def create_benefit(self, operator: Principal, body: Any) -> Dict[str, Any]:
        require_operator(operator)
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_non_finite(body)
        reject_unknown_keys(body, ("kind", "title", "description", "cost_points", "inventory_total", "funded", "sponsor",
                                   "available_until", "reservation_ttl_seconds"), where="benefit")
        kind = body.get("kind")
        if kind not in KINDS:
            raise ValidationFailed(f"kind must be one of {KINDS}", extra={"field": "kind"})
        funded = body.get("funded") is True
        sponsor = body.get("sponsor")
        if kind == "partner" and (not funded or not isinstance(sponsor, str) or not sponsor.strip()):
            raise ValidationFailed("a partner benefit must be funded under a contract and name its sponsor", extra={"field": "funded"})
        row = {
            "benefit_id": new_id(), "kind": kind, "title": require_text(body.get("title"), name="title", max_len=120),
            "description": require_text(body.get("description"), name="description", max_len=500),
            "cost_points": require_strict_int(body.get("cost_points"), name="cost_points", lo=1, hi=1_000_000),
            "inventory_total": require_strict_int(body.get("inventory_total"), name="inventory_total", lo=0, hi=10_000_000),
            "inventory_reserved": 0, "inventory_fulfilled": 0, "funded": funded,
            "sponsor": sponsor.strip()[:120] if isinstance(sponsor, str) and sponsor.strip() else None, "active": True,
            "available_until": parse_iso(body["available_until"], name="available_until") if body.get("available_until") else None,
            "reservation_ttl_seconds": require_strict_int(body.get("reservation_ttl_seconds", 900), name="reservation_ttl_seconds", lo=60, hi=2_592_000),
            "version": 1,
        }

        def tx(txn, ctx: CommandContext):
            txn.insert("Benefits", columns=(*BENEFIT_COLS, "created_at", "updated_at"),
                       values=[[*(row[c] for c in BENEFIT_COLS), COMMIT_TIMESTAMP, COMMIT_TIMESTAMP]])
            return _benefit_dto(row, server_now(txn))

        return command(self.db, operator, tx)

    # --------------------------------------------------------------- member

    def list_benefits(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")

        def read(s):
            now = server_now(s)
            rows = query(s, f"SELECT {', '.join(BENEFIT_COLS)} FROM Benefits WHERE active ORDER BY cost_points, benefit_id LIMIT 100")
            return [_benefit_dto(dict(zip(BENEFIT_COLS, r)), now) for r in rows]

        return {"items": run_read(self.db, read), "next_cursor": None}

    def reserve(self, principal: Principal, benefit_id: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "rewards:write")
        benefit_id = require_uuid(benefit_id, name="benefit_id")
        member = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, member):
                raise NotFound("member not found")
            guard_write(txn, member, "rewards.redemptions")
            now = server_now(txn)
            b = _benefit(txn, benefit_id)
            if b is None or not b["active"]:
                raise NotFound("benefit not found")
            if (b["available_until"] is not None and b["available_until"] <= now) or \
                    b["inventory_reserved"] + b["inventory_fulfilled"] >= b["inventory_total"]:
                raise DetailedInvalidTransition("this benefit is not available right now", code="benefit_unavailable")
            acct = ledger.load_account(txn, member)
            cost = b["cost_points"]
            if acct.available < cost:
                raise DetailedInvalidTransition("not enough available points", code="insufficient_points",
                                                extra={"available": acct.available, "cost_points": cost})
            reservation_id = new_id()
            expires = now + timedelta(seconds=b["reservation_ttl_seconds"])
            acct = ledger.save_account(txn, replace(acct, available=acct.available - cost, reserved=acct.reserved + cost))
            ledger.insert_entry(txn, member_id=member, entry_id=stable_id("reward-reserve", reservation_id), kind="reserve", state="posted",
                                points=cost, available_delta=-cost, reserved_delta=cost, reservation_id=reservation_id,
                                evidence_refs=[f"benefit:{benefit_id}"], actor_ref=principal.actor_ref)
            txn.update("Benefits", columns=("benefit_id", "inventory_reserved", "version", "updated_at"),
                       values=[(benefit_id, b["inventory_reserved"] + 1, b["version"] + 1, COMMIT_TIMESTAMP)])
            r = {"member_id": member, "reservation_id": reservation_id, "benefit_id": benefit_id, "cost_points": cost, "state": "pending",
                 "expires_at": expires, "release_reason": None, "version": 1}
            txn.insert("BenefitReservations", columns=(*RES_COLS[:-2], "created_at"), values=[[*(r[c] for c in RES_COLS[:-2]), COMMIT_TIMESTAMP]])
            ctx.emit("benefit.reserved", "1", "benefit_reservation", reservation_id, 1,
                     {"member_id": member, "reservation_id": reservation_id, "benefit_id": benefit_id, "cost_points": cost}, "member_private")
            return {**_res_dto({**r, "created_at": now}), "account": acct.dto()}

        response, _ = idempotent_command(self.db, principal, "benefits.reserve", idempotency_key, {"benefit_id": benefit_id}, tx)
        return response

    def list_reservations(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")
        rows = run_read(self.db, lambda s: query(
            s, f"SELECT {', '.join(RES_COLS)} FROM BenefitReservations WHERE member_id=@m ORDER BY created_at DESC LIMIT 100",
            {"m": principal.member_id}, {"m": STR}))
        return {"items": [_res_dto(dict(zip(RES_COLS, r))) for r in rows], "next_cursor": None}

    # ------------------------------------------------------------ settlement

    def settle(self, reservation_id: Any, *, succeeded: bool, reason: str = "fulfillment_failed",
               environment: str = "development") -> Dict[str, Any]:
        """Record the fulfillment outcome once (worker path)."""
        reservation_id = require_uuid(reservation_id, name="reservation_id")
        principal = service_principal("benefit-fulfillment", environment=environment)

        def tx(txn, ctx: CommandContext):
            rows = query(txn, f"SELECT {', '.join(RES_COLS)} FROM BenefitReservations@{{FORCE_INDEX=BenefitReservationsById}} "
                              "WHERE reservation_id=@r", {"r": reservation_id}, {"r": STR})
            if not rows:
                raise NotFound("reservation not found")
            r = dict(zip(RES_COLS, rows[0]))
            if r["state"] != "pending":
                return {**_res_dto(r), "changed": False}
            return {**self._settle(txn, ctx, r, succeeded, reason), "changed": True}

        return command(self.db, principal, tx)

    def _settle(self, txn, ctx: CommandContext, r: Dict[str, Any], succeeded: bool, reason: str) -> Dict[str, Any]:
        member, cost, rid = r["member_id"], r["cost_points"], r["reservation_id"]
        acct = ledger.load_account(txn, member)
        b = _benefit(txn, r["benefit_id"])
        if succeeded:
            acct = replace(acct, reserved=acct.reserved - cost, spent_total=acct.spent_total + cost)
            ledger.insert_entry(txn, member_id=member, entry_id=stable_id("reward-redeem", rid), kind="redeem", state="posted", points=cost,
                                reserved_delta=-cost, reservation_id=rid, evidence_refs=[f"benefit:{r['benefit_id']}"], actor_ref=ctx.principal.actor_ref)
            inv = (b["inventory_reserved"] - 1, b["inventory_fulfilled"] + 1)
            state, why, event = "fulfilled", None, "benefit.fulfilled"
        else:
            acct = replace(acct, reserved=acct.reserved - cost, available=acct.available + cost)
            ledger.insert_entry(txn, member_id=member, entry_id=stable_id("reward-release", rid), kind="release", state="posted", points=cost,
                                available_delta=cost, reserved_delta=-cost, reservation_id=rid, outcome_reason=reason[:48],
                                evidence_refs=[f"benefit:{r['benefit_id']}"], actor_ref=ctx.principal.actor_ref)
            inv = (b["inventory_reserved"] - 1, b["inventory_fulfilled"])
            state, why, event = "refunded", reason[:48], "benefit.refunded"
        ledger.save_account(txn, acct)
        txn.update("Benefits", columns=("benefit_id", "inventory_reserved", "inventory_fulfilled", "version", "updated_at"),
                   values=[(b["benefit_id"], inv[0], inv[1], b["version"] + 1, COMMIT_TIMESTAMP)])
        txn.update("BenefitReservations", columns=("member_id", "reservation_id", "state", "release_reason", "version", "settled_at"),
                   values=[(member, rid, state, why, r["version"] + 1, COMMIT_TIMESTAMP)])
        ctx.emit(event, "1", "benefit_reservation", rid, r["version"] + 1,
                 {"member_id": member, "reservation_id": rid, "benefit_id": r["benefit_id"], "cost_points": cost}, "member_private")
        return _res_dto({**r, "state": state, "release_reason": why, "version": r["version"] + 1})

    def expire_due(self, *, limit: int = 100, environment: str = "development") -> Dict[str, int]:
        """Release pending reservations past their server-time expiry."""
        due = run_read(self.db, lambda s: query(
            s, "SELECT reservation_id FROM BenefitReservations@{FORCE_INDEX=BenefitReservationsByStateExpiry} "
               "WHERE state='pending' AND expires_at <= @n ORDER BY expires_at LIMIT @l",
            {"n": server_now(s), "l": limit}, {"n": TS, "l": INT}))
        n = 0
        for (rid,) in due:
            n += int(self.settle(rid, succeeded=False, reason="expired", environment=environment)["changed"])
        return {"released": n}

    def run_fulfillment(self, fulfiller: Callable[[Dict[str, Any]], bool], *, benefit_id: Optional[str] = None, limit: int = 50,
                        environment: str = "development") -> Dict[str, int]:
        """Durable job: each pending reservation (optionally of one benefit, since
        fulfillers differ by benefit) is fulfilled outside any transaction, then
        settled once. A fulfiller exception counts as a failure."""
        only = "AND benefit_id=@b " if benefit_id else ""
        pending = run_read(self.db, lambda s: query(
            s, f"SELECT {', '.join(RES_COLS)} FROM BenefitReservations@{{FORCE_INDEX=BenefitReservationsByStateExpiry}} "
               f"WHERE state='pending' AND expires_at > @n {only}ORDER BY expires_at LIMIT @l",
            {"n": server_now(s), "l": limit, "b": benefit_id or ""}, {"n": TS, "l": INT, "b": STR}))
        counts = {"fulfilled": 0, "refunded": 0, "skipped": 0}
        for row in pending:
            r = _res_dto(dict(zip(RES_COLS, row)))
            try:
                ok = bool(fulfiller(r))
            except Exception:  # noqa: BLE001 - a failed provider call is an outcome, not a crash
                ok = False
            out = self.settle(r["reservation_id"], succeeded=ok, environment=environment)
            counts["skipped" if not out["changed"] else ("fulfilled" if ok else "refunded")] += 1
        return counts
