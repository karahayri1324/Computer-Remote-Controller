import json
import time
import asyncio
import logging
import random

import websockets

logger = logging.getLogger(__name__)


class RelayConnection:
    def __init__(self, config, message_handler):
        self.config = config
        self.handler = message_handler
        self.ws = None
        self._send_queue: asyncio.Queue = asyncio.Queue()

    async def run_forever(self):
        delay = self.config.reconnect_base_delay
        while True:
            try:
                logger.info(f"Connecting to {self.config.relay_url}")
                async with websockets.connect(
                    self.config.relay_url,
                    max_size=2 ** 21,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self.ws = ws

                    # Authenticate
                    await ws.send(json.dumps({
                        "type": "auth",
                        "payload": {"token": self.config.agent_token}
                    }))
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    resp = json.loads(raw)
                    if not resp.get("payload", {}).get("success"):
                        logger.error("Authentication failed")
                        await asyncio.sleep(30)
                        continue

                    logger.info("Connected and authenticated")
                    delay = self.config.reconnect_base_delay

                    await asyncio.gather(
                        self._recv_loop(ws),
                        self._send_loop(ws),
                        self._heartbeat_loop(ws),
                    )
            except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                logger.warning(f"Connection lost: {e}")
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
            finally:
                self.ws = None

            jitter = random.uniform(0, delay * 0.2)
            wait = delay + jitter
            logger.info(f"Reconnecting in {wait:.1f}s")
            await asyncio.sleep(wait)
            delay = min(delay * 2, self.config.reconnect_max_delay)

    async def _recv_loop(self, ws):
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "heartbeat":
                continue
            asyncio.create_task(self.handler(msg))

    async def _send_loop(self, ws):
        while True:
            msg = await self._send_queue.get()
            await ws.send(json.dumps(msg))

    async def _heartbeat_loop(self, ws):
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)
            await ws.send(json.dumps({
                "type": "heartbeat",
                "payload": {"ts": time.time()}
            }))

    async def send(self, msg: dict):
        await self._send_queue.put(msg)
