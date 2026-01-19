"""
Brand.Me Agentic State Manager
=============================

Manages agentic state transitions in Firestore.
Ensures agents can signal state changes that propagate to frontend.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import uuid

from google.cloud import firestore

from brandme_core.logging import get_logger

logger = get_logger("firestore.agentic")


class AgenticState(Enum):
    """Agentic states for cube processing."""
    IDLE = "idle"
    PROCESSING = "processing"
    MODIFIED = "modified"
    SYNCING = "syncing"
    ERROR = "error"


@dataclass
class AgentSession:
    """Represents an active agent session."""
    session_id: str
    agent_id: str
    user_id: str
    cube_id: str
    face_name: Optional[str]
    action: str
    started_at: datetime
    status: str  # 'active' | 'completed' | 'failed'


class AgenticStateManager:
    """
    Manages agentic state transitions in Firestore.

    When an agent modifies a cube:
    1. Agent starts modification -> cube.agentic_state = 'processing'
    2. Agent completes -> cube.agentic_state = 'modified'
    3. Sync to Spanner -> cube.agentic_state = 'syncing'
    4. Sync complete -> cube.agentic_state = 'idle'

    This allows the frontend to show real-time progress.
    """

    def __init__(self, firestore_client):
        self.db = firestore_client

    def _cube_ref(self, user_id: str, cube_id: str):
        """Get reference to a cube document."""
        return self.db.client.collection('wardrobes').document(user_id).collection('cubes').document(cube_id)

    def _sessions_collection(self):
        """Get reference to agent sessions collection."""
        return self.db.client.collection('agent_sessions')

    async def start_agent_session(
        self,
        agent_id: str,
        user_id: str,
        cube_id: str,
        action: str,
        face_name: Optional[str] = None
    ) -> str:
        """
        Start a new agent session.

        Updates cube's agentic_state to 'processing'.
        Returns session_id.
        """
        session_id = str(uuid.uuid4())

        # Create session document
        session_data = {
            'session_id': session_id,
            'agent_id': agent_id,
            'user_id': user_id,
            'cube_id': cube_id,
            'face_name': face_name,
            'action': action,
            'started_at': firestore.SERVER_TIMESTAMP,
            'completed_at': None,
            'status': 'active',
            'changes': []
        }

        session_ref = self._sessions_collection().document(session_id)
        await session_ref.set(session_data)

        # Update cube state
        cube_ref = self._cube_ref(user_id, cube_id)
        update_data = {
            'agentic_state': AgenticState.PROCESSING.value,
            'last_agent_id': agent_id,
            'last_agent_action': firestore.SERVER_TIMESTAMP
        }

        if face_name:
            update_data[f'faces.{face_name}.agentic_state'] = 'processing'

        await cube_ref.update(update_data)

        logger.info({
            "event": "agent_session_started",
            "session_id": session_id,
            "agent_id": agent_id,
            "cube_id": cube_id[:8] + "...",
            "action": action
        })

        return session_id

    async def record_change(
        self,
        session_id: str,
        face_name: str,
        field: str,
        old_value: Any,
        new_value: Any
    ):
        """Record a change made by the agent."""
        session_ref = self._sessions_collection().document(session_id)

        await session_ref.update({
            'changes': firestore.ArrayUnion([{
                'face_name': face_name,
                'field': field,
                'old_value': str(old_value) if old_value is not None else None,
                'new_value': str(new_value) if new_value is not None else None,
                'timestamp': datetime.utcnow().isoformat()
            }])
        })

    async def complete_modification(
        self,
        session_id: str,
        user_id: str,
        cube_id: str,
        face_name: str,
        new_data: Dict[str, Any]
    ):
        """
        Complete an agent modification.

        Updates face data and sets agentic_state to 'modified'.
        """
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            'agentic_state': AgenticState.MODIFIED.value,
            f'faces.{face_name}.data': new_data,
            f'faces.{face_name}.agentic_state': 'modified',
            f'faces.{face_name}.pending_sync': True,
            f'faces.{face_name}.updated_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

        # Update session
        session_ref = self._sessions_collection().document(session_id)
        await session_ref.update({
            'status': 'completed',
            'completed_at': firestore.SERVER_TIMESTAMP
        })

        logger.info({
            "event": "agent_modification_complete",
            "session_id": session_id,
            "cube_id": cube_id[:8] + "...",
            "face": face_name
        })

    async def fail_modification(
        self,
        session_id: str,
        user_id: str,
        cube_id: str,
        error: str,
        face_name: Optional[str] = None
    ):
        """
        Mark an agent modification as failed.
        """
        cube_ref = self._cube_ref(user_id, cube_id)

        update_data = {
            'agentic_state': AgenticState.ERROR.value
        }

        if face_name:
            update_data[f'faces.{face_name}.agentic_state'] = 'error'

        await cube_ref.update(update_data)

        # Update session
        session_ref = self._sessions_collection().document(session_id)
        await session_ref.update({
            'status': 'failed',
            'completed_at': firestore.SERVER_TIMESTAMP,
            'error': error
        })

        logger.error({
            "event": "agent_modification_failed",
            "session_id": session_id,
            "cube_id": cube_id[:8] + "...",
            "error": error
        })

    async def start_sync(self, user_id: str, cube_id: str, face_name: str):
        """Mark cube as syncing to Spanner."""
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            'agentic_state': AgenticState.SYNCING.value,
            f'faces.{face_name}.agentic_state': 'syncing'
        })

    async def complete_sync(self, user_id: str, cube_id: str, face_name: str):
        """Mark sync as complete, return to idle state."""
        cube_ref = self._cube_ref(user_id, cube_id)

        await cube_ref.update({
            'agentic_state': AgenticState.IDLE.value,
            f'faces.{face_name}.agentic_state': 'idle',
            f'faces.{face_name}.pending_sync': False
        })

        logger.info({
            "event": "sync_complete",
            "cube_id": cube_id[:8] + "...",
            "face": face_name
        })

    async def get_active_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all active agent sessions, optionally filtered by user."""
        query = self._sessions_collection().where('status', '==', 'active')

        if user_id:
            query = query.where('user_id', '==', user_id)

        docs = await query.get()
        return [doc.to_dict() for doc in docs]

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific session."""
        session_ref = self._sessions_collection().document(session_id)
        doc = await session_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def cleanup_stale_sessions(self, max_age_minutes: int = 60) -> int:
        """
        Clean up stale sessions (active for too long).

        Returns number of sessions cleaned up.
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

        query = self._sessions_collection()\
            .where('status', '==', 'active')\
            .where('started_at', '<', cutoff)

        docs = await query.get()
        count = 0

        for doc in docs:
            session_data = doc.to_dict()

            # Mark as failed
            await doc.reference.update({
                'status': 'failed',
                'completed_at': firestore.SERVER_TIMESTAMP,
                'error': 'session_timeout'
            })

            # Reset cube state
            try:
                cube_ref = self._cube_ref(
                    session_data['user_id'],
                    session_data['cube_id']
                )
                await cube_ref.update({
                    'agentic_state': AgenticState.IDLE.value
                })
            except Exception:
                pass  # Cube may have been deleted

            count += 1

        if count > 0:
            logger.info({
                "event": "stale_sessions_cleaned",
                "count": count
            })

        return count
