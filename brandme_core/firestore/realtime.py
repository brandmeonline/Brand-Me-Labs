"""
Brand.Me Wardrobe Real-time Listener
===================================

Firestore real-time listener for wardrobe state changes.
Pushes updates to connected frontend clients.
"""

from typing import Callable, Optional, Dict, Any, Set
import asyncio
from datetime import datetime
from dataclasses import dataclass

from google.cloud.firestore_v1.watch import DocumentChange

from brandme_core.logging import get_logger

logger = get_logger("firestore.realtime")


@dataclass
class CubeChangeEvent:
    """Event fired when a cube changes."""
    cube_id: str
    user_id: str
    change_type: str  # 'added' | 'modified' | 'removed'
    agentic_state: Optional[str]
    last_agent_id: Optional[str]
    modified_faces: list
    timestamp: datetime


class WardrobeRealtimeListener:
    """
    Firestore real-time listener for wardrobe state changes.

    Subscribes to a user's wardrobe and fires callbacks when:
    - A cube is added/modified/removed
    - An agent modifies a face
    - Agentic state changes

    Usage:
        listener = WardrobeRealtimeListener(firestore_client)

        async def on_change(event: CubeChangeEvent):
            print(f"Cube {event.cube_id} changed: {event.change_type}")

        sub_id = await listener.subscribe_user_wardrobe(
            user_id="user123",
            on_change=on_change
        )

        # Later...
        await listener.unsubscribe(sub_id)
    """

    def __init__(self, firestore_client):
        self.db = firestore_client
        self._active_listeners: Dict[str, Any] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()

    async def subscribe_user_wardrobe(
        self,
        user_id: str,
        on_change: Callable[[CubeChangeEvent], None],
        filter_agentic_only: bool = False
    ) -> str:
        """
        Subscribe to real-time updates for a user's wardrobe.

        Args:
            user_id: User whose wardrobe to watch
            on_change: Async callback for change events
            filter_agentic_only: Only fire events for agentic state changes

        Returns:
            subscription_id for cleanup
        """
        cubes_ref = self.db.client.collection('wardrobes').document(user_id).collection('cubes')

        # Track previous states for change detection
        previous_states: Dict[str, Dict] = {}

        def on_snapshot(col_snapshot, changes, read_time):
            """Handle snapshot changes."""
            for change in changes:
                doc_id = change.document.id
                doc_data = change.document.to_dict() if change.document.exists else {}

                # Determine what changed
                modified_faces = []
                if change.type.name == 'MODIFIED' and doc_id in previous_states:
                    prev = previous_states.get(doc_id, {})
                    prev_faces = prev.get('faces', {})
                    curr_faces = doc_data.get('faces', {})

                    for face_name in set(prev_faces.keys()) | set(curr_faces.keys()):
                        prev_face = prev_faces.get(face_name, {})
                        curr_face = curr_faces.get(face_name, {})

                        if prev_face != curr_face:
                            modified_faces.append(face_name)

                # Update previous state
                previous_states[doc_id] = doc_data.copy() if doc_data else {}

                # Check agentic filter
                agentic_state = doc_data.get('agentic_state')
                if filter_agentic_only:
                    if agentic_state not in ('processing', 'modified'):
                        continue

                # Build event
                event = CubeChangeEvent(
                    cube_id=doc_id,
                    user_id=user_id,
                    change_type=change.type.name.lower(),
                    agentic_state=agentic_state,
                    last_agent_id=doc_data.get('last_agent_id'),
                    modified_faces=modified_faces,
                    timestamp=datetime.utcnow()
                )

                # Fire callback
                asyncio.create_task(self._fire_callback(subscription_id, event))

        # Generate subscription ID
        subscription_id = f"{user_id}:{id(on_snapshot)}"

        async with self._lock:
            # Store callback
            self._callbacks[subscription_id] = on_change

            # Start listening
            listener = cubes_ref.on_snapshot(on_snapshot)
            self._active_listeners[subscription_id] = listener

        logger.info({
            "event": "wardrobe_subscribed",
            "user_id": user_id[:8] + "...",
            "subscription_id": subscription_id,
            "filter_agentic_only": filter_agentic_only
        })

        return subscription_id

    async def _fire_callback(self, subscription_id: str, event: CubeChangeEvent):
        """Fire the callback for a subscription."""
        callback = self._callbacks.get(subscription_id)
        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error({
                    "event": "callback_error",
                    "subscription_id": subscription_id,
                    "error": str(e)
                })

    async def unsubscribe(self, subscription_id: str):
        """Remove a subscription."""
        async with self._lock:
            if subscription_id in self._active_listeners:
                listener = self._active_listeners[subscription_id]
                listener.unsubscribe()
                del self._active_listeners[subscription_id]

            if subscription_id in self._callbacks:
                del self._callbacks[subscription_id]

        logger.info({
            "event": "wardrobe_unsubscribed",
            "subscription_id": subscription_id
        })

    async def unsubscribe_all(self):
        """Remove all subscriptions."""
        async with self._lock:
            for listener in self._active_listeners.values():
                listener.unsubscribe()

            self._active_listeners.clear()
            self._callbacks.clear()

        logger.info({"event": "all_subscriptions_removed"})

    def get_active_subscriptions(self) -> Set[str]:
        """Get set of active subscription IDs."""
        return set(self._active_listeners.keys())


class WebSocketBroadcaster:
    """
    Broadcasts Firestore changes to connected WebSocket clients.

    Integrates with FastAPI WebSocket manager to push real-time
    updates to frontend clients.
    """

    def __init__(self, firestore_client):
        self.db = firestore_client
        self.realtime = WardrobeRealtimeListener(firestore_client)
        self._user_connections: Dict[str, Set[Any]] = {}
        self._lock = asyncio.Lock()

    async def register_connection(self, user_id: str, websocket):
        """Register a WebSocket connection for a user."""
        async with self._lock:
            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()

                # Start listening for this user
                await self.realtime.subscribe_user_wardrobe(
                    user_id=user_id,
                    on_change=lambda event: self._broadcast_to_user(user_id, event)
                )

            self._user_connections[user_id].add(websocket)

        logger.info({
            "event": "websocket_registered",
            "user_id": user_id[:8] + "...",
            "total_connections": len(self._user_connections[user_id])
        })

    async def unregister_connection(self, user_id: str, websocket):
        """Unregister a WebSocket connection."""
        async with self._lock:
            if user_id in self._user_connections:
                self._user_connections[user_id].discard(websocket)

                # If no more connections, stop listening
                if not self._user_connections[user_id]:
                    del self._user_connections[user_id]
                    # Find and remove subscription
                    for sub_id in list(self.realtime._active_listeners.keys()):
                        if sub_id.startswith(f"{user_id}:"):
                            await self.realtime.unsubscribe(sub_id)

        logger.info({
            "event": "websocket_unregistered",
            "user_id": user_id[:8] + "..."
        })

    async def _broadcast_to_user(self, user_id: str, event: CubeChangeEvent):
        """Broadcast event to all user's WebSocket connections."""
        connections = self._user_connections.get(user_id, set())

        message = {
            'type': 'wardrobe_update',
            'cube_id': event.cube_id,
            'change_type': event.change_type,
            'agentic_state': event.agentic_state,
            'last_agent_id': event.last_agent_id,
            'modified_faces': event.modified_faces,
            'timestamp': event.timestamp.isoformat()
        }

        # Send to all connections
        disconnected = set()
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error({
                    "event": "websocket_send_failed",
                    "error": str(e)
                })
                disconnected.add(ws)

        # Clean up disconnected
        for ws in disconnected:
            await self.unregister_connection(user_id, ws)
