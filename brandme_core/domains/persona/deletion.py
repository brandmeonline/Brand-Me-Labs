"""
W10 privacy registration for the persona domain.

Two registrations, one implementation:

* foundation ``brandme_core.domains.register_data_category`` (always present):
  ``export(database, member_id)`` / ``delete(database, member_id)`` callables;
* the privacy lane's published ``DomainPrivacyHandler``
  (``brandme_core.domains.privacy.deletion``), registered when that module is
  importable (integration). Its orchestrator drives ``export``/``delete`` per
  category inside its own snapshot / read-write transaction.

The subject reference is the internal member UUID. Account deletion
(``delete_member``) also writes ``PersonaTombstones`` first, so a racing
inference job cannot recreate the profile even where the privacy lane's
freeze tables are absent.
"""

from __future__ import annotations

from typing import Any, Dict, List

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, KeySet

from brandme_core.domains import DataCategory as FoundationDataCategory, register_data_category

from .kernel import STR, iso, json_value, query, run_read, run_txn
from .privacy_guard import record_scope_refusal

DOMAIN = "persona"

# key -> (title, supplied_by, retention, on_edit, tables)
CATEGORIES: Dict[str, Dict[str, Any]] = {
    "persona.declared": {
        "title": "Style choices you made (declared axes, locks, budget, exclusions, contexts)",
        "supplied_by": "member",
        "retention": "Until you edit, reset or delete them, or delete your account",
        "on_edit": "Recommendations use the new value immediately; a locked value overrides any inference",
        "tables": ("PersonaProfiles", "PersonaAxes", "PersonaContextOverrides"),
    },
    "persona.inferred": {
        "title": "Style estimates Brand.Me inferred from your activity",
        "supplied_by": "inferred",
        "retention": "Recomputed from active evidence; cleared by reset or deletion",
        "on_edit": "Lock a declared value to override it, or turn off learning for the axis",
        "tables": ("PersonaAxes",),
    },
    "persona.evidence": {
        "title": "Examples used for inference (saved looks, products, feedback, carried-over profile)",
        "supplied_by": "inferred",
        "retention": "Until excluded, reset, expired or deleted. Exclusion keeps a one-way hash so the same example is not reused",
        "on_edit": "Exclude an example: its contribution is removed and it cannot be re-ingested",
        "tables": ("PersonaEvidence", "PersonaSuppressions"),
    },
    "persona.snapshots": {
        "title": "Named snapshots of your style",
        "supplied_by": "member",
        "retention": "Until you delete them or your account",
        "on_edit": "Restoring a snapshot creates a new profile version",
        "tables": ("PersonaSnapshots",),
    },
    "persona.feedback": {
        "title": "Recommendation feedback (interested / not me)",
        "supplied_by": "member",
        "retention": "Until account deletion",
        "on_edit": "'Not me' hides that product; interest informs ranking only while learning is on",
        "tables": ("RecommendationFeedback",),
    },
}

_M = {"m": STR}


# --------------------------------------------------------------- export


def export_category(snap, member_id: str, category: str) -> List[Dict[str, Any]]:
    m = {"m": member_id}
    if category == "persona.declared":
        prof = query(
            snap,
            "SELECT version, learning_enabled, budget_ceiling_minor, budget_currency, excluded_brands, "
            "excluded_materials, excluded_categories, goals, prefer_owned, social_signals_enabled, updated_at "
            "FROM PersonaProfiles WHERE member_id=@m",
            m,
            _M,
        )
        if not prof:
            return []
        r = prof[0]
        axes = query(
            snap,
            "SELECT axis_key, declared_value, locked, adapt_enabled, inference_allowed, hidden FROM PersonaAxes "
            "WHERE member_id=@m ORDER BY axis_key",
            m,
            _M,
        )
        overrides = query(
            snap,
            "SELECT override_id, label, axes, starts_at, ends_at, enabled FROM PersonaContextOverrides WHERE member_id=@m",
            m,
            _M,
        )
        return [
            {
                "profile_version": str(r[0]),
                "learning_enabled": r[1],
                "budget_ceiling_minor": None if r[2] is None else str(r[2]),
                "budget_currency": r[3],
                "excluded_brands": list(r[4] or []),
                "excluded_materials": list(r[5] or []),
                "excluded_categories": list(r[6] or []),
                "goals": list(r[7] or []),
                "prefer_owned": r[8],
                "social_signals_enabled": r[9],
                "updated_at": iso(r[10]),
                "axes": [
                    {"axis": a[0], "declared": a[1], "locked": a[2], "adapt_enabled": a[3], "inference_allowed": a[4], "hidden": a[5]}
                    for a in axes
                ],
                "context_overrides": [
                    {"override_id": o[0], "label": o[1], "axes": json_value(o[2]), "starts_at": iso(o[3]), "ends_at": iso(o[4]), "enabled": o[5]}
                    for o in overrides
                ],
            }
        ]
    if category == "persona.inferred":
        return [
            {"axis": a[0], "inferred": a[1], "confidence": a[2], "evidence_count": a[3]}
            for a in query(
                snap,
                "SELECT axis_key, inferred_value, inferred_confidence, inferred_evidence_count FROM PersonaAxes "
                "WHERE member_id=@m AND inferred_value IS NOT NULL ORDER BY axis_key",
                m,
                _M,
            )
        ]
    if category == "persona.evidence":
        return [
            {
                "evidence_id": e[0],
                "source_type": e[1],
                "source_ref": e[2],
                "purpose": e[3],
                "axis_contributions": json_value(e[4]),
                "weight": e[5],
                "model_version": e[6],
                "observed_at": iso(e[7]),
                "expires_at": iso(e[8]),
                "suppression_state": e[9],
            }
            for e in query(
                snap,
                "SELECT evidence_id, source_type, source_ref, purpose, axis_contributions, weight, model_version, "
                "observed_at, expires_at, suppression_state FROM PersonaEvidence WHERE member_id=@m "
                "ORDER BY observed_at, evidence_id",
                m,
                _M,
            )
        ]
    if category == "persona.snapshots":
        return [
            {"snapshot_id": s[0], "saved_name": s[1], "profile_version": str(s[2]), "axes": json_value(s[3]), "created_at": iso(s[4])}
            for s in query(
                snap,
                "SELECT snapshot_id, saved_name, profile_version, axes_snapshot, created_at FROM PersonaSnapshots "
                "WHERE member_id=@m ORDER BY created_at",
                m,
                _M,
            )
        ]
    if category == "persona.feedback":
        return [
            {"feedback_id": f[0], "product_id": f[1], "category": f[2], "signal": f[3], "created_at": iso(f[4])}
            for f in query(
                snap,
                "SELECT feedback_id, product_id, category, signal, created_at FROM RecommendationFeedback "
                "WHERE member_id=@m ORDER BY created_at",
                m,
                _M,
            )
        ]
    raise KeyError(category)


def export_member(snap, member_id: str) -> Dict[str, Any]:
    return {
        "domain": DOMAIN,
        "schema_version": "1",
        "categories": {c: export_category(snap, member_id, c) for c in CATEGORIES},
    }


# --------------------------------------------------------------- delete


def delete_category(txn, member_id: str, category: str) -> int:
    """Remove one category's rows inside the caller's read/write transaction."""
    m = {"m": member_id}
    if category == "persona.declared":
        n = txn.execute_update(
            "UPDATE PersonaAxes SET declared_value = NULL, locked = FALSE, adapt_enabled = FALSE, "
            "adapt_first_accepted = FALSE, adapt_last_applied_at = NULL, hidden = FALSE, inference_allowed = TRUE "
            "WHERE member_id=@m AND (declared_value IS NOT NULL OR locked OR adapt_enabled OR hidden OR NOT inference_allowed)",
            params=m,
            param_types=_M,
        )
        n += txn.execute_update("DELETE FROM PersonaContextOverrides WHERE member_id=@m", params=m, param_types=_M)
        n += txn.execute_update(
            # The two processing switches reset to the protective value, not the
            # new-profile default: deleting declared data never re-enables learning
            # the member had turned off. They can switch it back on.
            "UPDATE PersonaProfiles SET budget_ceiling_minor = NULL, budget_currency = NULL, excluded_brands = [], "
            "excluded_materials = [], excluded_categories = [], goals = [], prefer_owned = FALSE, "
            "learning_enabled = FALSE, social_signals_enabled = FALSE, "
            "onboarding_intent = NULL, version = version + 1, updated_at = PENDING_COMMIT_TIMESTAMP() WHERE member_id=@m",
            params=m,
            param_types=_M,
        )
        return n
    if category == "persona.inferred":
        return txn.execute_update(
            "UPDATE PersonaAxes SET inferred_value = NULL, inferred_confidence = NULL, inferred_evidence_count = 0 "
            "WHERE member_id=@m AND inferred_value IS NOT NULL",
            params=m,
            param_types=_M,
        )
    if category == "persona.evidence":
        # Keep one-way fingerprints as suppression rules so a queued job cannot
        # re-ingest the same observations; drop the evidence rows themselves.
        rows = query(txn, "SELECT source_fingerprint FROM PersonaEvidence WHERE member_id=@m", m, _M)
        if rows:
            txn.insert_or_update(
                "PersonaSuppressions",
                columns=("member_id", "source_fingerprint", "reason", "created_at"),
                values=[(member_id, r[0], "privacy_deleted", COMMIT_TIMESTAMP) for r in rows],
            )
        n = txn.execute_update("DELETE FROM PersonaEvidence WHERE member_id=@m", params=m, param_types=_M)
        n += txn.execute_update(
            "UPDATE PersonaAxes SET inferred_value = NULL, inferred_confidence = NULL, inferred_evidence_count = 0 "
            "WHERE member_id=@m AND inferred_value IS NOT NULL",
            params=m,
            param_types=_M,
        )
        return n
    if category == "persona.snapshots":
        from brandme_core.domains.social.shares import revoke_for_deleted_subjects

        # Snapshot share previews embed the snapshot's declared axes.
        n = revoke_for_deleted_subjects(txn, member_id, ("persona_snapshot",))
        return n + txn.execute_update("DELETE FROM PersonaSnapshots WHERE member_id=@m", params=m, param_types=_M)
    if category == "persona.feedback":
        return txn.execute_update("DELETE FROM RecommendationFeedback WHERE member_id=@m", params=m, param_types=_M)
    raise KeyError(category)


def delete_member(txn, member_id: str) -> Dict[str, Any]:
    """Account deletion: tombstone first, then remove every persona row."""
    counts = {
        "evidence": query(txn, "SELECT COUNT(*) FROM PersonaEvidence WHERE member_id=@m", {"m": member_id}, _M)[0][0],
        "snapshots": query(txn, "SELECT COUNT(*) FROM PersonaSnapshots WHERE member_id=@m", {"m": member_id}, _M)[0][0],
    }
    txn.insert_or_update("PersonaTombstones", columns=("member_id", "deleted_at"), values=[(member_id, COMMIT_TIMESTAMP)])
    # Interleaved children (axes, evidence, suppressions, overrides, snapshots,
    # feedback) cascade with the parent row.
    txn.delete("PersonaProfiles", KeySet(keys=[[member_id]]))
    txn.execute_update("DELETE FROM GuestMigrations WHERE member_id=@m", params={"m": member_id}, param_types=_M)
    return {"domain": DOMAIN, "deleted": counts, "retained": [], "tombstoned": True}


_LEFT_IN_PROFILE = (
    "SELECT 1 FROM PersonaEvidence WHERE member_id=@m LIMIT 1",
    "SELECT 1 FROM PersonaSnapshots WHERE member_id=@m LIMIT 1",
    "SELECT 1 FROM RecommendationFeedback WHERE member_id=@m LIMIT 1",
    "SELECT 1 FROM PersonaContextOverrides WHERE member_id=@m LIMIT 1",
    "SELECT 1 FROM PersonaAxes WHERE member_id=@m AND (declared_value IS NOT NULL OR inferred_value IS NOT NULL) LIMIT 1",
)


def remove_account_shell(txn, member_id: str, job_id: str) -> int:
    """Whole-account privacy deletion runs per category, which leaves an empty
    profile row (reset axes, suppression fingerprints). Once every persona
    category is empty in an account-scoped job, drop that row as ``delete_member``
    does. A category-scoped job keeps it: the member still has a profile.
    ``DeletionJobs`` is the privacy lane's job table (V009)."""
    if not query(txn, "SELECT 1 FROM DeletionJobs WHERE job_id=@j AND scope='account'", {"j": job_id}, {"j": STR}):
        return 0
    m = {"m": member_id}
    if not query(txn, "SELECT 1 FROM PersonaProfiles WHERE member_id=@m", m, _M) or any(query(txn, q, m, _M) for q in _LEFT_IN_PROFILE):
        return 0
    delete_member(txn, member_id)
    return 1


# ---------------------------------------------- foundation registration


def _foundation_export(category: str):
    return lambda database, member_id: run_read(database, lambda s: export_category(s, member_id, category))


def _foundation_delete(category: str):
    return lambda database, member_id: run_txn(database, lambda t: delete_category(t, member_id, category))


for _key, _c in CATEGORIES.items():
    register_data_category(
        FoundationDataCategory(
            name=_key,
            domain=DOMAIN,
            description=_c["title"],
            supplied_by=_c["supplied_by"],
            visible_to="member only",
            retention=_c["retention"],
            tables=_c["tables"],
            export=_foundation_export(_key),
            delete=_foundation_delete(_key),
        )
    )


# ------------------------------------------- privacy-lane registration


def build_privacy_handler():
    """A fresh handler instance, or None when the privacy lane is absent."""
    try:
        from brandme_core.domains.privacy import deletion as pd
    except ImportError:
        return None

    supplier = {"member": pd.Supplier.MEMBER, "inferred": pd.Supplier.INFERRED}

    class PersonaPrivacyHandler:
        domain = DOMAIN

        def categories(self):
            return [
                pd.DataCategory(
                    key=k,
                    domain=DOMAIN,
                    title=c["title"],
                    supplied_by=supplier[c["supplied_by"]],
                    visible_to=("member",),
                    retention=c["retention"],
                    on_edit=c["on_edit"],
                    on_delete=pd.OnDelete.ERASE,
                )
                for k, c in CATEGORIES.items()
            ]

        def export(self, snapshot, ctx, category: str):
            return pd.ExportSection(category, export_category(snapshot, ctx.subject_ref, category))

        def delete(self, txn, ctx, category: str):
            refused = record_scope_refusal(pd, ctx, category)
            if refused:
                return refused
            n = delete_category(txn, ctx.subject_ref, category)
            return pd.DeletionOutcome(category, n + remove_account_shell(txn, ctx.subject_ref, ctx.job_id))

        def purge_derived(self, ctx, category: str):
            # No Firestore projection, cache or object storage is owned by the
            # persona domain yet; recommendation previews are computed per request.
            return pd.DeletionOutcome(category, 0, done=True, detail="persona keeps no derived stores")

        def reapply_tombstone(self, txn, tombstone) -> int:
            if tombstone.record_keys:
                return 0  # record-level deletions are refused by delete(); nothing to reapply
            n = delete_category(txn, tombstone.subject_ref, tombstone.category)
            return n + remove_account_shell(txn, tombstone.subject_ref, tombstone.deletion_job_id)

    return PersonaPrivacyHandler()


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

