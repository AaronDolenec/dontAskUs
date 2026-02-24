"""WebSocket connection manager for real-time group events.

Manages two kinds of connections:
1. Group-level: ws/groups/{group_id} — receives ALL events for a group
2. Question-level: ws/groups/{group_id}/questions/{question_id} — vote updates only (legacy)

Event types broadcast to group-level connections:
- vote_update: a member voted or changed their vote
- new_question: the daily question rolled over
- streak_update: a member's streak changed (increment or reset)
- member_joined: a new member joined the group
- member_left: a member left the group
- ping/pong: keepalive
"""

from typing import Set, Dict, Optional, Any
import json
import logging
from datetime import datetime, timezone
# pylint: disable=broad-except


class ConnectionManager:
    def __init__(self):
        # Question-level connections: {group_id: {question_id: set(websocket)}}
        self.active_connections: Dict[str, Dict[str, Set]] = {}

        # Group-level connections: {group_id: set(websocket)}
        self.group_connections: Dict[str, Set] = {}

        # Track authenticated user for each group connection: {id(ws): {"user_id": ..., "display_name": ...}}
        self.group_user_map: Dict[int, Dict[str, Any]] = {}

    # ─── Question-Level (legacy) ─────────────────────────────────

    async def connect(self, group_id: str, question_id: str, websocket):
        """Accept a question-level WebSocket connection."""
        await websocket.accept()

        if group_id not in self.active_connections:
            self.active_connections[group_id] = {}
        if question_id not in self.active_connections[group_id]:
            self.active_connections[group_id][question_id] = set()

        self.active_connections[group_id][question_id].add(websocket)
        logging.info("WS question-level connect: group=%s question=%s", group_id, question_id)

    def disconnect(self, group_id: str, question_id: str, websocket):
        """Remove a question-level WebSocket connection."""
        if (group_id in self.active_connections and
                question_id in self.active_connections[group_id]):
            self.active_connections[group_id][question_id].discard(websocket)

            if not self.active_connections[group_id][question_id]:
                del self.active_connections[group_id][question_id]
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]

        logging.info("WS question-level disconnect: group=%s question=%s", group_id, question_id)

    async def broadcast_update(self, group_id: str, question_id: str, data: dict):
        """Broadcast to all clients in a specific question room (legacy)."""
        if (group_id in self.active_connections and
                question_id in self.active_connections[group_id]):

            message = json.dumps({
                "type": "update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            })

            connections = list(self.active_connections[group_id][question_id])
            for connection in connections:
                try:
                    await connection.send_text(message)
                except (OSError, RuntimeError):
                    logging.exception("Error sending WS message; removing connection")
                    self.active_connections[group_id][question_id].discard(connection)

    # ─── Group-Level ─────────────────────────────────────────────

    async def connect_group(self, group_id: str, websocket, user_info: Optional[Dict] = None):
        """Accept a group-level WebSocket connection."""
        await websocket.accept()

        if group_id not in self.group_connections:
            self.group_connections[group_id] = set()

        self.group_connections[group_id].add(websocket)
        if user_info:
            self.group_user_map[id(websocket)] = user_info

        logging.info("WS group-level connect: group=%s user=%s",
                      group_id, (user_info or {}).get("display_name", "?"))

    def disconnect_group(self, group_id: str, websocket):
        """Remove a group-level WebSocket connection."""
        if group_id in self.group_connections:
            self.group_connections[group_id].discard(websocket)
            if not self.group_connections[group_id]:
                del self.group_connections[group_id]

        self.group_user_map.pop(id(websocket), None)
        logging.info("WS group-level disconnect: group=%s", group_id)

    def get_group_connection_count(self, group_id: str) -> int:
        """Return the number of active group-level connections for a group."""
        return len(self.group_connections.get(group_id, set()))

    # ─── Broadcast Helpers ───────────────────────────────────────

    async def broadcast_to_group(self, group_id: str, event_type: str, data: dict):
        """Broadcast a typed event to all group-level connections in a group.

        Args:
            group_id: The group's public UUID string.
            event_type: One of: vote_update, new_question, streak_update,
                        member_joined, member_left, question_results.
            data: Event payload dict.
        """
        connections = list(self.group_connections.get(group_id, set()))
        if not connections:
            return

        message = json.dumps({
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })

        for connection in connections:
            try:
                await connection.send_text(message)
            except (OSError, RuntimeError):
                logging.warning("Error sending group WS message; removing connection")
                self.group_connections.get(group_id, set()).discard(connection)
                self.group_user_map.pop(id(connection), None)

    async def broadcast_vote_update(self, group_id: str, question_id: str, data: dict):
        """Broadcast a vote update to BOTH question-level and group-level clients."""
        # Question-level (legacy)
        await self.broadcast_update(group_id, question_id, data)

        # Group-level — wrap as vote_update event
        await self.broadcast_to_group(group_id, "vote_update", {
            "question_id": question_id,
            **data,
        })

    async def broadcast_new_question(self, group_id: str, question_data: dict):
        """Broadcast new_question event to all group-level clients."""
        await self.broadcast_to_group(group_id, "new_question", question_data)

    async def broadcast_streak_update(self, group_id: str, streak_data: dict):
        """Broadcast streak_update event to all group-level clients."""
        await self.broadcast_to_group(group_id, "streak_update", streak_data)

    async def broadcast_member_event(self, group_id: str, event_type: str, member_data: dict):
        """Broadcast member_joined or member_left event."""
        await self.broadcast_to_group(group_id, event_type, member_data)


manager = ConnectionManager()
