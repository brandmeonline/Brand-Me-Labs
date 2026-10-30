"""Share projector (Ultra plan 02 item 10): this lane's reducers on foundation's
projection framework, against the Spanner and Firestore emulators."""

from __future__ import annotations

import os
import socket
import uuid

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import member_principal
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.social.projection import SHARE_SPEC, register_share_projector
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.social.shares import ShareService
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.events import EventEnvelope
from brandme_core.events.projections import ProjectionRegistry, ProjectionStore
from test_persona_harness import MEMBER_SCOPES, spanner_db  # noqa: F401
from test_persona_harness import insert_member

OUTBOX_COLS = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version", "environment",
               "actor_ref", "correlation_id", "causation_id", "privacy_class", "payload", "occurred_at")


def _firestore_up() -> bool:
    h, _, p = os.environ.get("FIRESTORE_EMULATOR_HOST", "").partition(":")
    if not h:
        return False
    try:
        with socket.create_connection((h, int(p or 8080)), timeout=1):
            return True
    except OSError:
        return False


if os.environ.get("BRANDME_REQUIRE_EMULATORS") == "1" and not _firestore_up():
    raise RuntimeError("BRANDME_REQUIRE_EMULATORS=1 but the Firestore emulator is not reachable")
pytestmark = pytest.mark.skipif(not _firestore_up(), reason="Firestore emulator not reachable (FIRESTORE_EMULATOR_HOST)")


def key():
    return "k-" + uuid.uuid4().hex


def event(db, event_type, share_id):
    with db.snapshot() as s:
        rows = list(s.execute_sql(f"SELECT {', '.join(OUTBOX_COLS)} FROM OutboxEvents WHERE event_type=@t AND JSON_VALUE(payload, '$.share_id')=@s",
                                  params={"t": event_type, "s": share_id}, param_types={"t": param_types.STRING, "s": param_types.STRING}))
    assert len(rows) == 1, (event_type, share_id)
    return EventEnvelope.from_row(dict(zip(OUTBOX_COLS, rows[0])))


def events(db, event_type, share_id):
    with db.snapshot() as s:
        rows = list(s.execute_sql(f"SELECT {', '.join(OUTBOX_COLS)} FROM OutboxEvents WHERE event_type=@t AND JSON_VALUE(payload, '$.share_id')=@s "
                                  "ORDER BY aggregate_version", params={"t": event_type, "s": share_id},
                                  param_types={"t": param_types.STRING, "s": param_types.STRING}))
    return [EventEnvelope.from_row(dict(zip(OUTBOX_COLS, r))) for r in rows]


@pytest.fixture
def store():
    from google.cloud import firestore

    return ProjectionStore(firestore.Client(project=f"bm-share-{uuid.uuid4().hex[:8]}"))


def test_selected_member_shares_project_per_recipient_and_revocation_removes_them(spanner_db, store):
    db = spanner_db
    owner, friend, other = (member_principal(insert_member(db), MEMBER_SCOPES) for _ in range(3))
    rel = RelationshipService(db)
    for f in (friend, other):
        rel.accept(f, rel.request(owner, f.member_id)["relationship_id"])
    item = WardrobeService(db).create_items(owner, {"source": "manual", "title": "Linen shirt", "category": "top", "color_family": "neutral"},
                                            key())["items"][0]["id"]
    reg = ProjectionRegistry()
    assert register_share_projector(db, reg) == ["share.created", "share.revoked", "share.audience_changed"]
    assert register_share_projector(db, reg) == []  # idempotent

    shares = ShareService(db)
    grant = shares.create(owner, {"subject_type": "wardrobe_item", "subject_id": item, "audience": "selected_members",
                                  "allowed_fields": ["title", "category"], "recipient_ids": [friend.member_id],
                                  "expires_at": "2027-01-01T00:00:00+00:00"}, key())
    sid = grant["share_id"]
    assert reg.apply(store, event(db, "share.created", sid)) == ["applied"]
    copy = store.get(SHARE_SPEC, {"share_id": sid}, recipient=friend.member_id)
    assert copy["kind"] == "wardrobe_item" and copy["preview"] == {"title": "Linen shirt", "category": "top"}
    assert store.get(SHARE_SPEC, {"share_id": sid}, recipient=other.member_id) is None  # not invited, no copy
    assert owner.member_id not in str(copy)

    # A link share has no recipient copies; it is resolved through the API only.
    link = shares.create(owner, {"subject_type": "wardrobe_item", "subject_id": item, "audience": "unlisted", "allowed_fields": ["title"],
                                 "recipient_ids": [], "expires_at": "2027-01-01T00:00:00+00:00"}, key())
    assert reg.apply(store, event(db, "share.created", link["share_id"])) == []

    # Persona axes never reach a shared projection, even when the share itself allows them.
    persona = PersonaService(db)
    persona.patch(owner, '"0"', {"changes": [{"axis": "expression", "value": 80, "locked": False}], "client_revision": "c"})
    snap = persona.create_snapshot(owner, "Summer")
    ss = shares.create(owner, {"subject_type": "persona_snapshot", "subject_id": snap["snapshot_id"], "audience": "selected_members",
                               "allowed_fields": ["saved_name", "declared_axes"], "recipient_ids": [friend.member_id],
                               "expires_at": "2027-01-01T00:00:00+00:00"}, key())
    assert reg.apply(store, event(db, "share.created", ss["share_id"])) == ["applied"]
    assert store.get(SHARE_SPEC, {"share_id": ss["share_id"]}, recipient=friend.member_id)["preview"] == {"saved_name": "Summer"}

    # Revocation removes every copy and tombstones the share against late upserts.
    shares.revoke(owner, sid)
    assert reg.apply(store, event(db, "share.revoked", sid)) == ["applied"]
    assert store.get(SHARE_SPEC, {"share_id": sid}, recipient=friend.member_id) is None
    assert reg.apply(store, event(db, "share.created", sid)) == []  # the grant is revoked; nothing to project


def test_block_and_unfriend_remove_the_recipients_projected_copy(spanner_db, store):
    db = spanner_db
    owner, a, b = (member_principal(insert_member(db), MEMBER_SCOPES) for _ in range(3))
    rel = RelationshipService(db)
    for f in (a, b):
        rel.accept(f, rel.request(owner, f.member_id)["relationship_id"])
    item = WardrobeService(db).create_items(owner, {"source": "manual", "title": "Wool scarf", "category": "accessory"}, key())["items"][0]["id"]
    reg = ProjectionRegistry()
    register_share_projector(db, reg)
    sid = ShareService(db).create(owner, {"subject_type": "wardrobe_item", "subject_id": item, "audience": "selected_members",
                                          "allowed_fields": ["title"], "recipient_ids": [a.member_id, b.member_id],
                                          "expires_at": "2027-01-01T00:00:00+00:00"}, key())["share_id"]
    assert reg.apply(store, event(db, "share.created", sid)) == ["applied"]

    def copy(who):
        return store.get(SHARE_SPEC, {"share_id": sid}, recipient=who.member_id)

    assert copy(a) and copy(b)
    # a blocks the owner: a leaves the share and a's copy goes; b keeps theirs.
    rel.block(a, owner.member_id)
    (changed,) = events(db, "share.audience_changed", sid)
    assert reg.apply(store, changed) == ["applied"]
    assert copy(a) is None and copy(b)["preview"] == {"title": "Wool scarf"}
    # The owner unfriends b: nobody is left, so every copy goes.
    rel.remove(owner, b.member_id)
    assert reg.apply(store, events(db, "share.audience_changed", sid)[1]) == ["applied"]
    assert copy(a) is None and copy(b) is None
    # Late or repeated deliveries cannot bring a copy back.
    assert reg.apply(store, event(db, "share.created", sid)) == []
    reg.apply(store, changed)  # re-reads the grant as it is now: still nobody
    assert copy(a) is None and copy(b) is None
