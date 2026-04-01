import asyncio
import logging

from config import load_config
from ws_client import RelayConnection
from shell import ShellManager
from file_ops import FileOperations
from sysinfo import SystemInfo
from screen import ScreenCapture

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    config = load_config()
    sysinfo = SystemInfo(cache_ttl=config.sysinfo_cache_seconds)

    conn = RelayConnection(config, message_handler=None)

    async def send(msg: dict):
        await conn.send(msg)

    shell = ShellManager(send_callback=send)
    files = FileOperations(send_callback=send, allowed_paths=config.allowed_paths)
    screen = ScreenCapture(send_callback=send)

    async def handle_message(msg: dict):
        t = msg.get("type", "")
        p = msg.get("payload", {})
        sid = msg.get("_session_id")
        rid = msg.get("id")

        try:
            if t == "shell_input":
                if shell.pid is None:
                    await shell.start(config.shell_default_cols, config.shell_default_rows)
                await shell.write(p.get("data", ""))

            elif t == "shell_resize":
                cols = p.get("cols", config.shell_default_cols)
                rows = p.get("rows", config.shell_default_rows)
                if shell.pid is None:
                    await shell.start(cols, rows)
                else:
                    shell.resize(cols, rows)

            elif t == "file_list_req":
                await files.list_directory(p.get("path", "/"), rid, sid)

            elif t == "file_download_req":
                await files.download_file(p.get("path", ""), rid, sid)

            elif t == "file_upload_start":
                await files.handle_upload_start(
                    p.get("path", ""), p.get("total_size", 0),
                    p.get("total_chunks", 1), sid
                )

            elif t == "file_upload_chunk":
                await files.handle_upload_chunk(
                    p.get("path", ""), p.get("chunk_index", 0),
                    p.get("data", ""), p.get("done", False), rid, sid
                )

            elif t == "sysinfo_req":
                data = sysinfo.collect()
                await send({
                    "type": "sysinfo_res",
                    "id": rid,
                    "_session_id": sid,
                    "payload": data,
                })

            elif t == "screen_start":
                await screen.start_stream(
                    session_id=sid,
                    fps=p.get("fps", 15),
                    quality=p.get("quality", 50),
                    max_width=p.get("max_width", 1280),
                )

            elif t == "screen_stop":
                await screen.stop_stream()

            elif t == "screen_input":
                await screen.handle_input(
                    p.get("input_type", ""),
                    p.get("data", {}),
                )

            elif t == "screen_check":
                await send({
                    "type": "screen_check_res",
                    "_session_id": sid,
                    "payload": {"available": screen.available, "input_available": True},
                })

        except Exception as e:
            logger.error(f"Error handling {t}: {e}")
            await send({
                "type": "error",
                "_session_id": sid,
                "payload": {"message": str(e)}
            })

    conn.handler = handle_message
    logger.info("Agent starting...")
    await conn.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
