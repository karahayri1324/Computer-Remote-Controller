import json
import time
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)
@dataclass
class UserConnection:
    agent_ws: WebSocket | None = None
    agent_alive: bool = False
    agent_last_heartbeat: float = 0
    web_clients: dict[str, WebSocket] = field(default_factory=dict)
class ConnectionManager:
    def __init__(self):
        self.users: dict[str, UserConnection] = {}

    def _get_user(self, username: str) -> UserConnection:
        if username not in self.users:
            self.users[username] = UserConnection()
        return self.users[username]
    async def register_agent(self, username: str, ws: WebSocket):
        uc = self._get_user(username)
        if uc.agent_ws is not None:
            try:
                await uc.agent_ws.close(code=1000, reason="New agent connected")
            except Exception:
                pass
        uc.agent_ws = ws
        uc.agent_alive = True
        uc.agent_last_heartbeat = time.time()
        logger.info(f"Agent connected: {username}")
        await self._broadcast_agent_status(username)

    async def unregister_agent(self, username: str):
        uc = self._get_user(username)
        uc.agent_ws = None
        uc.agent_alive = False
        logger.info(f"Agent disconnected: {username}")
        await self._broadcast_agent_status(username)
    async def register_web_client(self, username: str, session_id: str, ws: WebSocket):
        uc = self._get_user(username)
        uc.web_clients[session_id] = ws
        logger.info(f"Web client connected: {username}/{session_id}")
        await self._send_to_ws(ws, {
            "type": "agent_status",
            "payload": {"online": uc.agent_alive}
        })

    def unregister_web_client(self, username: str, session_id: str):
        uc = self.users.get(username)
        if uc:
            uc.web_clients.pop(session_id, None)
        logger.info(f"Web client disconnected: {username}/{session_id}")
    async def route_to_agent(self, username: str, message: dict) -> bool:
        uc = self.users.get(username)
        if not uc or uc.agent_ws is None or not uc.agent_alive:
            return False
        try:
            await uc.agent_ws.send_text(json.dumps(message))
            return True
        except Exception:
            return False

    async def route_to_web_clients(self, username: str, message: dict):
        uc = self.users.get(username)
        if not uc:
            return
        dead = []
        for sid, ws in uc.web_clients.items():
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(sid)
        for sid in dead:
            uc.web_clients.pop(sid, None)

    async def route_to_web_client(self, username: str, session_id: str, message: dict):
        uc = self.users.get(username)
        if not uc:
            return
        ws = uc.web_clients.get(session_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                uc.web_clients.pop(session_id, None)
    def update_heartbeat(self, username: str):
        uc = self.users.get(username)
        if uc:
            uc.agent_last_heartbeat = time.time()
            uc.agent_alive = True

    async def check_all_heartbeats(self, timeout: int):
        for username, uc in self.users.items():
            if uc.agent_ws is not None and uc.agent_alive:
                if time.time() - uc.agent_last_heartbeat > timeout:
                    uc.agent_alive = False
                    logger.warning(f"Agent heartbeat timeout: {username}")
                    await self._broadcast_agent_status(username)

    def is_agent_online(self, username: str) -> bool:
        uc = self.users.get(username)
        return uc.agent_alive if uc else False
    async def _broadcast_agent_status(self, username: str):
        uc = self.users.get(username)
        if not uc:
            return
        await self.route_to_web_clients(username, {
            "type": "agent_status",
            "payload": {"online": uc.agent_alive}
        })

    async def _send_to_ws(self, ws: WebSocket, message: dict):
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            pass
manager = ConnectionManager()
