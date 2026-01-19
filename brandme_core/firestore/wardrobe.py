"""
Brand.Me Wardrobe Manager
========================

Manages wardrobe state in Firestore for real-time frontend updates.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

from google.cloud import firestore

from brandme_core.logging import get_logger

logger = get_logger("firestore.wardrobe")


class AgenticState(Enum):
    """State of an item being modified by an agent."""
    IDLE = "idle"
    PROCESSING = "processing"
    MODIFIED = "modified"
    SYNCING = "syncing"
    ERROR = "error"


class FaceVisibility(Enum):
    """Visibility level for a cube face."""
    PUBLIC = "public"
    FRIENDS_ONLY = "friends_only"
    PRIVATE = "private"
    AUTHENTICATED = "authenticated"


@dataclass
class CubeFaceState:
    """State of a single cube face."""
    face_name: str
    visibility: str
    data: Dict[str, Any]
    agentic_state: str = "idle"
    pending_sync: bool = False
    last_modified_by: Optional[str] = None
    updated_at: Optional[datetime] = None


@dataclass
class CubeState:
    """Full state of a product cube."""
    cube_id: str
    owner_id: str
    agentic_state: str = "idle"
    last_agent_id: Optional[str] = None
    last_agent_action: Optional[datetime] = None
    faces: Dict[str, CubeFaceState] = None
    visibility_settings: Dict[str, str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WardrobeManager:
    """
    Manages wardrobe state in Firestore.

    Collection structure:
        /wardrobes/{user_id}/
            metadata: {owner_id, display_name, total_cubes, last_updated}
            /cubes/{cube_id}/
                cube_id, owner_id, agentic_state, faces, ...
    """

    def __init__(self, firestore_client):
        self.db = firestore_client

    def _wardrobe_ref(self, user_id: str):
        """Get reference to user's wardrobe document."""
        return self.db.client.collection('wardrobes').document(user_id)

    def _cubes_collection(self, user_id: str):
        """Get reference to user's cubes collection."""
        return self._wardrobe_ref(user_id).collection('cubes')

    def _cube_ref(self, user_id: str, cube_id: str):
        """Get reference to a specific cube document."""
        return self._cubes_collection(user_id).document(cube_id)

    async def initialize_wardrobe(
        self,
        user_id: str,
        display_name: Optional[str] = None
    ):
        """
        Initialize a user's wardrobe if it doesn't exist.
        """
        wardrobe_ref = self._wardrobe_ref(user_id)
        doc = await wardrobe_ref.get()

        if not doc.exists:
            await wardrobe_ref.set({
                'owner_id': user_id,
                'display_name': display_name,
                'total_cubes': 0,
                'last_updated': firestore.SERVER_TIMESTAMP,
                'created_at': firestore.SERVER_TIMESTAMP
            })

            logger.info({
                "event": "wardrobe_initialized",
                "user_id": user_id[:8] + "..."
            })

    async def add_cube(
        self,
        user_id: str,
        cube_id: str,
        faces: Dict[str, Dict[str, Any]],
        visibility_settings: Optional[Dict[str, str]] = None
    ):
        """
        Add a cube to user's wardrobe.
        """
        # Ensure wardrobe exists
        await self.initialize_wardrobe(user_id)

        # Default visibility settings
        if not visibility_settings:
            visibility_settings = {
                'product_details': 'public',
                'provenance': 'public',
                'ownership': 'private',
                'social_layer': 'public',
                'esg_impact': 'public',
                'lifecycle': 'authenticated'
            }

        # Prepare face states
        face_states = {}
        for face_name, face_data in faces.items():
            face_states[face_name] = {
                'face_name': face_name,
                'visibility': visibility_settings.get(face_name, 'public'),
                'data': face_data,
                'agentic_state': 'idle',
                'pending_sync': False,
                'updated_at': firestore.SERVER_TIMESTAMP
            }

        cube_doc = {
            'cube_id': cube_id,
            'owner_id': user_id,
            'agentic_state': 'idle',
            'last_agent_id': None,
            'last_agent_action': None,
            'faces': face_states,
            'visibility_settings': visibility_settings,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }

        # Add cube
        cube_ref = self._cube_ref(user_id, cube_id)
        await cube_ref.set(cube_doc)

        # Update wardrobe metadata
        wardrobe_ref = self._wardrobe_ref(user_id)
        await wardrobe_ref.update({
            'total_cubes': firestore.Increment(1),
            'last_updated': firestore.SERVER_TIMESTAMP
        })

        logger.info({
            "event": "cube_added_to_wardrobe",
            "user_id": user_id[:8] + "...",
            "cube_id": cube_id[:8] + "..."
        })

    async def get_cube(self, user_id: str, cube_id: str) -> Optional[Dict[str, Any]]:
        """Get a cube from wardrobe."""
        cube_ref = self._cube_ref(user_id, cube_id)
        doc = await cube_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def get_all_cubes(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all cubes in a user's wardrobe."""
        cubes_ref = self._cubes_collection(user_id)
        docs = await cubes_ref.get()

        return [doc.to_dict() for doc in docs]

    async def update_face(
        self,
        user_id: str,
        cube_id: str,
        face_name: str,
        data: Dict[str, Any],
        mark_pending_sync: bool = True
    ):
        """
        Update a specific face's data.
        """
        cube_ref = self._cube_ref(user_id, cube_id)

        update_data = {
            f'faces.{face_name}.data': data,
            f'faces.{face_name}.updated_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }

        if mark_pending_sync:
            update_data[f'faces.{face_name}.pending_sync'] = True

        await cube_ref.update(update_data)

        logger.info({
            "event": "face_updated",
            "user_id": user_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "face": face_name
        })

    async def update_visibility(
        self,
        user_id: str,
        cube_id: str,
        face_name: str,
        visibility: str
    ):
        """Update visibility setting for a face."""
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            f'faces.{face_name}.visibility': visibility,
            f'visibility_settings.{face_name}': visibility,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

    async def transfer_cube(
        self,
        from_user_id: str,
        to_user_id: str,
        cube_id: str
    ):
        """
        Transfer a cube from one user's wardrobe to another.
        """
        # Get cube data
        cube_data = await self.get_cube(from_user_id, cube_id)
        if not cube_data:
            raise ValueError(f"Cube {cube_id} not found in {from_user_id}'s wardrobe")

        # Ensure destination wardrobe exists
        await self.initialize_wardrobe(to_user_id)

        # Update owner in cube data
        cube_data['owner_id'] = to_user_id
        cube_data['updated_at'] = firestore.SERVER_TIMESTAMP

        # Use batch for atomic transfer
        batch = self.db.client.batch()

        # Delete from source
        from_cube_ref = self._cube_ref(from_user_id, cube_id)
        batch.delete(from_cube_ref)

        # Add to destination
        to_cube_ref = self._cube_ref(to_user_id, cube_id)
        batch.set(to_cube_ref, cube_data)

        # Update wardrobe counts
        from_wardrobe = self._wardrobe_ref(from_user_id)
        batch.update(from_wardrobe, {
            'total_cubes': firestore.Increment(-1),
            'last_updated': firestore.SERVER_TIMESTAMP
        })

        to_wardrobe = self._wardrobe_ref(to_user_id)
        batch.update(to_wardrobe, {
            'total_cubes': firestore.Increment(1),
            'last_updated': firestore.SERVER_TIMESTAMP
        })

        await batch.commit()

        logger.info({
            "event": "cube_transferred",
            "from": from_user_id[:8] + "...",
            "to": to_user_id[:8] + "...",
            "cube_id": cube_id[:8] + "..."
        })

    async def remove_cube(self, user_id: str, cube_id: str):
        """Remove a cube from wardrobe."""
        cube_ref = self._cube_ref(user_id, cube_id)
        await cube_ref.delete()

        # Update wardrobe count
        wardrobe_ref = self._wardrobe_ref(user_id)
        await wardrobe_ref.update({
            'total_cubes': firestore.Increment(-1),
            'last_updated': firestore.SERVER_TIMESTAMP
        })

        logger.info({
            "event": "cube_removed",
            "user_id": user_id[:8] + "...",
            "cube_id": cube_id[:8] + "..."
        })

    async def get_pending_sync_cubes(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all cubes with pending sync flags."""
        cubes = await self.get_all_cubes(user_id)

        pending = []
        for cube in cubes:
            faces = cube.get('faces', {})
            for face_name, face_data in faces.items():
                if face_data.get('pending_sync'):
                    pending.append({
                        'cube_id': cube['cube_id'],
                        'face_name': face_name,
                        'data': face_data.get('data')
                    })

        return pending

    async def clear_pending_sync(
        self,
        user_id: str,
        cube_id: str,
        face_name: str
    ):
        """Clear pending sync flag for a face."""
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            f'faces.{face_name}.pending_sync': False
        })
