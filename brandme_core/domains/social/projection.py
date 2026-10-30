"""
Share projector: this lane's reducers for foundation's projection framework
(``brandme_core/events/projections.py``; Ultra plan 02, item 10).

* ``share.created`` → one shared document per invited member at
  ``shared/{share_id}/recipients/{member_id}``. It holds the share's kind and
  its filtered preview, read from Spanner at reduce time and never taken from
  the event. Only ``selected_members`` shares are projected; link shares are
  resolved through the API and have no recipient copies.
* ``share.revoked`` → delete every recipient copy and tombstone the share, so a
  delayed upsert cannot bring it back. A share id is never reused, so the
  tombstone is permanent.
* ``share.audience_changed`` (a block or an unfriend removed a recipient) →
  re-project the grant at its new version: the framework deletes the copy of
  every member no longer in the audience. With nobody left, every copy goes.
* **What the shared projection never carries:** anything the framework treats
  as private (owner, member, price, size, persona axes …). A preview field that
  would be refused is left out of the projection; the full preview stays behind
  the API's authorization.

``register_share_projector`` registers both reducers with a registry (the
foundation's module-level ``registry`` by default). The reducers read the
database they are given, so the worker that applies the registry passes it;
one database per process, and the first registration wins.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

from brandme_core.events.projections import Delete, ProjectionRegistry, ProjectionSpec, Upsert, is_private_field
from brandme_core.events.projections import registry as default_registry

from brandme_core.domains.persona.kernel import STR, json_value, query, run_read, server_now

SHARE_SPEC = ProjectionSpec("member_share", "shared", "shared/{share_id}", frozenset({"kind", "preview"}))
REVOKED_FOREVER = 2 ** 53  # share ids are never reused


def _drop_private(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _drop_private(v) for k, v in node.items() if not is_private_field(k)}
    if isinstance(node, list):
        return [_drop_private(v) for v in node]
    return node


def share_reducers(database) -> Dict[str, Callable[[Any], Iterable[Any]]]:
    def project(share_id: str, *, emptied: bool) -> List[Any]:
        def read(s):
            rows = query(s, "SELECT g.subject_type, g.audience, g.recipient_ids, g.expires_at, g.revoked_at, g.version, p.preview "
                            "FROM ShareGrants@{FORCE_INDEX=ShareGrantsById} g LEFT JOIN SharePreviews p "
                            "ON p.member_id = g.member_id AND p.share_id = g.share_id WHERE g.share_id=@s", {"s": share_id}, {"s": STR})
            return rows, server_now(s)

        rows, now = run_read(database, read)
        if not rows:
            return []  # deleted before projection: nothing to show
        kind, audience, recipients, expires_at, revoked_at, version, preview = rows[0]
        if audience != "selected_members" or revoked_at is not None or expires_at <= now or preview is None:
            return []
        if not recipients:
            # Everyone left: remove every copy at this version (recipients are never added back).
            return [Delete(SHARE_SPEC, {"share_id": share_id}, int(version))] if emptied else []
        return [Upsert(SHARE_SPEC, {"share_id": share_id}, {"kind": kind, "preview": _drop_private(json_value(preview))}, int(version),
                       audience_member_ids=tuple(recipients), expires_at=expires_at)]

    def created(event) -> List[Any]:
        return project(event.payload["share_id"], emptied=False)

    def audience_changed(event) -> List[Any]:
        return project(event.payload["share_id"], emptied=True)

    def revoked(event) -> List[Any]:
        return [Delete(SHARE_SPEC, {"share_id": event.payload["share_id"]}, REVOKED_FOREVER)]

    return {"share.created": created, "share.revoked": revoked, "share.audience_changed": audience_changed}


def register_share_projector(database, registry: Optional[ProjectionRegistry] = None) -> List[str]:
    reg = registry if registry is not None else default_registry
    out = []
    for event_type, reducer in share_reducers(database).items():
        existing = reg.reducers.get(event_type)
        if existing is not None and getattr(existing, "__qualname__", "") == reducer.__qualname__:
            continue  # this lane's reducer is already registered (re-import or a second worker setup)
        reg.register(event_type, reducer)
        out.append(event_type)
    return out
