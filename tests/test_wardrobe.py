"""
Tests for Firestore Wardrobe Manager.
"""

import pytest
import uuid


@pytest.mark.asyncio
async def test_initialize_wardrobe(wardrobe_manager, test_user_id, cleanup_firestore):
    """Test initializing a user's wardrobe."""
    user_id = test_user_id

    await wardrobe_manager.initialize_wardrobe(user_id, display_name="Test User")

    cleanup_firestore.add_path(f'wardrobes/{user_id}')

    # Verify wardrobe exists
    wardrobe = await wardrobe_manager._wardrobe_ref(user_id).get()
    assert wardrobe.exists
    data = wardrobe.to_dict()
    assert data['owner_id'] == user_id
    assert data['display_name'] == "Test User"
    assert data['total_cubes'] == 0


@pytest.mark.asyncio
async def test_add_cube_to_wardrobe(wardrobe_manager, test_user_id, cleanup_firestore):
    """Test adding a cube to wardrobe."""
    user_id = test_user_id
    cube_id = str(uuid.uuid4())

    cleanup_firestore.add_path(f'wardrobes/{user_id}')
    cleanup_firestore.add_path(f'wardrobes/{user_id}/cubes/{cube_id}')

    faces = {
        'product_details': {'name': 'Test Product', 'brand': 'TestBrand'},
        'provenance': {'origin': 'Italy'},
        'ownership': {'acquired_date': '2024-01-01'},
        'social_layer': {'likes': 0},
        'esg_impact': {'score': 'A'},
        'lifecycle': {'repairs': 0}
    }

    await wardrobe_manager.add_cube(user_id, cube_id, faces)

    # Verify cube exists
    cube = await wardrobe_manager.get_cube(user_id, cube_id)
    assert cube is not None
    assert cube['cube_id'] == cube_id
    assert cube['owner_id'] == user_id
    assert cube['agentic_state'] == 'idle'
    assert 'product_details' in cube['faces']


@pytest.mark.asyncio
async def test_update_face(wardrobe_manager, test_user_id, cleanup_firestore):
    """Test updating a cube face."""
    user_id = test_user_id
    cube_id = str(uuid.uuid4())

    cleanup_firestore.add_path(f'wardrobes/{user_id}')
    cleanup_firestore.add_path(f'wardrobes/{user_id}/cubes/{cube_id}')

    # Add cube first
    faces = {
        'product_details': {'name': 'Original Name'},
        'social_layer': {'likes': 0}
    }
    await wardrobe_manager.add_cube(user_id, cube_id, faces)

    # Update face
    await wardrobe_manager.update_face(
        user_id, cube_id, 'social_layer',
        {'likes': 10, 'comments': 5}
    )

    # Verify update
    cube = await wardrobe_manager.get_cube(user_id, cube_id)
    assert cube['faces']['social_layer']['data']['likes'] == 10
    assert cube['faces']['social_layer']['data']['comments'] == 5
    assert cube['faces']['social_layer']['pending_sync'] is True


@pytest.mark.asyncio
async def test_transfer_cube(wardrobe_manager, cleanup_firestore):
    """Test transferring a cube between users."""
    user1_id = str(uuid.uuid4())
    user2_id = str(uuid.uuid4())
    cube_id = str(uuid.uuid4())

    cleanup_firestore.add_path(f'wardrobes/{user1_id}')
    cleanup_firestore.add_path(f'wardrobes/{user1_id}/cubes/{cube_id}')
    cleanup_firestore.add_path(f'wardrobes/{user2_id}')
    cleanup_firestore.add_path(f'wardrobes/{user2_id}/cubes/{cube_id}')

    # Add cube to user1
    faces = {'product_details': {'name': 'Transfer Test'}}
    await wardrobe_manager.add_cube(user1_id, cube_id, faces)

    # Verify user1 has cube
    cube1 = await wardrobe_manager.get_cube(user1_id, cube_id)
    assert cube1 is not None

    # Transfer to user2
    await wardrobe_manager.transfer_cube(user1_id, user2_id, cube_id)

    # Verify user1 no longer has cube
    cube1_after = await wardrobe_manager.get_cube(user1_id, cube_id)
    assert cube1_after is None

    # Verify user2 has cube
    cube2 = await wardrobe_manager.get_cube(user2_id, cube_id)
    assert cube2 is not None
    assert cube2['owner_id'] == user2_id


@pytest.mark.asyncio
async def test_get_all_cubes(wardrobe_manager, test_user_id, cleanup_firestore):
    """Test getting all cubes in a wardrobe."""
    user_id = test_user_id

    cleanup_firestore.add_path(f'wardrobes/{user_id}')

    cube_ids = [str(uuid.uuid4()) for _ in range(3)]
    for cube_id in cube_ids:
        cleanup_firestore.add_path(f'wardrobes/{user_id}/cubes/{cube_id}')
        await wardrobe_manager.add_cube(
            user_id, cube_id,
            {'product_details': {'id': cube_id}}
        )

    # Get all cubes
    cubes = await wardrobe_manager.get_all_cubes(user_id)

    assert len(cubes) == 3
    returned_ids = {c['cube_id'] for c in cubes}
    assert returned_ids == set(cube_ids)


@pytest.mark.asyncio
async def test_visibility_update(wardrobe_manager, test_user_id, cleanup_firestore):
    """Test updating face visibility."""
    user_id = test_user_id
    cube_id = str(uuid.uuid4())

    cleanup_firestore.add_path(f'wardrobes/{user_id}')
    cleanup_firestore.add_path(f'wardrobes/{user_id}/cubes/{cube_id}')

    # Add cube
    await wardrobe_manager.add_cube(
        user_id, cube_id,
        {'ownership': {'data': 'sensitive'}}
    )

    # Update visibility
    await wardrobe_manager.update_visibility(
        user_id, cube_id, 'ownership', 'friends_only'
    )

    # Verify
    cube = await wardrobe_manager.get_cube(user_id, cube_id)
    assert cube['visibility_settings']['ownership'] == 'friends_only'
    assert cube['faces']['ownership']['visibility'] == 'friends_only'
