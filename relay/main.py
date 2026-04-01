import asyncio
import logging
import os
import sys

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import load_config
from connection_manager import manager
from routes_api import router as api_router
from routes_ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)
async def heartbeat_checker(interval: int, timeout: int):
    while True:
        await asyncio.sleep(interval)
        await manager.check_all_heartbeats(timeout)
@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    task = asyncio.create_task(
        heartbeat_checker(cfg.heartbeat_interval, cfg.heartbeat_timeout)
    )
    logger.info(f"Relay server starting on {cfg.host}:{cfg.port} (multi-user)")
    yield
    task.cancel()
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
app.include_router(ws_router)

cfg = load_config()
web_root = os.path.join(os.path.dirname(__file__), cfg.web_root)
if os.path.isdir(web_root):
    app.mount("/", StaticFiles(directory=web_root, html=True), name="web")
else:
    logger.warning(f"Web root not found: {web_root}")
if __name__ == "__main__":
    cfg = load_config()
    uvicorn.run(
        "main:app",
        host=cfg.host,
        port=cfg.port,
        log_level="info",
    )
