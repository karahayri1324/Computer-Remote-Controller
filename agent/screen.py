import io
import sys
import asyncio
import logging
import base64
import time
import subprocess

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

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

HAS_INPUT = False

if IS_WINDOWS:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        HAS_INPUT = True

        INPUT_MOUSE = 0
        INPUT_KEYBOARD = 1
        MOUSEEVENTF_MOVE = 0x0001
        MOUSEEVENTF_ABSOLUTE = 0x8000
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010
        MOUSEEVENTF_MIDDLEDOWN = 0x0020
        MOUSEEVENTF_MIDDLEUP = 0x0040
        MOUSEEVENTF_WHEEL = 0x0800
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_UNICODE = 0x0004
        WHEEL_DELTA = 120
        SM_CXSCREEN = 0
        SM_CYSCREEN = 1

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]

    except Exception:
        HAS_INPUT = False
else:
    try:
        def _check_xdotool():
            try:
                subprocess.run(["xdotool", "--version"], capture_output=True, timeout=2)
                return True
            except Exception:
                return False
        HAS_INPUT = _check_xdotool()
    except Exception:
        HAS_INPUT = False
class ScreenCapture:
    def __init__(self, send_callback):
        self.send = send_callback
        self._streaming = False
        self._stream_task = None
        self._target_fps = 15
        self._quality = 50
        self._max_width = 1280
        self._session_id = None
        self._screen_width = 0
        self._screen_height = 0
        self._img_width = 0
        self._img_height = 0

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

        self._target_fps = min(fps, 60)
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

    def _encode_image(self, img):
        if img.width > self._max_width:
            ratio = self._max_width / img.width
            new_size = (self._max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.BILINEAR)

        self._img_width = img.width
        self._img_height = img.height

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self._quality)
        return {
            "data": base64.b64encode(buf.getvalue()).decode("ascii"),
            "width": img.width,
            "height": img.height,
        }

    async def _capture_loop(self):
        frame_interval = 1.0 / self._target_fps
        loop = asyncio.get_event_loop()
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

                while self._streaming:
                    t0 = time.monotonic()

                    screenshot = sct.grab(monitor)
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                    self._screen_width = img.width
                    self._screen_height = img.height

                    payload = await loop.run_in_executor(None, self._encode_image, img)

                    await self.send({
                        "type": "screen_frame",
                        "_session_id": self._session_id,
                        "payload": payload,
                    })

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

    def _scale_coords(self, x, y):
        if self._img_width > 0 and self._screen_width > 0:
            x = int(x * self._screen_width / self._img_width)
            y = int(y * self._screen_height / self._img_height)
        return x, y

    async def handle_input(self, input_type: str, data: dict):
        if not HAS_INPUT:
            return
        try:
            loop = asyncio.get_event_loop()
            if IS_WINDOWS:
                await loop.run_in_executor(None, self._handle_input_windows, input_type, data)
            else:
                await loop.run_in_executor(None, self._handle_input_linux, input_type, data)
        except Exception as e:
            logger.error(f"Input handling error: {e}")
    def _handle_input_linux(self, input_type: str, data: dict):
        def _run(args):
            subprocess.run(args, capture_output=True, timeout=2)

        if input_type == "mouse_move":
            x, y = self._scale_coords(int(data["x"]), int(data["y"]))
            _run(["xdotool", "mousemove", str(x), str(y)])
        elif input_type == "mouse_click":
            x, y = self._scale_coords(int(data["x"]), int(data["y"]))
            _run(["xdotool", "mousemove", "--sync", str(x), str(y),
                  "click", str(data.get("button", 1))])
        elif input_type == "mouse_dblclick":
            x, y = self._scale_coords(int(data["x"]), int(data["y"]))
            _run(["xdotool", "mousemove", "--sync", str(x), str(y),
                  "click", "--repeat", "2", "--delay", "50",
                  str(data.get("button", 1))])
        elif input_type == "mouse_scroll":
            if "x" in data and "y" in data:
                x, y = self._scale_coords(int(data["x"]), int(data["y"]))
                _run(["xdotool", "mousemove", "--sync", str(x), str(y)])
            btn = "4" if data.get("direction", "up") == "up" else "5"
            clicks = int(data.get("clicks", 3))
            clicks = max(1, min(clicks, 20))
            _run(["xdotool", "click", "--repeat", str(clicks), "--delay", "8", btn])
        elif input_type == "key_press":
            key = data.get("key", "")
            if key:
                _run(["xdotool", "key", "--delay", "0", key])
        elif input_type == "key_type":
            text = data.get("text", "")
            if text:
                _run(["xdotool", "type", "--delay", "0", "--clearmodifiers", text])
        elif input_type == "mouse_down":
            if "x" in data and "y" in data:
                x, y = self._scale_coords(int(data["x"]), int(data["y"]))
                _run(["xdotool", "mousemove", "--sync", str(x), str(y)])
            _run(["xdotool", "mousedown", str(data.get("button", 1))])
        elif input_type == "mouse_up":
            _run(["xdotool", "mouseup", str(data.get("button", 1))])
    def _handle_input_windows(self, input_type: str, data: dict):
        if input_type == "mouse_move":
            x, y = self._scale_coords(int(data["x"]), int(data["y"]))
            user32.SetCursorPos(x, y)

        elif input_type == "mouse_click":
            x, y = self._scale_coords(int(data["x"]), int(data["y"]))
            user32.SetCursorPos(x, y)
            btn = int(data.get("button", 1))
            down, up = self._win_mouse_buttons(btn)
            self._win_send_mouse(down)
            self._win_send_mouse(up)

        elif input_type == "mouse_dblclick":
            x, y = self._scale_coords(int(data["x"]), int(data["y"]))
            user32.SetCursorPos(x, y)
            btn = int(data.get("button", 1))
            down, up = self._win_mouse_buttons(btn)
            for _ in range(2):
                self._win_send_mouse(down)
                self._win_send_mouse(up)

        elif input_type == "mouse_down":
            if "x" in data and "y" in data:
                x, y = self._scale_coords(int(data["x"]), int(data["y"]))
                user32.SetCursorPos(x, y)
            down, _ = self._win_mouse_buttons(int(data.get("button", 1)))
            self._win_send_mouse(down)

        elif input_type == "mouse_up":
            _, up = self._win_mouse_buttons(int(data.get("button", 1)))
            self._win_send_mouse(up)

        elif input_type == "mouse_scroll":
            if "x" in data and "y" in data:
                x, y = self._scale_coords(int(data["x"]), int(data["y"]))
                user32.SetCursorPos(x, y)
            direction = data.get("direction", "up")
            clicks = int(data.get("clicks", 3))
            clicks = max(1, min(clicks, 20))
            amount = WHEEL_DELTA * clicks * (1 if direction == "up" else -1)
            inp = INPUT(type=INPUT_MOUSE)
            inp.union.mi.dwFlags = MOUSEEVENTF_WHEEL
            inp.union.mi.mouseData = amount & 0xFFFFFFFF
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        elif input_type == "key_type":
            text = data.get("text", "")
            for ch in text:
                inp_down = INPUT(type=INPUT_KEYBOARD)
                inp_down.union.ki.wScan = ord(ch)
                inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
                inp_up = INPUT(type=INPUT_KEYBOARD)
                inp_up.union.ki.wScan = ord(ch)
                inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
                user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

        elif input_type == "key_press":
            key = data.get("key", "")
            vk = self._win_key_to_vk(key)
            if vk:
                inp_down = INPUT(type=INPUT_KEYBOARD)
                inp_down.union.ki.wVk = vk
                inp_up = INPUT(type=INPUT_KEYBOARD)
                inp_up.union.ki.wVk = vk
                inp_up.union.ki.dwFlags = KEYEVENTF_KEYUP
                user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
                user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

    def _win_mouse_buttons(self, button):
        if button == 3:
            return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif button == 2:
            return MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    def _win_send_mouse(self, flags):
        inp = INPUT(type=INPUT_MOUSE)
        inp.union.mi.dwFlags = flags
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    @staticmethod
    def _win_key_to_vk(key_str: str) -> int:
        """Map xdotool-style key names to Windows VK codes."""
        parts = key_str.lower().split("+")
        modifiers = []
        main_key = parts[-1] if parts else ""
        for p in parts[:-1]:
            modifiers.append(p.strip())

        vk_map = {
            "return": 0x0D, "backspace": 0x08, "tab": 0x09, "escape": 0x1B,
            "space": 0x20, "delete": 0x2E, "insert": 0x2D,
            "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
            "home": 0x24, "end": 0x23, "prior": 0x21, "next": 0x22,
            "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
            "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
            "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
            "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "super": 0x5B,
        }

        if modifiers:
            for mod in modifiers:
                vk = vk_map.get(mod, 0)
                if vk:
                    inp = INPUT(type=INPUT_KEYBOARD)
                    inp.union.ki.wVk = vk
                    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        main_vk = vk_map.get(main_key, 0)
        if not main_vk and len(main_key) == 1:
            main_vk = user32.VkKeyScanW(ord(main_key)) & 0xFF

        if main_vk:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.union.ki.wVk = main_vk
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            inp2 = INPUT(type=INPUT_KEYBOARD)
            inp2.union.ki.wVk = main_vk
            inp2.union.ki.dwFlags = KEYEVENTF_KEYUP
            user32.SendInput(1, ctypes.byref(inp2), ctypes.sizeof(INPUT))

        if modifiers:
            for mod in reversed(modifiers):
                vk = vk_map.get(mod, 0)
                if vk:
                    inp = INPUT(type=INPUT_KEYBOARD)
                    inp.union.ki.wVk = vk
                    inp.union.ki.dwFlags = KEYEVENTF_KEYUP
                    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        return 0  # Already handled
