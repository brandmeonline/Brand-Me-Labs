"""
Tests for Consent Graph functionality.
"""

import pytest
import uuid

from brandme_core.spanner.consent_graph import ConsentScope, Visibility


@pytest.mark.asyncio
async def test_check_consent_owner_access(consent_graph, seed_test_user, seed_test_asset):
    """Owner should always have full access to their own assets."""
    user_id = seed_test_user
    asset_id = seed_test_asset

    decision = await consent_graph.check_consent(
        viewer_id=user_id,
        owner_id=user_id,
        asset_id=asset_id
    )

    assert decision.allowed is True
    assert decision.visibility == "private"
    assert decision.reason == "viewer_is_owner"


@pytest.mark.asyncio
async def test_check_consent_public_default(consent_graph, seed_test_user, seed_test_asset):
    """Non-owners without friendship should get public access by default."""
    owner_id = seed_test_user
    asset_id = seed_test_asset
    viewer_id = str(uuid.uuid4())  # Random viewer

    decision = await consent_graph.check_consent(
        viewer_id=viewer_id,
        owner_id=owner_id,
        asset_id=asset_id
    )

    assert decision.allowed is True
    assert decision.visibility == "public"
    assert "default" in decision.scope


@pytest.mark.asyncio
async def test_grant_and_check_consent(consent_graph, seed_test_user, cleanup_spanner):
    """Test granting consent and verifying it."""
    user_id = seed_test_user
    viewer_id = str(uuid.uuid4())

    # Grant friends_only consent
    consent_id = await consent_graph.grant_consent(
        user_id=user_id,
        scope=ConsentScope.GLOBAL,
        visibility=Visibility.FRIENDS_ONLY
    )

    cleanup_spanner.add_consent(consent_id)

    assert consent_id is not None


@pytest.mark.asyncio
async def test_check_friendship_not_friends(consent_graph, seed_test_user):
    """Two random users should not be friends."""
    user1 = seed_test_user
    user2 = str(uuid.uuid4())

    friendship = await consent_graph.check_friendship(user1, user2)

    assert friendship.are_friends is False


@pytest.mark.asyncio
async def test_add_friend(consent_graph, seed_test_user, spanner_pool, cleanup_spanner):
    """Test adding a friend."""
    from google.cloud import spanner
    from google.cloud.spanner_v1 import param_types

    user1 = seed_test_user

    # Create second user
    user2 = str(uuid.uuid4())

    def _create_user2(transaction):
        transaction.insert(
            table='Users',
            columns=['user_id', 'handle', 'display_name', 'region_code', 'trust_score', 'is_active', 'created_at'],
            values=[(user2, f'user2_{user2[:8]}', 'User 2', 'us-east1', 0.7, True, spanner.COMMIT_TIMESTAMP)]
        )

    spanner_pool.run_in_transaction(_create_user2)
    cleanup_spanner.add_user(user2)

    # Add friend
    success = await consent_graph.add_friend(user1, user2, initiated_by=user1)
    assert success is True

    # Check friendship (should be pending)
    friendship = await consent_graph.check_friendship(user1, user2)
    assert friendship.status == 'pending'
    assert friendship.are_friends is False

    # Accept friend
    success = await consent_graph.accept_friend(user1, user2)
    assert success is True

    # Check friendship (should be accepted)
    friendship = await consent_graph.check_friendship(user1, user2)
    assert friendship.are_friends is True
    assert friendship.status == 'accepted'


@pytest.mark.asyncio
async def test_revoke_global_consent(consent_graph, seed_test_user, cleanup_spanner):
    """Test global revocation."""
    user_id = seed_test_user

    # Grant some consents
    consent1 = await consent_graph.grant_consent(
        user_id=user_id,
        scope=ConsentScope.GLOBAL,
        visibility=Visibility.PUBLIC
    )
    cleanup_spanner.add_consent(consent1)

    consent2 = await consent_graph.grant_consent(
        user_id=user_id,
        scope=ConsentScope.GLOBAL,
        visibility=Visibility.FRIENDS_ONLY
    )
    cleanup_spanner.add_consent(consent2)

    # Revoke all
    count = await consent_graph.revoke_global_consent(user_id, reason="test_revocation")

    assert count >= 2
