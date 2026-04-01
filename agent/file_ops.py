import os
import stat
import base64
import asyncio
import logging

logger = logging.getLogger(__name__)

CHUNK_SIZE = 524288  # 512KB


class FileOperations:
    def __init__(self, send_callback, allowed_paths=None):
        self.send = send_callback
        self.allowed_paths = allowed_paths or []
        self._uploads: dict[str, dict] = {}

    def _check_path(self, path: str) -> str:
        resolved = os.path.realpath(path)
        if self.allowed_paths:
            if not any(resolved.startswith(os.path.realpath(ap)) for ap in self.allowed_paths):
                raise PermissionError(f"Access denied: {path}")
        return resolved

    async def list_directory(self, path: str, request_id: str, session_id: str):
        try:
            resolved = self._check_path(path)
            entries = []
            for name in sorted(os.listdir(resolved)):
                full = os.path.join(resolved, name)
                try:
                    st = os.stat(full)
                    entries.append({
                        "name": name,
                        "is_dir": stat.S_ISDIR(st.st_mode),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "permissions": oct(st.st_mode)[-3:]
                    })
                except PermissionError:
                    entries.append({
                        "name": name, "is_dir": False, "size": 0,
                        "mtime": 0, "permissions": "---"
                    })
            await self.send({
                "type": "file_list_res",
                "id": request_id,
                "_session_id": session_id,
                "payload": {"path": resolved, "entries": entries, "error": None}
            })
        except Exception as e:
            await self.send({
                "type": "file_list_res",
                "id": request_id,
                "_session_id": session_id,
                "payload": {"path": path, "entries": [], "error": str(e)}
            })

    async def download_file(self, path: str, request_id: str, session_id: str):
        try:
            resolved = self._check_path(path)
            file_size = os.path.getsize(resolved)
            total_chunks = max(1, (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE)

            with open(resolved, "rb") as f:
                for chunk_index in range(total_chunks):
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    await self.send({
                        "type": "file_download_chunk",
                        "id": request_id,
                        "_session_id": session_id,
                        "payload": {
                            "path": resolved,
                            "chunk_index": chunk_index,
                            "total_chunks": total_chunks,
                            "data": base64.b64encode(data).decode("ascii"),
                            "done": chunk_index == total_chunks - 1
                        }
                    })
                    await asyncio.sleep(0)
        except Exception as e:
            await self.send({
                "type": "error",
                "id": request_id,
                "_session_id": session_id,
                "payload": {"message": f"Download failed: {e}"}
            })

    async def handle_upload_start(self, path: str, total_size: int, total_chunks: int, session_id: str):
        try:
            resolved = self._check_path(path)
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(resolved), exist_ok=True)
            self._uploads[resolved] = {
                "expected": total_chunks,
                "received": 0,
                "f": open(resolved, "wb"),
                "session_id": session_id,
            }
            logger.info(f"Upload started: {resolved} ({total_size} bytes, {total_chunks} chunks)")
        except Exception as e:
            await self.send({
                "type": "error",
                "_session_id": session_id,
                "payload": {"message": f"Upload start failed: {e}"}
            })

    async def handle_upload_chunk(self, path: str, chunk_index: int, data_b64: str,
                                   done: bool, request_id: str, session_id: str):
        try:
            resolved = self._check_path(path)
            state = self._uploads.get(resolved)
            if not state:
                await self.send({
                    "type": "error",
                    "id": request_id,
                    "_session_id": session_id,
                    "payload": {"message": "No upload in progress for this path"}
                })
                return

            raw = base64.b64decode(data_b64)
            state["f"].write(raw)
            state["received"] += 1

            await self.send({
                "type": "file_upload_ack",
                "id": request_id,
                "_session_id": session_id,
                "payload": {
                    "path": path,
                    "chunk_index": chunk_index,
                    "success": True,
                    "error": None
                }
            })

            if done:
                state["f"].close()
                del self._uploads[resolved]
                logger.info(f"Upload completed: {resolved}")
        except Exception as e:
            await self.send({
                "type": "file_upload_ack",
                "id": request_id,
                "_session_id": session_id,
                "payload": {
                    "path": path,
                    "chunk_index": chunk_index,
                    "success": False,
                    "error": str(e)
                }
            })
