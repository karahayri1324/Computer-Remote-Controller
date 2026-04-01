import json
import time
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.agent_ws: WebSocket | None = None
        self.agent_alive: bool = False
        self.agent_last_heartbeat: float = 0
        self.web_clients: dict[str, WebSocket] = {}

    async def register_agent(self, ws: WebSocket):
        if self.agent_ws is not None:
            try:
                await self.agent_ws.close(code=1000, reason="New agent connected")
            except Exception:
                pass
        self.agent_ws = ws
        self.agent_alive = True
        self.agent_last_heartbeat = time.time()
        logger.info("Agent connected")
        await self._broadcast_agent_status()

    async def unregister_agent(self):
        self.agent_ws = None
        self.agent_alive = False
        logger.info("Agent disconnected")
        await self._broadcast_agent_status()

    async def register_web_client(self, session_id: str, ws: WebSocket):
        self.web_clients[session_id] = ws
        logger.info(f"Web client connected: {session_id}")
        await self._send_to_ws(ws, {
            "type": "agent_status",
            "payload": {"online": self.agent_alive}
        })

    def unregister_web_client(self, session_id: str):
        self.web_clients.pop(session_id, None)
        logger.info(f"Web client disconnected: {session_id}")

    async def route_to_agent(self, message: dict) -> bool:
        if self.agent_ws is None or not self.agent_alive:
            return False
        try:
            await self.agent_ws.send_text(json.dumps(message))
            return True
        except Exception:
            return False

    async def route_to_web_clients(self, message: dict):
        dead = []
        for sid, ws in self.web_clients.items():
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(sid)
        for sid in dead:
            self.web_clients.pop(sid, None)

    async def route_to_web_client(self, session_id: str, message: dict):
        ws = self.web_clients.get(session_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.web_clients.pop(session_id, None)

    async def check_agent_heartbeat(self, timeout: int):
        if self.agent_ws is not None and self.agent_alive:
            if time.time() - self.agent_last_heartbeat > timeout:
                self.agent_alive = False
                logger.warning("Agent heartbeat timeout")
                await self._broadcast_agent_status()

    async def _broadcast_agent_status(self):
        await self.route_to_web_clients({
            "type": "agent_status",
            "payload": {"online": self.agent_alive}
        })

    async def _send_to_ws(self, ws: WebSocket, message: dict):
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            pass


manager = ConnectionManager()
