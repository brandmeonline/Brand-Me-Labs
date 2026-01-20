"""
Brand.Me Wardrobe Manager v9
============================

Manages wardrobe state in Firestore for real-time frontend updates.
v9: Added Biometric Sync for AR glasses (<100ms Active Facet display)
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
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
    AGENT_ONLY = "agent_only"


class LifecycleState(Enum):
    """DPP Lifecycle states for circular economy."""
    PRODUCED = "PRODUCED"
    ACTIVE = "ACTIVE"
    REPAIR = "REPAIR"
    DISSOLVE = "DISSOLVE"
    REPRINT = "REPRINT"


class ARPriority(Enum):
    """Rendering priority for AR glasses."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BACKGROUND = "background"


@dataclass
class BiometricSync:
    """
    Biometric Sync state for AR glasses (<100ms response).
    Enables real-time Active Facet display on AR devices.
    """
    active_facet: str = "esg_impact"              # Currently displayed face
    ar_priority: str = "high"                      # Rendering priority
    last_gaze_timestamp: Optional[datetime] = None # Eye tracking sync
    ar_device_session: Optional[str] = None        # Device session ID
    render_hints: Dict[str, Any] = field(default_factory=lambda: {
        "highlight_esg": True,
        "show_provenance_trail": False,
        "show_material_composition": True,
        "enable_haptic_feedback": False
    })
    gaze_duration_ms: int = 0                      # How long user has gazed
    last_interaction_type: Optional[str] = None    # "gaze", "gesture", "voice"


@dataclass
class MolecularData:
    """
    Molecular data for circularity tracking.
    Stored in the molecular_data face.
    """
    material_type: str
    tensile_strength_mpa: Optional[float] = None
    dissolve_auth_key_hash: Optional[str] = None   # Hash only, key in Midnight
    material_composition: List[Dict[str, Any]] = field(default_factory=list)
    esg_score: Optional[float] = None
    carbon_footprint_kg: Optional[float] = None
    water_usage_liters: Optional[float] = None
    recyclability_pct: Optional[float] = None
    certifications: List[str] = field(default_factory=list)


@dataclass
class LifecycleData:
    """
    Lifecycle tracking for DPP state machine.
    """
    current_state: str = "ACTIVE"
    state_history: List[Dict[str, Any]] = field(default_factory=list)
    repair_count: int = 0
    reprint_generation: int = 0
    reprint_eligible: bool = True
    parent_asset_id: Optional[str] = None
    dissolve_authorized: bool = False
    last_state_change: Optional[datetime] = None


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
    """Full state of a product cube with v9 enhancements."""
    cube_id: str
    owner_id: str
    agentic_state: str = "idle"
    last_agent_id: Optional[str] = None
    last_agent_action: Optional[datetime] = None
    faces: Dict[str, CubeFaceState] = None
    visibility_settings: Dict[str, str] = None
    # v9: Biometric Sync for AR
    biometric_sync: Optional[BiometricSync] = None
    # v9: Lifecycle state
    lifecycle_state: str = "ACTIVE"
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WardrobeManager:
    """
    Manages wardrobe state in Firestore.
    v9: Enhanced for AR glasses biometric sync and circular economy.

    Collection structure:
        /wardrobes/{user_id}/
            metadata: {
                owner_id, display_name, total_cubes, last_updated,
                ar_sync_enabled, last_biometric_ping, active_ar_device_id
            }
            /cubes/{cube_id}/
                cube_id, owner_id, agentic_state, faces,
                biometric_sync: { active_facet, ar_priority, render_hints, ... }
                lifecycle_state, molecular_data, ...
    """

    # v9: Face names now include molecular_data
    FACE_NAMES = [
        'product_details',
        'provenance',
        'ownership',
        'social_layer',
        'esg_impact',
        'lifecycle',
        'molecular_data'  # v9: New face for circularity
    ]

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
        display_name: Optional[str] = None,
        ar_sync_enabled: bool = True
    ):
        """
        Initialize a user's wardrobe if it doesn't exist.
        v9: Added AR sync configuration.
        """
        wardrobe_ref = self._wardrobe_ref(user_id)
        doc = await wardrobe_ref.get()

        if not doc.exists:
            await wardrobe_ref.set({
                'owner_id': user_id,
                'display_name': display_name,
                'total_cubes': 0,
                # v9: AR Biometric Sync settings
                'ar_sync_enabled': ar_sync_enabled,
                'last_biometric_ping': None,
                'active_ar_device_id': None,
                'ar_preferences': {
                    'default_active_facet': 'esg_impact',
                    'haptic_feedback': True,
                    'gaze_threshold_ms': 500
                },
                # Timestamps
                'last_updated': firestore.SERVER_TIMESTAMP,
                'created_at': firestore.SERVER_TIMESTAMP
            })

            logger.info({
                "event": "wardrobe_initialized",
                "user_id": user_id[:8] + "...",
                "ar_sync_enabled": ar_sync_enabled
            })

    async def add_cube(
        self,
        user_id: str,
        cube_id: str,
        faces: Dict[str, Dict[str, Any]],
        visibility_settings: Optional[Dict[str, str]] = None,
        molecular_data: Optional[Dict[str, Any]] = None,
        lifecycle_state: str = "ACTIVE"
    ):
        """
        Add a cube to user's wardrobe.
        v9: Added molecular_data face and lifecycle state.
        """
        # Ensure wardrobe exists
        await self.initialize_wardrobe(user_id)

        # Default visibility settings (v9: includes molecular_data)
        if not visibility_settings:
            visibility_settings = {
                'product_details': 'public',
                'provenance': 'public',
                'ownership': 'private',
                'social_layer': 'public',
                'esg_impact': 'public',
                'lifecycle': 'authenticated',
                'molecular_data': 'authenticated'  # v9: Default to authenticated
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

        # v9: Add molecular_data face if provided
        if molecular_data:
            face_states['molecular_data'] = {
                'face_name': 'molecular_data',
                'visibility': visibility_settings.get('molecular_data', 'authenticated'),
                'data': molecular_data,
                'agentic_state': 'idle',
                'pending_sync': False,
                'updated_at': firestore.SERVER_TIMESTAMP
            }

        # v9: Add lifecycle face
        face_states['lifecycle'] = {
            'face_name': 'lifecycle',
            'visibility': visibility_settings.get('lifecycle', 'authenticated'),
            'data': {
                'current_state': lifecycle_state,
                'state_history': [
                    {
                        'state': lifecycle_state,
                        'at': firestore.SERVER_TIMESTAMP,
                        'by': 'system'
                    }
                ],
                'repair_count': 0,
                'reprint_generation': 0,
                'reprint_eligible': True
            },
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
            # v9: Biometric Sync for AR glasses
            'biometric_sync': {
                'active_facet': 'esg_impact',
                'ar_priority': 'high',
                'last_gaze_timestamp': None,
                'ar_device_session': None,
                'render_hints': {
                    'highlight_esg': True,
                    'show_provenance_trail': False,
                    'show_material_composition': True,
                    'enable_haptic_feedback': False
                },
                'gaze_duration_ms': 0,
                'last_interaction_type': None
            },
            # v9: Lifecycle state
            'lifecycle_state': lifecycle_state,
            # Timestamps
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
            "cube_id": cube_id[:8] + "...",
            "lifecycle_state": lifecycle_state
        })

    async def update_biometric_sync(
        self,
        user_id: str,
        cube_id: str,
        active_facet: str,
        ar_device_session: str,
        gaze_duration_ms: int = 0,
        interaction_type: str = "gaze"
    ):
        """
        Update biometric sync state for AR glasses.
        v9: Enables <100ms Active Facet display.
        """
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            'biometric_sync.active_facet': active_facet,
            'biometric_sync.ar_device_session': ar_device_session,
            'biometric_sync.last_gaze_timestamp': firestore.SERVER_TIMESTAMP,
            'biometric_sync.gaze_duration_ms': gaze_duration_ms,
            'biometric_sync.last_interaction_type': interaction_type,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

        logger.debug({
            "event": "biometric_sync_updated",
            "user_id": user_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "active_facet": active_facet,
            "device": ar_device_session[:8] + "..." if ar_device_session else None
        })

    async def set_ar_priority(
        self,
        user_id: str,
        cube_id: str,
        priority: str,
        render_hints: Optional[Dict[str, Any]] = None
    ):
        """
        Set AR rendering priority and hints for a cube.
        v9: Controls how cube is rendered on AR glasses.
        """
        update_data = {
            'biometric_sync.ar_priority': priority,
            'updated_at': firestore.SERVER_TIMESTAMP
        }

        if render_hints:
            for key, value in render_hints.items():
                update_data[f'biometric_sync.render_hints.{key}'] = value

        cube_ref = self._cube_ref(user_id, cube_id)
        await cube_ref.update(update_data)

    async def update_lifecycle_state(
        self,
        user_id: str,
        cube_id: str,
        new_state: str,
        triggered_by: str,
        notes: Optional[str] = None
    ):
        """
        Update lifecycle state (DPP state machine transition).
        v9: Implements PRODUCED -> ACTIVE -> REPAIR -> DISSOLVE -> REPRINT flow.
        """
        cube_ref = self._cube_ref(user_id, cube_id)
        cube_doc = await cube_ref.get()

        if not cube_doc.exists:
            raise ValueError(f"Cube {cube_id} not found")

        cube_data = cube_doc.to_dict()
        current_state = cube_data.get('lifecycle_state', 'ACTIVE')

        # Validate state transition
        valid_transitions = {
            'PRODUCED': ['ACTIVE'],
            'ACTIVE': ['REPAIR', 'DISSOLVE'],
            'REPAIR': ['ACTIVE', 'DISSOLVE'],
            'DISSOLVE': ['REPRINT'],
            'REPRINT': ['PRODUCED']  # Reprint creates new item in PRODUCED state
        }

        if new_state not in valid_transitions.get(current_state, []):
            raise ValueError(
                f"Invalid transition: {current_state} -> {new_state}. "
                f"Valid: {valid_transitions.get(current_state, [])}"
            )

        # Build state history entry
        state_entry = {
            'state': new_state,
            'from_state': current_state,
            'at': firestore.SERVER_TIMESTAMP,
            'by': triggered_by,
            'notes': notes
        }

        # Update repair count if transitioning to REPAIR
        repair_increment = 1 if new_state == 'REPAIR' else 0

        # Update reprint generation if completing reprint
        reprint_increment = 1 if current_state == 'REPRINT' and new_state == 'PRODUCED' else 0

        await cube_ref.update({
            'lifecycle_state': new_state,
            'faces.lifecycle.data.current_state': new_state,
            'faces.lifecycle.data.state_history': firestore.ArrayUnion([state_entry]),
            'faces.lifecycle.data.repair_count': firestore.Increment(repair_increment),
            'faces.lifecycle.data.reprint_generation': firestore.Increment(reprint_increment),
            'faces.lifecycle.data.last_state_change': firestore.SERVER_TIMESTAMP,
            'faces.lifecycle.pending_sync': True,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

        logger.info({
            "event": "lifecycle_state_updated",
            "user_id": user_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "from_state": current_state,
            "to_state": new_state,
            "triggered_by": triggered_by
        })

    async def update_molecular_data(
        self,
        user_id: str,
        cube_id: str,
        molecular_data: Dict[str, Any]
    ):
        """
        Update molecular data face for circularity tracking.
        v9: Stores material composition, tensile strength, dissolve auth.
        """
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            'faces.molecular_data.data': molecular_data,
            'faces.molecular_data.updated_at': firestore.SERVER_TIMESTAMP,
            'faces.molecular_data.pending_sync': True,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

        logger.info({
            "event": "molecular_data_updated",
            "user_id": user_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "material_type": molecular_data.get('material_type')
        })

    async def authorize_dissolve(
        self,
        user_id: str,
        cube_id: str,
        dissolve_auth_key_hash: str
    ):
        """
        Authorize dissolution for circular economy.
        v9: Marks cube as ready for DISSOLVE state transition.
        """
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            'faces.lifecycle.data.dissolve_authorized': True,
            'faces.molecular_data.data.dissolve_auth_key_hash': dissolve_auth_key_hash,
            'faces.lifecycle.pending_sync': True,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

        logger.info({
            "event": "dissolve_authorized",
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

    async def get_cubes_by_lifecycle_state(
        self,
        user_id: str,
        lifecycle_state: str
    ) -> List[Dict[str, Any]]:
        """
        Get cubes by lifecycle state.
        v9: Filter cubes in specific DPP state.
        """
        cubes_ref = self._cubes_collection(user_id)
        query = cubes_ref.where('lifecycle_state', '==', lifecycle_state)
        docs = await query.get()

        return [doc.to_dict() for doc in docs]

    async def get_reprint_eligible_cubes(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get cubes eligible for reprint.
        v9: Returns cubes that can be dissolved and reprinted.
        """
        cubes_ref = self._cubes_collection(user_id)
        query = cubes_ref.where('faces.lifecycle.data.reprint_eligible', '==', True)
        docs = await query.get()

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

        # Reset biometric sync for new owner
        cube_data['biometric_sync'] = {
            'active_facet': 'esg_impact',
            'ar_priority': 'high',
            'last_gaze_timestamp': None,
            'ar_device_session': None,
            'render_hints': {
                'highlight_esg': True,
                'show_provenance_trail': False,
                'show_material_composition': True,
                'enable_haptic_feedback': False
            },
            'gaze_duration_ms': 0,
            'last_interaction_type': None
        }

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

    async def ping_ar_device(
        self,
        user_id: str,
        ar_device_id: str
    ):
        """
        Update last biometric ping from AR device.
        v9: Tracks AR device connection state.
        """
        wardrobe_ref = self._wardrobe_ref(user_id)

        await wardrobe_ref.update({
            'last_biometric_ping': firestore.SERVER_TIMESTAMP,
            'active_ar_device_id': ar_device_id
        })

        logger.debug({
            "event": "ar_device_ping",
            "user_id": user_id[:8] + "...",
            "device": ar_device_id[:8] + "..."
        })
