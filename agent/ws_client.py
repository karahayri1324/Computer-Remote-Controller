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
        # Timestamp (monotonic) of the last message received from the relay.
        # The watchdog uses this to detect dead / half-open connections.
        self._last_recv = 0.0

    async def run_forever(self):
        delay = self.config.reconnect_base_delay
        while True:
            try:
                logger.info(f"Connecting to {self.config.relay_url}")
                async with websockets.connect(
                    self.config.relay_url,
                    max_size=2 ** 24,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                ) as ws:
                    self.ws = ws

                    await ws.send(json.dumps({
                        "type": "auth",
                        "payload": {
                            "username": self.config.username,
                            "token": self.config.agent_token,
                        }
                    }))
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    resp = json.loads(raw)
                    if not resp.get("payload", {}).get("success"):
                        logger.error("Authentication failed")
                        await asyncio.sleep(30)
                        continue

                    logger.info("Connected and authenticated")
                    delay = self.config.reconnect_base_delay
                    self._last_recv = time.monotonic()

                    # Run all loops together. Whichever one finishes or raises
                    # first (a dropped connection, or the watchdog firing) tears
                    # down the others so we fall through to the reconnect logic.
                    tasks = [
                        asyncio.create_task(self._recv_loop(ws)),
                        asyncio.create_task(self._send_loop(ws)),
                        asyncio.create_task(self._heartbeat_loop(ws)),
                        asyncio.create_task(self._watchdog_loop(ws)),
                    ]
                    try:
                        done, pending = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_COMPLETED
                        )
                    finally:
                        for t in tasks:
                            t.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                    # Surface the first real error so reconnect/backoff kicks in.
                    for t in done:
                        exc = t.exception()
                        if exc:
                            raise exc
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
            self._last_recv = time.monotonic()
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

    async def _watchdog_loop(self, ws):
        """Force a reconnect if the relay goes silent.

        The relay echoes a heartbeat back on every heartbeat we send, so under a
        healthy connection we receive data at least every heartbeat_interval. If
        nothing arrives for several intervals the link is dead (or half-open in a
        way the protocol ping/pong missed) — close it so run_forever reconnects.
        """
        timeout = max(self.config.heartbeat_interval * 3, 45)
        check_every = max(self.config.heartbeat_interval, 5)
        while True:
            await asyncio.sleep(check_every)
            silent_for = time.monotonic() - self._last_recv
            if silent_for > timeout:
                logger.warning(
                    f"No data from relay for {silent_for:.0f}s; forcing reconnect"
                )
                await ws.close(code=4000)
                return

    async def send(self, msg: dict):
        await self._send_queue.put(msg)
