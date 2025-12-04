from typing import Set, Dict, List
import json
from datetime import datetime

class ConnectionManager:
    def __init__(self):
        # Structure: {group_id: {question_id: [websocket_connections]}}
        self.active_connections: Dict[str, Dict[str, Set]] = {}
        self.user_map: Dict = {}  # Maps connection id to user info
    
    async def connect(self, group_id: str, question_id: str, websocket):
        await websocket.accept()
        
        if group_id not in self.active_connections:
            self.active_connections[group_id] = {}
        
        if question_id not in self.active_connections[group_id]:
            self.active_connections[group_id][question_id] = set()
        
        self.active_connections[group_id][question_id].add(websocket)
        print(f"WebSocket connection opened: Group={group_id}, Question={question_id}")
    
    def disconnect(self, group_id: str, question_id: str, websocket):
        if (group_id in self.active_connections and 
            question_id in self.active_connections[group_id]):
            self.active_connections[group_id][question_id].discard(websocket)
            
            # Clean up empty structures
            if not self.active_connections[group_id][question_id]:
                del self.active_connections[group_id][question_id]
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]
        
        print(f"WebSocket connection closed: Group={group_id}, Question={question_id}")
    
    async def broadcast_update(self, group_id: str, question_id: str, data: dict):
        """Broadcast update to all users in a specific question room"""
        if (group_id in self.active_connections and 
            question_id in self.active_connections[group_id]):
            
            message = json.dumps({
                "type": "update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            })
            
            # Use list to avoid "Set changed during iteration" error
            connections = list(self.active_connections[group_id][question_id])
            for connection in connections:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"Error sending message: {e}")
                    self.active_connections[group_id][question_id].discard(connection)
    
    async def broadcast_to_group(self, group_id: str, data: dict):
        """Broadcast to all active connections in a group"""
        if group_id in self.active_connections:
            message = json.dumps({
                "type": "group_update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            })
            
            # Flatten all connections in all questions for this group
            all_connections = []
            for connections_set in self.active_connections[group_id].values():
                all_connections.extend(connections_set)
            
            for connection in all_connections:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"Error sending group message: {e}")

manager = ConnectionManager()
