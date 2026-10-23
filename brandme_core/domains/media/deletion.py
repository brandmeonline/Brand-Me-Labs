"""W10 privacy registration for try-on consents, jobs and app-owned media.

Rows are removed in the deletion transaction; media rows are first
tombstoned so the blob purge (an external side effect) runs after commit
through the configured store, then the rows are removed. Provider-side copies
are requested for deletion where the provider supports it; the export says
what was sent to which provider under which terms.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from brandme_core.domains import DataCategory as FoundationDataCategory, register_data_category
from brandme_core.domains.persona.kernel import STR, iso, query, run_read, run_txn
from brandme_core.domains.persona.privacy_guard import record_scope_refusal

DOMAIN = "media"
_M = {"m": STR}
_STORE: Optional[Any] = None
_DB: Optional[Any] = None

CATEGORIES: Dict[str, Dict[str, Any]] = {
    "media.tryon_consents": {
        "title": "Your consents to send photos to a try-on provider",
        "supplied_by": "member",
        "retention": "Until you revoke them or delete your account",
        "on_edit": "Revoking cancels queued previews and deletes their photos",
        "tables": ("TryOnConsents",),
    },
    "media.tryon_media": {
        "title": "Photos you uploaded for try-on and generated previews",
        "supplied_by": "member",
        "retention": "Unsaved photos and previews: 24 hours; saved previews: until you delete them",
        "on_edit": "Deleting a preview removes the photo, the result and their derivatives",
        "tables": ("TryOnJobs", "MediaObjects"),
    },
}


def configure_store(store: Any, db: Any = None) -> None:
    """The media service registers its object store (and database) so the
    privacy deletion can purge blobs after its transaction commits."""
    global _STORE, _DB
    _STORE = store
    _DB = db if db is not None else _DB


def export_category(snap, member_id: str, category: str) -> List[Dict[str, Any]]:
    m = {"m": member_id}
    if category == "media.tryon_consents":
        return [{"consent_id": r[0], "mode": r[1], "provider_id": r[2], "purposes": list(r[3]), "terms_version": r[4], "granted_at": iso(r[5]),
                 "revoked_at": iso(r[6])}
                for r in query(snap, "SELECT consent_id, mode, provider_id, purposes, terms_version, granted_at, revoked_at FROM TryOnConsents "
                                     "WHERE member_id=@m ORDER BY granted_at", m, _M)]
    if category == "media.tryon_media":
        jobs = [{"job_id": r[0], "mode": r[1], "provider_id": r[2], "state": r[3], "fidelity_label": r[4], "saved": r[5], "expires_at": iso(r[6]),
                 "provider_deletion": r[7]}
                for r in query(snap, "SELECT job_id, mode, provider_id, state, fidelity_label, saved, expires_at, provider_deletion FROM TryOnJobs "
                                     "WHERE member_id=@m ORDER BY created_at", m, _M)]
        media = [{"media_id": r[0], "job_id": r[1], "kind": r[2], "state": r[3], "content_type": r[4], "bytes": r[5], "saved": r[6],
                  "expires_at": iso(r[7]), "deleted_at": iso(r[8]), "image": "available through the authenticated export download" if r[6] else None}
                 for r in query(snap, "SELECT media_id, job_id, kind, state, content_type, bytes, saved, expires_at, deleted_at FROM MediaObjects "
                                      "WHERE member_id=@m ORDER BY created_at", m, _M)]
        return [{"jobs": jobs, "media": media}]
    raise KeyError(category)


def delete_category(txn, member_id: str, category: str) -> int:
    m = {"m": member_id}
    if category == "media.tryon_consents":
        return txn.execute_update("DELETE FROM TryOnConsents WHERE member_id=@m", params=m, param_types=_M)
    if category == "media.tryon_media":
        n = txn.execute_update("DELETE FROM TryOnJobs WHERE member_id=@m", params=m, param_types=_M)
        # Tombstone first; ``purge_member`` removes blobs after commit, then the rows.
        return n + txn.execute_update("UPDATE MediaObjects SET state='deleted', saved=FALSE, deleted_at=CURRENT_TIMESTAMP() "
                                      "WHERE member_id=@m AND deleted_at IS NULL", params=m, param_types=_M)
    raise KeyError(category)


def purge_member(db, member_id: str) -> Dict[str, Any]:
    """After commit: delete the member's blobs, then the tombstoned rows."""
    rows = run_read(db, lambda s: query(s, "SELECT media_id, storage_ref FROM MediaObjects WHERE member_id=@m AND deleted_at IS NOT NULL",
                                        {"m": member_id}, _M))
    if rows and _STORE is None:
        return {"done": False, "pending": len(rows), "detail": "media store not configured; blobs pending purge"}
    for _, ref in rows:
        _STORE.delete(ref)
    run_txn(db, lambda t: t.execute_update("DELETE FROM MediaObjects WHERE member_id=@m AND deleted_at IS NOT NULL",
                                           params={"m": member_id}, param_types=_M))
    return {"done": True, "purged": len(rows)}


def _delete(db, member_id: str, category: str) -> int:
    n = run_txn(db, lambda t: delete_category(t, member_id, category))
    if category == "media.tryon_media":
        purge_member(db, member_id)
    return n


for _key, _c in CATEGORIES.items():
    register_data_category(FoundationDataCategory(
        name=_key, domain=DOMAIN, description=_c["title"], supplied_by=_c["supplied_by"], visible_to="member only",
        retention=_c["retention"], tables=_c["tables"],
        export=(lambda k: lambda db, mid: run_read(db, lambda s: export_category(s, mid, k)))(_key),
        delete=(lambda k: lambda db, mid: _delete(db, mid, k))(_key),
    ))


def build_privacy_handler():
    """A fresh handler instance, or None when the privacy lane is absent."""
    try:
        from brandme_core.domains.privacy import deletion as pd
    except ImportError:
        return None

    class MediaPrivacyHandler:
        domain = DOMAIN

        def categories(self):
            return [pd.DataCategory(key=k, domain=DOMAIN, title=c["title"], supplied_by=pd.Supplier.MEMBER, visible_to=("member",),
                                    retention=c["retention"], on_edit=c["on_edit"], on_delete=pd.OnDelete.ERASE)
                    for k, c in CATEGORIES.items()]

        def export(self, snapshot, ctx, category):
            return pd.ExportSection(category, export_category(snapshot, ctx.subject_ref, category))

        def delete(self, txn, ctx, category):
            return record_scope_refusal(pd, ctx, category) or pd.DeletionOutcome(category, delete_category(txn, ctx.subject_ref, category))

        def purge_derived(self, ctx, category):
            if category != "media.tryon_media":
                return pd.DeletionOutcome(category, 0, done=True, detail="no blobs for this category")
            if _DB is None:
                return pd.DeletionOutcome(category, 0, done=False, detail="media service not wired; blobs pending purge")
            out = purge_member(_DB, ctx.subject_ref)
            return pd.DeletionOutcome(category, out.get("purged", 0), done=out["done"], detail=out.get("detail", "blobs purged"))

        def reapply_tombstone(self, txn, tombstone):
            if tombstone.record_keys:
                return 0  # record-level deletions are refused by delete(); nothing to reapply
            return delete_category(txn, tombstone.subject_ref, tombstone.category)

    return MediaPrivacyHandler()


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
