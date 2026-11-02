"""My Data and account deletion for the foundation's own platform records (Q19).

The privacy orchestrator never knows table names: every table owner registers
a handler (domains/privacy/deletion.py:6-10). Foundation owns ``OutboxEvents``
and ``IdempotencyRecords`` (V001), so it declares two categories:

* ``platform.event_outbox``: the subject's own undelivered events are
  withdrawn in place and their delivered ones deleted; other members' events
  that name them keep their rows with the subject unlinked (``retention.py``);
* ``platform.request_replay``: the subject's replay records are deleted and
  other members' replay bodies are unlinked from them.

Both are account-scope only: they hold the records an active account needs
(undelivered changes, replay protection), so a category-only request, a
record-level request and a subject ref the platform cannot match safely are
refused with a truthful outcome that changes nothing, never an error that
would stop the job's other categories.

``register_platform_privacy`` puts them in the foundation ``data_categories()``
catalog (inventory and export) and, when the privacy lane is installed, in its
default registry as a native handler. The handler is non-transactional:
``delete_outside_txn`` runs before the orchestrator's tombstone transaction,
and restore re-applies it the same way (privacy.py:296-299, :444-455). The
catalog's delete callback, which only ``bridge_foundation_categories`` would
call, raises: that path cannot report a refusal or a count, so a job composed
through it fails loudly instead of claiming "deleted". Compositions use the
native handler. ``brandme_core/domains/__init__.py`` calls it; the
privacy lane is imported lazily, never at module level.
"""
from __future__ import annotations

from typing import Any, Optional

from . import retention

DOMAIN = "platform"
EVENT_OUTBOX, REQUEST_REPLAY = retention.CATEGORIES
VISIBLE_TO = "brand.me services"
ACCOUNT_ONLY = ("These records are erased only when you delete your whole account; a request to delete only this "
                "category is refused and changes nothing.")

CATEGORIES = {
    EVENT_OUTBOX: {
        "title": "Delivery records of changes you made, and of other members' changes that name you",
        "retention": ("Delivered event records are purged 7 days after delivery. Records whose delivery failed keep "
                      "their contents until our operators resolve them or you delete your account. When you delete "
                      "your account, records of your own changes are deleted, or emptied and never sent if not yet "
                      "delivered; in other members' records that name you, your ID is replaced by a placeholder for a "
                      "deleted member. A delivery already in progress at that moment may still reach our message "
                      "broker, and copies already handed to it are not recalled; they expire under its retention "
                      "(configured at 24 hours or more). " + ACCOUNT_ONLY),
        "on_edit": "Not editable: each record describes a change that was already made",
        "tables": ("OutboxEvents",),
    },
    REQUEST_REPLAY: {
        "title": "Saved responses that stop a retried request from being applied twice",
        "retention": ("Each record is marked to expire 30 days after the request, but expired records are not yet "
                      "purged automatically. When you delete your account, yours are deleted, and in other members' "
                      "records that mention you, your ID is replaced by a placeholder for a deleted member. "
                      + ACCOUNT_ONLY),
        "on_edit": "Not editable: a retried request replays the saved response",
        "tables": ("IdempotencyRecords",),
    },
}
RECORD_LEVEL_REFUSED = ("platform records are erased per subject only; a record-level request was not applied "
                        "so nothing was over-deleted")
ACCOUNT_SCOPE_REFUSED = ("platform records are erased only by a whole-account deletion; this category-only request "
                         "was not applied, so an active account keeps its undelivered changes and replay protection")
UNMATCHABLE_REFUSED = ("platform records were not erased: this subject reference contains characters the platform "
                       "cannot match safely")
REFUSAL_REAPPLIED = "refused when the deletion ran; nothing to re-apply"
BROKER_COPIES = "published broker copies are not recalled; they expire with topic retention (24 hours or more)"
EVENT_NOTES = ["Only events caused by your own actions are listed. Event contents are not exported because they "
               "can name other members."]
REPLAY_NOTES = ["Saved responses are not exported because they can contain other members' data."]


def _privacy():
    from brandme_core.domains.privacy import deletion as pd

    return pd


def _params(subject_ref: str) -> tuple[dict, dict]:
    from google.cloud.spanner_v1 import param_types

    # Export matches actors and principals by equality only, which is safe for any ref.
    keys = retention.subject_keys(subject_ref) if retention.matchable(subject_ref) else (subject_ref,)
    return {"s": list(keys)}, {"s": param_types.Array(param_types.STRING)}


def _refusal(database: Any, ctx: Any, category: str) -> Optional[tuple[str, bool]]:
    """Why this request may not erase platform records, and whether that refusal is already recorded.

    ``None`` means erase: a whole-category step of an account-scope job for a
    matchable subject. The refusal is recorded when the job's step for this
    category is already done: then this call is a restore re-applying the
    tombstone (run_deletion only calls a step that is not done, privacy.py:295).

    No job row at all can only be a restore whose backup predates the job and
    that carried the tombstone ledger without DeletionJobs (run_deletion always
    has its job). Scope is then unknowable, because every category of a job gets
    a tombstone, refused ones included (privacy.py:307-308). Privacy wins: the
    tombstone is re-applied as an erasure. The cost is that a category-only
    request on a still-active member, restored this way, also erases that
    member's undelivered events and replay records. Carry DeletionJobs with
    the tombstones to keep refusals as no-ops.
    """
    from google.cloud.spanner_v1 import param_types

    with database.snapshot() as snap:
        rows = list(snap.execute_sql(
            "SELECT j.scope, j.subject_ref, (SELECT s.state FROM DeletionSteps AS s WHERE s.job_id = j.job_id "
            "AND s.category = @c AND s.step = 'delete_records') FROM DeletionJobs AS j WHERE j.job_id = @j",
            params={"j": ctx.job_id, "c": category}, param_types={"j": param_types.STRING, "c": param_types.STRING}))
    scope, subject, step = rows[0] if rows else ("account", ctx.subject_ref, None)  # no job: see docstring
    if ctx.record_keys:
        reason = RECORD_LEVEL_REFUSED  # same answer as the lanes' whole-category handlers
    elif scope != "account" or subject != ctx.subject_ref:
        reason = ACCOUNT_SCOPE_REFUSED
    elif not retention.matchable(ctx.subject_ref):
        reason = UNMATCHABLE_REFUSED
    else:
        return None
    return reason, step in ("done", "exception_done")


def export_events(reader: Any, subject_ref: str) -> list[dict]:
    """Metadata of events the subject caused (actor match), never payloads.

    Another member's event that names the subject is theirs: even its type
    (for example a report filed about the subject) is not disclosed.
    """
    params, types = _params(subject_ref)
    rows = reader.execute_sql(
        "SELECT event_type, occurred_at, status FROM OutboxEvents WHERE EXISTS(SELECT 1 FROM UNNEST(@s) AS x "
        "WHERE actor_ref = CONCAT('member:', x) OR STARTS_WITH(actor_ref, CONCAT('member:', x, '/'))) "
        "ORDER BY occurred_at, event_type", params=params, param_types=types)
    return [{"event_type": t, "occurred_at": o.isoformat(), "status": s} for t, o, s in rows]


def export_requests(reader: Any, subject_ref: str) -> list[dict]:
    """The subject's replay records: operation and times, never the saved body or key."""
    params, types = _params(subject_ref)
    rows = reader.execute_sql(
        f"SELECT operation, created_at, expires_at FROM IdempotencyRecords WHERE {retention.PRINCIPAL_MATCH} "
        "ORDER BY created_at, operation", params=params, param_types=types)
    return [{"operation": op, "created_at": c.isoformat(), "expires_at": e.isoformat()} for op, c, e in rows]


# Foundation-catalog callbacks ``(database, member_id)``; module-level so that
# re-registering an identical DataCategory compares equal (base.py:255-259).
def _export_events(database: Any, member_id: str) -> list[dict]:
    with database.snapshot() as snap:
        return export_events(snap, member_id)


def _export_requests(database: Any, member_id: str) -> list[dict]:
    with database.snapshot() as snap:
        return export_requests(snap, member_id)


def _bridge_delete(database: Any, member_id: str) -> None:
    # The bridge's callback cannot report a refusal or a count, and it always
    # reports "deleted" (foundation_bridge.py:56-58). Fail the job loudly instead
    # of issuing a receipt that is not true; compositions call register_platform_privacy.
    raise RuntimeError("platform categories need the native handler (brandme_core.events.erasure.register_platform_privacy)")


class PlatformPrivacyHandler:
    """Native ``DomainPrivacyHandler`` for the two platform categories."""

    domain = DOMAIN
    transactional = False  # Partitioned DML cannot run inside the orchestrator's transaction

    def categories(self):
        pd = _privacy()
        return [pd.DataCategory(key=k, domain=DOMAIN, title=c["title"], supplied_by=pd.Supplier.SYSTEM,
                                visible_to=(VISIBLE_TO,), retention=c["retention"], on_edit=c["on_edit"],
                                on_delete=pd.OnDelete.ERASE)
                for k, c in CATEGORIES.items()]

    def export(self, snapshot, ctx, category):
        pd = _privacy()
        if category == EVENT_OUTBOX:
            return pd.ExportSection(category, export_events(snapshot, ctx.subject_ref), notes=list(EVENT_NOTES))
        if category == REQUEST_REPLAY:
            return pd.ExportSection(category, export_requests(snapshot, ctx.subject_ref), notes=list(REPLAY_NOTES))
        raise KeyError(category)

    def delete(self, txn, ctx, category):
        raise RuntimeError("platform categories are deleted outside the orchestrator transaction")

    def delete_outside_txn(self, database, ctx, category):
        pd = _privacy()
        if category not in CATEGORIES:
            raise KeyError(category)
        refused = _refusal(database, ctx, category)
        if refused:
            reason, recorded = refused
            if recorded:
                # A restore re-applying a refused tombstone: nothing was erased, so nothing is owed.
                return pd.DeletionOutcome(category, 0, detail=REFUSAL_REAPPLIED)
            # The lanes' refusal shape: done, nothing changed, the truthful reason.
            return pd.DeletionOutcome(category, 0, done=True, exception=reason)
        if category == EVENT_OUTBOX:
            withdrawn, deleted, unlinked = retention.erase_subject_events(database, [ctx.subject_ref])
            return pd.DeletionOutcome(category, withdrawn + deleted + unlinked,
                                      detail=f"{withdrawn} undelivered withdrawn, {deleted} delivered deleted, "
                                             f"{unlinked} other events unlinked")
        deleted, unlinked = retention.erase_subject_requests(database, [ctx.subject_ref])
        return pd.DeletionOutcome(category, deleted + unlinked,
                                  detail=f"{deleted} deleted, {unlinked} other members' records unlinked")

    def purge_derived(self, ctx, category):
        pd = _privacy()
        if category == EVENT_OUTBOX:
            return pd.DeletionOutcome(category, 0, detail=BROKER_COPIES)
        if category == REQUEST_REPLAY:
            return pd.DeletionOutcome(category, 0, detail="no derived copies outside Spanner")
        raise KeyError(category)

    def reapply_tombstone(self, txn, tombstone):
        raise RuntimeError("restore re-applies platform tombstones through delete_outside_txn")


PLATFORM_PRIVACY_HANDLER = PlatformPrivacyHandler()


def register_foundation_categories() -> None:
    from brandme_core.domains.base import DataCategory, register_data_category

    for key, export, delete in ((EVENT_OUTBOX, _export_events, _bridge_delete),
                                (REQUEST_REPLAY, _export_requests, _bridge_delete)):
        c = CATEGORIES[key]
        register_data_category(DataCategory(
            name=key, domain=DOMAIN, description=c["title"], supplied_by="system", visible_to=VISIBLE_TO,
            retention=c["retention"], tables=c["tables"], export=export, delete=delete))


def register_platform_privacy(reg: Optional[Any] = None) -> Optional[PlatformPrivacyHandler]:
    """Register both catalogs; ``reg`` defaults to the privacy lane's default registry.

    Idempotent. Returns the native handler, or ``None`` when the privacy lane
    is not installed or another handler already owns the platform keys.
    """
    register_foundation_categories()
    try:
        pd = _privacy()
    except ImportError:
        return None
    try:
        pd.register_domain(PLATFORM_PRIVACY_HANDLER, reg)
    except pd.PrivacyRegistryError:
        # A lane-local stand-in owns the keys (as in social/deletion.py:198-212); never register twice.
        return None
    return PLATFORM_PRIVACY_HANDLER
