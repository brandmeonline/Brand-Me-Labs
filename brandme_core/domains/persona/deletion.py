"""
W10 privacy registration for the persona domain.

The privacy lane (Lane 4) owns the export/deletion job framework; it had not
published its interface when this was written. This module exposes the minimal
contract every consumer domain in this lane implements:

  DATA_CATEGORIES      what is stored, who supplied it, edit/delete meaning
  export_member(snap, member_id) -> dict    portable JSON for the export job
  delete_member(txn, member_id) -> dict     runs inside the deletion job's txn

Deletion writes a tombstone first so a racing inference job cannot recreate
the profile (ch.06 §4).
"""

from __future__ import annotations

from typing import Any, Dict

from google.cloud import spanner

from .kernel import STR, iso, json_value, query

DOMAIN = "persona"

DATA_CATEGORIES = [
    {
        "category": "persona.declared",
        "supplied_by": "member",
        "visible_to": "member only",
        "retention": "until edited, reset or account deletion",
        "edit_meaning": "Changes what recommendations use immediately",
        "delete_meaning": "Removes the declared value; the axis becomes unanswered",
    },
    {
        "category": "persona.inferred",
        "supplied_by": "Brand.Me inference from member activity",
        "visible_to": "member only",
        "retention": "recomputed from active evidence; suppressed evidence is never reused",
        "edit_meaning": "Lock or override with a declared value",
        "delete_meaning": "Suppression rule stops the same observation being reused",
    },
    {
        "category": "persona.evidence",
        "supplied_by": "member activity (saved looks, products, feedback)",
        "visible_to": "member only",
        "retention": "until suppressed, reset, expired or account deletion",
        "edit_meaning": "Exclude an example",
        "delete_meaning": "Contribution removed and future re-ingestion blocked",
    },
    {
        "category": "persona.snapshots",
        "supplied_by": "member",
        "visible_to": "member only",
        "retention": "until deleted or account deletion",
        "edit_meaning": "Restore creates a new profile version",
        "delete_meaning": "Snapshot removed",
    },
    {
        "category": "persona.recommendation_feedback",
        "supplied_by": "member",
        "visible_to": "member only",
        "retention": "until account deletion",
        "edit_meaning": "Not me hides a product; interest informs ranking only while learning is on",
        "delete_meaning": "Removed with the profile",
    },
]


def export_member(snap, member_id: str) -> Dict[str, Any]:
    m = {"m": member_id}
    t = {"m": STR}
    out: Dict[str, Any] = {"domain": DOMAIN, "schema_version": "1"}
    prof = query(
        snap,
        "SELECT version, learning_enabled, budget_ceiling_minor, budget_currency, excluded_brands, excluded_materials, "
        "excluded_categories, goals, updated_at FROM PersonaProfiles WHERE member_id=@m",
        m,
        t,
    )
    if not prof:
        out["profile"] = None
        return out
    r = prof[0]
    out["profile"] = {
        "version": str(r[0]),
        "learning_enabled": r[1],
        "budget_ceiling_minor": None if r[2] is None else str(r[2]),
        "budget_currency": r[3],
        "excluded_brands": list(r[4] or []),
        "excluded_materials": list(r[5] or []),
        "excluded_categories": list(r[6] or []),
        "goals": list(r[7] or []),
        "updated_at": iso(r[8]),
    }
    out["axes"] = [
        {
            "axis": a[0],
            "declared": a[1],
            "locked": a[2],
            "inferred": a[3],
            "inferred_confidence": a[4],
            "inference_allowed": a[5],
            "hidden": a[6],
        }
        for a in query(
            snap,
            "SELECT axis_key, declared_value, locked, inferred_value, inferred_confidence, inference_allowed, hidden "
            "FROM PersonaAxes WHERE member_id=@m ORDER BY axis_key",
            m,
            t,
        )
    ]
    out["evidence"] = [
        {
            "evidence_id": e[0],
            "source_type": e[1],
            "source_ref": e[2],
            "purpose": e[3],
            "axis_contributions": json_value(e[4]),
            "observed_at": iso(e[5]),
            "suppression_state": e[6],
        }
        for e in query(
            snap,
            "SELECT evidence_id, source_type, source_ref, purpose, axis_contributions, observed_at, suppression_state "
            "FROM PersonaEvidence WHERE member_id=@m ORDER BY observed_at, evidence_id",
            m,
            t,
        )
    ]
    out["snapshots"] = [
        {"snapshot_id": s[0], "saved_name": s[1], "profile_version": str(s[2]), "axes": json_value(s[3]), "created_at": iso(s[4])}
        for s in query(
            snap,
            "SELECT snapshot_id, saved_name, profile_version, axes_snapshot, created_at FROM PersonaSnapshots WHERE member_id=@m",
            m,
            t,
        )
    ]
    return out


def delete_member(txn, member_id: str) -> Dict[str, Any]:
    counts = {
        "evidence": query(txn, "SELECT COUNT(*) FROM PersonaEvidence WHERE member_id=@m", {"m": member_id}, {"m": STR})[0][0],
        "snapshots": query(txn, "SELECT COUNT(*) FROM PersonaSnapshots WHERE member_id=@m", {"m": member_id}, {"m": STR})[0][0],
    }
    txn.insert_or_update(
        "PersonaTombstones", columns=("member_id", "deleted_at"), values=[(member_id, spanner.COMMIT_TIMESTAMP)]
    )
    # Interleaved children (axes, evidence, suppressions, overrides, snapshots,
    # feedback) cascade with the parent row.
    txn.delete("PersonaProfiles", spanner.KeySet(keys=[[member_id]]))
    txn.execute_update("DELETE FROM GuestMigrations WHERE member_id=@m", params={"m": member_id}, param_types={"m": STR})
    return {"domain": DOMAIN, "deleted": counts, "retained": [], "tombstoned": True}
