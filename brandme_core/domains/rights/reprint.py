"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Licensed reprint workflow (ch.04 §7) — application side.

The contract enforces quota, manufacturer authorization and one child per
unit. This service tracks the product workflow around it and makes
manufacturer callbacks exactly-once at the application layer too:

* every callback is recorded in ManufacturerCallbacks keyed by
  (manufacturer_id, callback_id) inside the same transaction as its effect,
  so a redelivered callback is recorded once and applied once;
* a callback can never increase quota or move a job backwards;
* "unit_produced" advances units_attested only for the next unit in order
  and only up to the job quantity;
* failures never restore quota automatically — compensation is an
  issuer-authorized replacement allowance on chain (grantReplacementAllowance).

Payment state is tracked separately from rights state.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, param_types as pt
from google.cloud.spanner_v1.database import Database

STATES = (
    "eligibility_check", "quoted", "approved", "reserved", "rights_consuming", "rights_consumed", "accepted",
    "manufacturing", "quality_review", "shipped", "delivered", "cancel_requested", "cancelled", "failed", "disputed",
)

TRANSITIONS: Mapping[str, frozenset[str]] = {
    "eligibility_check": frozenset({"quoted", "failed"}),
    "quoted": frozenset({"approved", "cancelled", "failed"}),
    "approved": frozenset({"reserved", "cancelled", "failed"}),
    "reserved": frozenset({"rights_consuming", "cancel_requested", "failed"}),
    # A failed/unsubmitted proof returns to reserved; it never consumed quota.
    "rights_consuming": frozenset({"rights_consumed", "reserved", "failed"}),
    "rights_consumed": frozenset({"accepted", "cancel_requested", "failed", "disputed"}),
    "accepted": frozenset({"manufacturing", "cancel_requested", "failed", "disputed"}),
    "manufacturing": frozenset({"quality_review", "failed", "disputed"}),
    "quality_review": frozenset({"shipped", "failed", "disputed"}),
    "shipped": frozenset({"delivered", "disputed"}),
    "delivered": frozenset({"disputed"}),
    "cancel_requested": frozenset({"cancelled", "failed", "disputed"}),
    "cancelled": frozenset(),
    "failed": frozenset({"disputed"}),
    "disputed": frozenset({"delivered", "failed", "cancelled"}),
}

CALLBACK_EFFECTS: Mapping[str, Optional[str]] = {
    "accepted": "accepted",
    "manufacturing_started": "manufacturing",
    "unit_produced": None,        # advances units_attested; may move to quality_review
    "quality_passed": "shipped",  # requires quality_review
    "shipped": "shipped",
    "failed": "failed",
}


class IllegalReprintTransition(Exception):
    pass


@dataclass(frozen=True)
class CallbackResult:
    outcome: str        # applied | duplicate | rejected
    state: str
    units_attested: int
    reason: Optional[str] = None


def blinded_job_commitment(job_id: str, salt: bytes) -> str:
    """Job commitment for the chain nullifier: blinded with 32 random bytes, never a bare job id."""
    if len(salt) != 32:
        raise ValueError("salt must be 32 random bytes")
    return hashlib.sha256(b"brandme:reprint-job:v1" + salt + job_id.encode()).hexdigest()


class ReprintService:
    def __init__(self, database: Database) -> None:
        self.db = database

    def create(self, *, network: str, allowance_id: str, entitlement_id: str, manufacturer_id: str,
               member_subject_ref: str, quantity: int, job_commitment: str) -> str:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        job_id = str(uuid.uuid4())
        with self.db.batch() as b:
            b.insert("ReprintJobs", ["job_id", "network", "allowance_id", "entitlement_id", "manufacturer_id", "member_subject_ref",
                                     "job_commitment", "quantity", "state", "payment_state", "units_attested", "version", "created_at", "updated_at"],
                     [[job_id, network, allowance_id, entitlement_id, manufacturer_id, member_subject_ref, job_commitment,
                       quantity, "eligibility_check", "none", 0, 1, datetime.now(timezone.utc), COMMIT_TIMESTAMP]])
        return job_id

    def get(self, job_id: str) -> dict[str, Any]:
        with self.db.snapshot() as s:
            return self._read(s, job_id)

    def transition(self, job_id: str, to: str, **fields: Any) -> dict[str, Any]:
        def fn(txn: Any) -> dict[str, Any]:
            job = self._read(txn, job_id)
            self._check(job["state"], to)
            self._write(txn, job, to, **fields)
            return {**job, "state": to, **fields}
        return self.db.run_in_transaction(fn)

    def record_rights_consumed(self, job_id: str, *, nullifier: str, operation_id: str, operation_state: str) -> dict[str, Any]:
        """Only a finalized chain operation moves the job to rights_consumed (evidence direction: chain → app)."""
        if operation_state != "Finalized":
            raise IllegalReprintTransition(f"consumption not finalized on chain (operation is {operation_state})")
        return self.transition(job_id, "rights_consumed", consumption_nullifier=nullifier, consume_operation_id=operation_id)

    def apply_callback(self, *, manufacturer_id: str, callback_id: str, job_id: str, kind: str,
                       unit_index: Optional[int] = None, payload: Mapping[str, Any] | None = None) -> CallbackResult:
        digest = hashlib.sha256(json.dumps(payload or {}, sort_keys=True, default=str).encode()).hexdigest()

        def fn(txn: Any) -> CallbackResult:
            prior = list(txn.execute_sql(
                "SELECT outcome FROM ManufacturerCallbacks WHERE manufacturer_id = @m AND callback_id = @c",
                params={"m": manufacturer_id, "c": callback_id}, param_types={"m": pt.STRING, "c": pt.STRING}))
            job = self._read(txn, job_id)
            if prior:
                return CallbackResult("duplicate", job["state"], job["units_attested"])
            outcome, reason, new_state, units = "applied", None, job["state"], job["units_attested"]
            if job["manufacturer_id"] != manufacturer_id:
                outcome, reason = "rejected", "callback from a manufacturer not assigned to this job"
            elif kind not in CALLBACK_EFFECTS:
                outcome, reason = "rejected", f"unknown callback kind {kind}"
            elif kind == "unit_produced":
                if job["state"] not in ("manufacturing", "accepted"):
                    outcome, reason = "rejected", f"unit_produced not valid in state {job['state']}"
                elif unit_index != units:
                    outcome, reason = "rejected", f"unit {unit_index} out of order (next is {units})"
                elif units >= job["quantity"]:
                    outcome, reason = "rejected", "all units already produced"
                else:
                    units += 1
                    if job["state"] == "accepted":
                        new_state = "manufacturing"
                    if units == job["quantity"]:
                        new_state = "quality_review"
            else:
                target = CALLBACK_EFFECTS[kind]
                if target == "shipped" and kind == "quality_passed" and job["state"] != "quality_review":
                    outcome, reason = "rejected", "quality_passed requires quality_review"
                elif target not in TRANSITIONS[job["state"]]:
                    outcome, reason = "rejected", f"{kind} not valid in state {job['state']}"
                else:
                    new_state = target
            txn.insert("ManufacturerCallbacks", ["manufacturer_id", "callback_id", "job_id", "kind", "unit_index", "payload_digest", "outcome", "received_at"],
                       [[manufacturer_id, callback_id, job_id, kind, unit_index, digest, outcome, COMMIT_TIMESTAMP]])
            if outcome == "applied":
                self._write(txn, job, new_state, units_attested=units)
            return CallbackResult(outcome, new_state, units, reason)

        return self.db.run_in_transaction(fn)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _check(frm: str, to: str) -> None:
        if to not in TRANSITIONS.get(frm, frozenset()):
            raise IllegalReprintTransition(f"{frm} → {to}")

    @staticmethod
    def _read(reader: Any, job_id: str) -> dict[str, Any]:
        rows = list(reader.execute_sql(
            "SELECT job_id, state, quantity, units_attested, manufacturer_id, version, allowance_id, consumption_nullifier "
            "FROM ReprintJobs WHERE job_id = @j", params={"j": job_id}, param_types={"j": pt.STRING}))
        if not rows:
            raise KeyError(job_id)
        r = rows[0]
        return {"job_id": r[0], "state": r[1], "quantity": r[2], "units_attested": r[3], "manufacturer_id": r[4],
                "version": r[5], "allowance_id": r[6], "consumption_nullifier": r[7]}

    @staticmethod
    def _write(txn: Any, job: Mapping[str, Any], state: str, **fields: Any) -> None:
        cols = ["job_id", "state", "version", "updated_at", *fields.keys()]
        txn.update("ReprintJobs", cols, [[job["job_id"], state, job["version"] + 1, COMMIT_TIMESTAMP, *fields.values()]])
