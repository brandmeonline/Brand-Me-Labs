"""
Tests for Provenance tracking functionality.
"""

import pytest
import uuid

from brandme_core.spanner.provenance import TransferType


@pytest.mark.asyncio
async def test_get_current_owner(provenance_client, seed_test_user, seed_test_asset):
    """Test getting current owner of an asset."""
    user_id = seed_test_user
    asset_id = seed_test_asset

    ownership = await provenance_client.get_current_owner(asset_id)

    assert ownership is not None
    assert ownership.owner_id == user_id
    assert ownership.asset_id == asset_id


@pytest.mark.asyncio
async def test_get_full_provenance(provenance_client, seed_test_user, seed_test_asset):
    """Test getting full provenance chain."""
    user_id = seed_test_user
    asset_id = seed_test_asset

    provenance = await provenance_client.get_full_provenance(asset_id)

    assert provenance is not None
    assert provenance.asset_id == asset_id
    assert provenance.creator_id == user_id
    assert provenance.current_owner_id == user_id
    assert provenance.transfer_count >= 1

    # First entry should be mint
    assert len(provenance.chain) >= 1
    assert provenance.chain[0].transfer_type == 'mint'
    assert provenance.chain[0].to_user_id == user_id


@pytest.mark.asyncio
async def test_verify_provenance_chain(provenance_client, seed_test_asset):
    """Test provenance chain verification."""
    asset_id = seed_test_asset

    result = await provenance_client.verify_provenance_chain(asset_id)

    assert result['valid'] is True
    assert result['asset_id'] == asset_id
    assert len(result['issues']) == 0


@pytest.mark.asyncio
async def test_record_transfer(provenance_client, seed_test_user, seed_test_asset, spanner_pool, cleanup_spanner):
    """Test recording an ownership transfer."""
    from google.cloud import spanner

    owner_id = seed_test_user
    asset_id = seed_test_asset

    # Create new owner
    new_owner_id = str(uuid.uuid4())

    def _create_new_owner(transaction):
        transaction.insert(
            table='Users',
            columns=['user_id', 'handle', 'display_name', 'region_code', 'trust_score', 'is_active', 'created_at'],
            values=[(new_owner_id, f'new_{new_owner_id[:8]}', 'New Owner', 'us-east1', 0.5, True, spanner.COMMIT_TIMESTAMP)]
        )

    spanner_pool.run_in_transaction(_create_new_owner)
    cleanup_spanner.add_user(new_owner_id)

    # Record transfer
    entry = await provenance_client.record_transfer(
        asset_id=asset_id,
        from_user_id=owner_id,
        to_user_id=new_owner_id,
        transfer_type=TransferType.PURCHASE,
        price=100.0,
        currency="USD"
    )

    assert entry is not None
    assert entry.from_user_id == owner_id
    assert entry.to_user_id == new_owner_id
    assert entry.transfer_type == 'purchase'
    assert entry.price == 100.0

    # Verify new owner
    ownership = await provenance_client.get_current_owner(asset_id)
    assert ownership.owner_id == new_owner_id

    # Verify chain
    result = await provenance_client.verify_provenance_chain(asset_id)
    assert result['valid'] is True
    assert result['transfer_count'] >= 2


@pytest.mark.asyncio
async def test_mint_asset(provenance_client, seed_test_user, cleanup_spanner):
    """Test minting a new asset."""
    import hashlib

    creator_id = seed_test_user
    asset_id = str(uuid.uuid4())
    auth_hash = hashlib.sha256(asset_id.encode()).hexdigest()

    result = await provenance_client.mint_asset(
        asset_id=asset_id,
        creator_id=creator_id,
        asset_type='cube',
        display_name='Minted Test Cube',
        authenticity_hash=auth_hash
    )

    cleanup_spanner.add_asset(asset_id)

    assert result['asset_id'] == asset_id
    assert result['creator_id'] == creator_id

    # Verify ownership
    ownership = await provenance_client.get_current_owner(asset_id)
    assert ownership.owner_id == creator_id

    # Verify provenance
    provenance = await provenance_client.get_full_provenance(asset_id)
    assert provenance.creator_id == creator_id
    assert provenance.transfer_count == 1
    assert provenance.chain[0].transfer_type == 'mint'


@pytest.mark.asyncio
async def test_get_creator(provenance_client, seed_test_user, seed_test_asset):
    """Test getting creator of an asset."""
    user_id = seed_test_user
    asset_id = seed_test_asset

    creator = await provenance_client.get_creator(asset_id)

    assert creator is not None
    assert creator['creator_id'] == user_id
