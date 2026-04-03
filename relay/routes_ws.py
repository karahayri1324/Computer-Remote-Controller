import json
import time
import secrets
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from auth import verify_access_token
from connection_manager import manager
from users import verify_agent_token

logger = logging.getLogger(__name__)
router = APIRouter()

BROADCAST_TYPES = {"shell_output"}
SESSION_ROUTED_TYPES = {"file_list_res", "file_download_chunk", "file_upload_ack", "sysinfo_res",
                        "screen_frame", "screen_error", "screen_check_res"}
AGENT_FORWARD_TYPES = {"shell_input", "shell_resize", "shell_create", "shell_close",
                       "file_list_req", "file_download_req",
                       "file_upload_start", "file_upload_chunk",
                       "sysinfo_req",
                       "screen_start", "screen_stop", "screen_input", "screen_check"}
@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        msg = json.loads(raw)
        payload = msg.get("payload", {})
        username = payload.get("username", "").strip().lower()
        token = payload.get("token", "")

        if not username or msg.get("type") != "auth" or not verify_agent_token(username, token):
            await websocket.send_text(json.dumps({
                "type": "auth_result",
                "payload": {"success": False, "error": "Invalid credentials"}
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

    await manager.register_agent(username, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "heartbeat":
                manager.update_heartbeat(username)
                await websocket.send_text(json.dumps({
                    "type": "heartbeat", "payload": {"ts": time.time()}
                }))
            elif msg_type in BROADCAST_TYPES:
                msg.pop("_session_id", None)
                await manager.route_to_web_clients(username, msg)
            elif msg_type in SESSION_ROUTED_TYPES:
                session_id = msg.pop("_session_id", None)
                if session_id:
                    await manager.route_to_web_client(username, session_id, msg)
                else:
                    await manager.route_to_web_clients(username, msg)
            elif msg_type == "error":
                session_id = msg.pop("_session_id", None)
                if session_id:
                    await manager.route_to_web_client(username, session_id, msg)
                else:
                    await manager.route_to_web_clients(username, msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Agent error ({username}): {e}")
    finally:
        await manager.unregister_agent(username)
@router.websocket("/ws/client")
async def client_websocket(websocket: WebSocket, token: str = Query(...)):
    claims = verify_access_token(token)
    if not claims:
        await websocket.close(code=4001)
        return

    username = claims.get("sub", "")
    if not username:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    session_id = secrets.token_hex(8)
    await manager.register_web_client(username, session_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type in AGENT_FORWARD_TYPES:
                msg["_session_id"] = session_id
                sent = await manager.route_to_agent(username, msg)
                if not sent:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "payload": {"message": "Agent is not connected"}
                    }))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Web client error ({username}): {e}")
    finally:
        manager.unregister_web_client(username, session_id)
