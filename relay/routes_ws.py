import json
import time
import secrets
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from auth import verify_agent_token, verify_access_token
from connection_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()

# Message types the agent sends that should be broadcast to all web clients
BROADCAST_TYPES = {"shell_output"}

# Message types the agent sends that should go to a specific web client
SESSION_ROUTED_TYPES = {"file_list_res", "file_download_chunk", "file_upload_ack", "sysinfo_res", "screen_frame", "screen_error", "screen_check_res"}

# Message types web clients can send to the agent
AGENT_FORWARD_TYPES = {
    "shell_input", "shell_resize",
    "file_list_req", "file_download_req",
    "file_upload_start", "file_upload_chunk",
    "sysinfo_req",
    "screen_start", "screen_stop", "screen_input", "screen_check",
}


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()

    # First message must be auth
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        msg = json.loads(raw)
        if msg.get("type") != "auth" or not verify_agent_token(msg.get("payload", {}).get("token", "")):
            await websocket.send_text(json.dumps({
                "type": "auth_result",
                "payload": {"success": False, "error": "Invalid agent token"}
            }))
            await websocket.close(code=4001)
            return
        await websocket.send_text(json.dumps({
            "type": "auth_result",
            "payload": {"success": True}
        }))
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Agent auth failed: {e}")
        await websocket.close(code=4001)
        return

    await manager.register_agent(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "heartbeat":
                manager.agent_last_heartbeat = time.time()
                manager.agent_alive = True
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "payload": {"ts": time.time()}
                }))
            elif msg_type in BROADCAST_TYPES:
                # Remove internal session_id before broadcasting
                msg.pop("_session_id", None)
                await manager.route_to_web_clients(msg)
            elif msg_type in SESSION_ROUTED_TYPES:
                session_id = msg.pop("_session_id", None)
                if session_id:
                    await manager.route_to_web_client(session_id, msg)
                else:
                    await manager.route_to_web_clients(msg)
            elif msg_type == "error":
                session_id = msg.pop("_session_id", None)
                if session_id:
                    await manager.route_to_web_client(session_id, msg)
                else:
                    await manager.route_to_web_clients(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Agent connection error: {e}")
    finally:
        await manager.unregister_agent()


@router.websocket("/ws/client")
async def client_websocket(websocket: WebSocket, token: str = Query(...)):
    # Validate JWT
    claims = verify_access_token(token)
    if not claims:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    session_id = secrets.token_hex(8)
    await manager.register_web_client(session_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type in AGENT_FORWARD_TYPES:
                msg["_session_id"] = session_id
                sent = await manager.route_to_agent(msg)
                if not sent:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "payload": {"message": "Agent is not connected"}
                    }))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Web client error: {e}")
    finally:
        manager.unregister_web_client(session_id)
