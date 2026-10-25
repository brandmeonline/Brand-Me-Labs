"""My Data and account deletion for the foundation's own platform records (Q19).

The privacy orchestrator never knows table names: every table owner registers
a handler (domains/privacy/deletion.py:6-10). Foundation owns ``OutboxEvents``
and ``IdempotencyRecords`` (V001), so it declares two categories:

* ``platform.event_outbox``: undelivered events naming the subject are
  withdrawn in place and delivered ones deleted (``retention.py``);
* ``platform.request_replay``: the subject's replay records are deleted and
  other members' replay bodies are unlinked from them.

``register_platform_privacy`` puts them in the foundation ``data_categories()``
catalog (so ``bridge_foundation_categories`` sees them) and, when the privacy
lane is installed, in its default registry as a native handler. The handler is
non-transactional: ``delete_outside_txn`` runs Partitioned DML before the
orchestrator's tombstone transaction, and restore re-applies it the same way
(privacy.py:296-299, :444-455). ``brandme_core/domains/__init__.py`` calls it;
the privacy lane is imported lazily, never at module level.
"""
from __future__ import annotations

from typing import Any, Optional

from . import retention

DOMAIN = "platform"
EVENT_OUTBOX, REQUEST_REPLAY = retention.CATEGORIES
VISIBLE_TO = "brand.me services"

CATEGORIES = {
    EVENT_OUTBOX: {
        "title": "Delivery records of changes you made, and of other members' changes that name you",
        "retention": ("Delivered event records are purged 7 days after delivery; records not yet delivered are "
                      "withdrawn when you delete your account; copies already handed to our message broker are not "
                      "recalled and expire under its retention (configured at 24 hours or more)."),
        "on_edit": "Not editable: each record describes a change that was already made",
        "tables": ("OutboxEvents",),
    },
    REQUEST_REPLAY: {
        "title": "Saved responses that stop a retried request from being applied twice",
        "retention": ("Each record is marked to expire 30 days after the request, but expired records are not yet "
                      "purged automatically; yours are deleted when you delete your account, and you are unlinked "
                      "from other members' records that mention you."),
        "on_edit": "Not editable: a retried request replays the saved response",
        "tables": ("IdempotencyRecords",),
    },
}
RECORD_LEVEL_REFUSED = ("platform records are erased per subject only; a record-level request was not applied "
                        "so nothing was over-deleted")
BROKER_COPIES = "published broker copies are not recalled; they expire with topic retention (24 hours or more)"
EVENT_NOTES = ["Only events caused by your own actions are listed. Event contents are not exported because they "
               "can name other members."]
REPLAY_NOTES = ["Saved responses are not exported because they can contain other members' data."]


def _privacy():
    from brandme_core.domains.privacy import deletion as pd

    return pd


def _params(subject_ref: str) -> tuple[dict, dict]:
    from google.cloud.spanner_v1 import param_types

    return {"s": list(retention.subject_keys(subject_ref))}, {"s": param_types.Array(param_types.STRING)}


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


def _delete_events(database: Any, member_id: str) -> None:
    retention.erase_subject_events(database, [member_id])


def _delete_requests(database: Any, member_id: str) -> None:
    retention.erase_subject_requests(database, [member_id])


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
        if ctx.record_keys:
            # Same answer as the lanes' whole-category handlers: refused, truthfully.
            return pd.DeletionOutcome(category, 0, done=True, exception=RECORD_LEVEL_REFUSED)
        if category == EVENT_OUTBOX:
            withdrawn, deleted = retention.erase_subject_events(database, [ctx.subject_ref])
            return pd.DeletionOutcome(category, withdrawn + deleted,
                                      detail=f"{withdrawn} undelivered withdrawn, {deleted} delivered deleted")
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

    for key, export, delete in ((EVENT_OUTBOX, _export_events, _delete_events),
                                (REQUEST_REPLAY, _export_requests, _delete_requests)):
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
