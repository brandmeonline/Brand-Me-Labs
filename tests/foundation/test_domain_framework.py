"""Pure framework tests: policy, envelopes, If-Match, digests (no emulator)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains import (
    Grant, NotFound, PreconditionRequired, Principal, VersionConflict, authorize, canonical_digest,
    expect_version, parse_if_match,
)
from brandme_core.events import EventEnvelope, EventValidationError, registry


def P(mid=None, scopes=()):
    return Principal(mid or str(uuid.uuid4()), "s", None, None, frozenset(scopes), "aal1", "development")


def test_owner_allowed_everyone_else_denied_by_default():
    owner = P()
    authorize(owner, "wardrobe:read", owner.member_id)
    with pytest.raises(NotFound):
        authorize(P(), "wardrobe:read", owner.member_id)
    with pytest.raises(NotFound):
        authorize(None, "wardrobe:read", owner.member_id)


def test_grants_respect_action_expiry_revocation_and_block():
    owner, friend = P(), P()
    now = datetime.now(timezone.utc)
    ok = Grant("share", frozenset({"outfit:read"}), grantee_member_id=friend.member_id, expires_at=now + timedelta(hours=1))
    authorize(friend, "outfit:read", owner.member_id, [ok])
    for g in (Grant("share", frozenset({"outfit:read"}), friend.member_id, expires_at=now - timedelta(seconds=1)),
              Grant("share", frozenset({"outfit:read"}), friend.member_id, revoked=True),
              Grant("share", frozenset({"outfit:write"}), friend.member_id)):
        with pytest.raises(NotFound):
            authorize(friend, "outfit:read", owner.member_id, [g])
    with pytest.raises(NotFound):
        authorize(friend, "outfit:read", owner.member_id, [ok], blocked=True)


def test_if_match_and_versions():
    assert parse_if_match('"42"') == 42 and parse_if_match('W/"7"') == 7
    for bad in (None, "", '"abc"'):
        with pytest.raises(PreconditionRequired):
            parse_if_match(bad)
    assert expect_version(42, 42) == 43
    with pytest.raises(VersionConflict):
        expect_version(43, 42)


def test_canonical_digest_is_order_independent():
    assert canonical_digest({"a": 1, "b": [1, 2]}) == canonical_digest({"b": [1, 2], "a": 1})
    assert canonical_digest({"a": 1}) != canonical_digest({"a": 2})


def _ev(**over):
    mid = str(uuid.uuid4())
    base = dict(event_type="member.updated", schema_version="1", aggregate_type="member", aggregate_id=mid,
                aggregate_version=2, environment="development", actor_ref=f"member:{mid}",
                correlation_id=str(uuid.uuid4()), privacy_class="member_private",
                payload={"member_id": mid, "changed_fields": ["display_name"]})
    base.update(over)
    return EventEnvelope(**base)


def test_registered_event_validates():
    import brandme_core.domains  # noqa: F401  registers identity events
    _ev().validate()


@pytest.mark.parametrize("over,msg", [
    ({"event_type": "member.unknown"}, "unregistered"),
    ({"privacy_class": "public"}, "privacy_class"),
    ({"payload": {"member_id": str(uuid.uuid4()), "changed_fields": [], "email": "a@b.c"}}, "forbidden|payload invalid"),
    ({"payload": {"member_id": "not-a-uuid", "changed_fields": []}}, "payload invalid"),
    ({"environment": "staging"}, "envelope invalid"),
])
def test_invalid_events_are_rejected(over, msg):
    import brandme_core.domains  # noqa: F401
    with pytest.raises(EventValidationError, match=msg):
        _ev(**over).validate()


def test_registry_requires_closed_payload_schemas():
    with pytest.raises(ValueError):
        registry.register("x.open", "1", {"type": "object"}, "public")
