import io
import asyncio
import logging
import base64
import time

logger = logging.getLogger(__name__)

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import subprocess
    def _check_xdotool():
        try:
            subprocess.run(["xdotool", "--version"], capture_output=True, timeout=2)
            return True
        except Exception:
            return False
    HAS_XDOTOOL = _check_xdotool()
except Exception:
    HAS_XDOTOOL = False


class ScreenCapture:
    def __init__(self, send_callback):
        self.send = send_callback
        self._streaming = False
        self._stream_task = None
        self._target_fps = 15
        self._quality = 50
        self._max_width = 1280
        self._session_id = None

    @property
    def available(self) -> bool:
        return HAS_MSS and HAS_PIL

    async def start_stream(self, session_id: str, fps: int = 15, quality: int = 50, max_width: int = 1280):
        if not self.available:
            await self.send({
                "type": "screen_error",
                "_session_id": session_id,
                "payload": {"message": "Screen capture not available. Install: pip install mss Pillow"}
            })
            return

        self._target_fps = min(fps, 30)
        self._quality = max(10, min(quality, 95))
        self._max_width = max_width
        self._session_id = session_id

        if self._streaming:
            return

        self._streaming = True
        self._stream_task = asyncio.create_task(self._capture_loop())
        logger.info(f"Screen stream started: {fps}fps, q={quality}, w={max_width}")

    async def stop_stream(self):
        self._streaming = False
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        logger.info("Screen stream stopped")

    async def _capture_loop(self):
        frame_interval = 1.0 / self._target_fps
        try:
            with mss.mss() as sct:
                # Use primary monitor (index 1, index 0 is all monitors combined)
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

                while self._streaming:
                    t0 = time.monotonic()

                    # Capture screen
                    screenshot = sct.grab(monitor)

                    # Convert to PIL Image and resize
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                    # Resize if wider than max_width
                    if img.width > self._max_width:
                        ratio = self._max_width / img.width
                        new_size = (self._max_width, int(img.height * ratio))
                        img = img.resize(new_size, Image.LANCZOS)

                    # Compress to JPEG
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=self._quality, optimize=True)
                    frame_data = base64.b64encode(buf.getvalue()).decode("ascii")

                    await self.send({
                        "type": "screen_frame",
                        "_session_id": self._session_id,
                        "payload": {
                            "data": frame_data,
                            "width": img.width,
                            "height": img.height,
                        }
                    })

                    # Maintain target FPS
                    elapsed = time.monotonic() - t0
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                    else:
                        await asyncio.sleep(0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Screen capture error: {e}")
            await self.send({
                "type": "screen_error",
                "_session_id": self._session_id,
                "payload": {"message": str(e)}
            })
        finally:
            self._streaming = False

    async def handle_input(self, input_type: str, data: dict):
        if not HAS_XDOTOOL:
            return

        try:
            loop = asyncio.get_event_loop()
            if input_type == "mouse_move":
                x, y = int(data["x"]), int(data["y"])
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ["xdotool", "mousemove", str(x), str(y)],
                    capture_output=True, timeout=1
                ))
            elif input_type == "mouse_click":
                button = str(data.get("button", 1))
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ["xdotool", "click", button],
                    capture_output=True, timeout=1
                ))
            elif input_type == "mouse_dblclick":
                button = str(data.get("button", 1))
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ["xdotool", "click", "--repeat", "2", button],
                    capture_output=True, timeout=1
                ))
            elif input_type == "mouse_scroll":
                direction = data.get("direction", "up")
                clicks = str(data.get("clicks", 3))
                btn = "4" if direction == "up" else "5"
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ["xdotool", "click", "--repeat", clicks, btn],
                    capture_output=True, timeout=1
                ))
            elif input_type == "key_press":
                key = data.get("key", "")
                if key:
                    await loop.run_in_executor(None, lambda: subprocess.run(
                        ["xdotool", "key", key],
                        capture_output=True, timeout=1
                    ))
            elif input_type == "key_type":
                text = data.get("text", "")
                if text:
                    await loop.run_in_executor(None, lambda: subprocess.run(
                        ["xdotool", "type", "--clearmodifiers", text],
                        capture_output=True, timeout=1
                    ))
            elif input_type == "mouse_down":
                button = str(data.get("button", 1))
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ["xdotool", "mousedown", button],
                    capture_output=True, timeout=1
                ))
            elif input_type == "mouse_up":
                button = str(data.get("button", 1))
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ["xdotool", "mouseup", button],
                    capture_output=True, timeout=1
                ))
        except Exception as e:
            logger.error(f"Input handling error: {e}")
