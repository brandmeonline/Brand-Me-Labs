"""Firestore projections against the emulator (BM-FND-006: revocation removes shared projections)."""
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.events.projections import (
    Delete, ProjectionError, ProjectionRegistry, ProjectionSpec, ProjectionStore, Upsert, is_private_field,
)


def _firestore_up() -> bool:
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    h, _, p = host.partition(":")
    if not host:
        return False
    try:
        with socket.create_connection((h, int(p or 8080)), timeout=1):
            return True
    except OSError:
        return False


if os.environ.get("BRANDME_REQUIRE_EMULATORS") == "1" and not _firestore_up():
    raise RuntimeError("BRANDME_REQUIRE_EMULATORS=1 but the Firestore emulator is not reachable")
pytestmark = pytest.mark.skipif(not _firestore_up(), reason="Firestore emulator not reachable (FIRESTORE_EMULATOR_HOST)")

PROFILE = ProjectionSpec("member_profile", "member_private", "members/{member_id}/views/profile",
                         frozenset({"display_name", "room_theme"}))
SHARED_OUTFIT = ProjectionSpec("shared_outfit", "shared", "shared/{share_id}",
                               frozenset({"title", "items", "caption"}))


@pytest.fixture
def store():
    from google.cloud import firestore
    return ProjectionStore(firestore.Client(project=f"bm-proj-{uuid.uuid4().hex[:8]}"))


def _share(share_id, version, title="Look", audience=("friend-1",)):
    return Upsert(SHARED_OUTFIT, {"share_id": share_id}, {"title": title, "items": [{"title": "Tee"}]}, version,
                  audience_member_ids=audience, expires_at=datetime.now(timezone.utc) + timedelta(days=1))


def test_monotonic_upserts_ignore_redelivered_and_older_versions(store):
    key = {"member_id": "m-" + uuid.uuid4().hex[:8]}
    assert store.apply(Upsert(PROFILE, key, {"display_name": "Ada"}, 2)) == "applied"
    assert store.apply(Upsert(PROFILE, key, {"display_name": "Ada"}, 2)) == "stale"      # redelivery
    assert store.apply(Upsert(PROFILE, key, {"display_name": "Old"}, 1)) == "stale"      # out of order
    assert store.get(PROFILE, key)["display_name"] == "Ada"
    assert store.apply(Upsert(PROFILE, key, {"display_name": "Ada L"}, 3)) == "applied"
    assert store.get(PROFILE, key)["source_version"] == 3


def _copy(store, share_id, member="friend-1"):
    return store.get(SHARED_OUTFIT, {"share_id": share_id}, recipient=member)


def test_revocation_deletes_share_and_blocks_resurrection(store):
    share_id = "s-" + uuid.uuid4().hex
    assert store.apply(_share(share_id, 1)) == "applied"
    assert _copy(store, share_id)["title"] == "Look"
    assert store.apply(Delete(SHARED_OUTFIT, {"share_id": share_id}, 2)) == "applied"
    assert _copy(store, share_id) is None
    # A delayed older update must not bring the revoked share back.
    assert store.apply(_share(share_id, 1, title="stale")) == "revoked"
    assert store.apply(_share(share_id, 2, title="stale")) == "revoked"
    assert _copy(store, share_id) is None
    # A genuinely newer re-share (new grant revision) is allowed.
    assert store.apply(_share(share_id, 3, title="again")) == "applied"


def test_superseded_revocation_does_not_delete_newer_view(store):
    share_id = "s-" + uuid.uuid4().hex
    store.apply(_share(share_id, 5))
    assert store.apply(Delete(SHARED_OUTFIT, {"share_id": share_id}, 4)) == "stale"
    assert _copy(store, share_id) is not None


def test_shared_projections_refuse_private_fields_and_require_audience(store):
    share_id = "s-" + uuid.uuid4().hex
    with pytest.raises(ProjectionError, match="fields not allowed"):
        store.apply(Upsert(SHARED_OUTFIT, {"share_id": share_id}, {"owner_id": "m1"}, 1,
                           audience_member_ids=("f",), expires_at=datetime.now(timezone.utc)))
    with pytest.raises(ProjectionError, match="private field"):
        store.apply(Upsert(SHARED_OUTFIT, {"share_id": share_id}, {"items": [{"price": 100}]}, 1,
                           audience_member_ids=("f",), expires_at=datetime.now(timezone.utc)))
    with pytest.raises(ProjectionError, match="audience"):
        store.apply(Upsert(SHARED_OUTFIT, {"share_id": share_id}, {"title": "x"}, 1,
                           expires_at=datetime.now(timezone.utc)))
    assert _copy(store, share_id) is None


def test_shared_copies_are_per_recipient_and_carry_no_audience(store):
    share_id = "s-" + uuid.uuid4().hex
    store.apply(_share(share_id, 1, audience=("bo", "cy")))
    for member in ("bo", "cy"):
        copy = _copy(store, share_id, member)
        assert copy["title"] == "Look"
        assert not any(is_private_field(k) for k in copy), copy
        assert "bo" not in str(copy) and "cy" not in str(copy)
    # Dropping a recipient removes their copy on the next version.
    store.apply(_share(share_id, 2, audience=("bo",)))
    assert _copy(store, share_id, "bo")["source_version"] == 2
    assert _copy(store, share_id, "cy") is None
    with pytest.raises(ProjectionError, match="unique"):
        store.apply(_share(share_id, 3, audience=("bo", "bo")))


def test_shared_expiry_must_be_timezone_aware(store):
    with pytest.raises(ProjectionError, match="timezone-aware"):
        store.apply(Upsert(SHARED_OUTFIT, {"share_id": "s-" + uuid.uuid4().hex}, {"title": "x"}, 1,
                           audience_member_ids=("bo",), expires_at=datetime.utcnow() + timedelta(days=1)))


@pytest.mark.parametrize("name", ["ownerId", "owner", "memberId", "walletAddress", "bodyMeasurements",
                                  "purchase_price", "Audience", "recipientIds", "ShippingAddress"])
def test_private_fields_are_caught_in_any_naming_style(store, name):
    with pytest.raises(ProjectionError):
        ProjectionSpec("x", "shared", "shared/{share_id}", frozenset({name}))
    spec = ProjectionSpec("ok", "shared", "shared/{share_id}", frozenset({"items"}))
    with pytest.raises(ProjectionError, match="private field"):
        store.apply(Upsert(spec, {"share_id": "s-" + uuid.uuid4().hex}, {"items": [{name: "v"}]}, 1,
                           audience_member_ids=("bo",), expires_at=datetime.now(timezone.utc) + timedelta(days=1)))


def test_specs_reject_unsafe_shapes():
    with pytest.raises(ProjectionError):
        ProjectionSpec("x", "shared", "shared/{share_id}", frozenset({"owner_id"}))
    with pytest.raises(ProjectionError):
        ProjectionSpec("x", "member_private", "shared/{id}", frozenset({"a"}))
    with pytest.raises(ProjectionError):
        ProjectionSpec("x", "shared", "shared/{share_id}/views", frozenset({"a"}))
    with pytest.raises(ProjectionError, match="exactly"):  # rules serve only shared/{id}/recipients/{uid}
        ProjectionSpec("x", "shared", "shared/{share_id}/views/{view_id}", frozenset({"a"}))
    with pytest.raises(ProjectionError):
        PROFILE.path({"member_id": "../escape"})


def test_purge_member_removes_all_private_views(store):
    member = "m-" + uuid.uuid4().hex[:8]
    other = "m-" + uuid.uuid4().hex[:8]
    store.apply(Upsert(PROFILE, {"member_id": member}, {"display_name": "A"}, 1))
    store.apply(Upsert(PROFILE, {"member_id": other}, {"display_name": "B"}, 1))
    assert store.purge_member(member) == 1
    assert store.get(PROFILE, {"member_id": member}) is None
    assert store.get(PROFILE, {"member_id": other}) is not None
    assert store.purge_member(member) == 0
    # A delayed or retried event after the purge must not recreate the member's data.
    assert store.apply(Upsert(PROFILE, {"member_id": member}, {"display_name": "A"}, 5)) == "revoked"
    assert store.get(PROFILE, {"member_id": member}) is None
    assert store.apply(Upsert(PROFILE, {"member_id": other}, {"display_name": "B2"}, 2)) == "applied"


def test_registry_routes_events_to_reducers(store):
    import brandme_core.domains  # noqa: F401  registers member.updated
    from brandme_core.events import EventEnvelope

    reg = ProjectionRegistry()
    mid = str(uuid.uuid4())
    reg.register("member.updated", lambda ev: [Upsert(PROFILE, {"member_id": ev.aggregate_id}, {"display_name": "via event"}, ev.aggregate_version)])
    ev = EventEnvelope(event_type="member.updated", schema_version="1", aggregate_type="member", aggregate_id=mid,
                       aggregate_version=7, environment="development", actor_ref=f"member:{mid}",
                       correlation_id=str(uuid.uuid4()), privacy_class="member_private",
                       payload={"member_id": mid, "changed_fields": ["display_name"]})
    assert reg.apply(store, ev) == ["applied"]
    assert reg.apply(store, ev) == ["stale"]
    assert store.get(PROFILE, {"member_id": mid})["source_version"] == 7
    ev.event_type = "unrelated.event"
    assert reg.apply(store, ev) == []
