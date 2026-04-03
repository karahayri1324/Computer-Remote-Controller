import os
import sys
import signal
import asyncio
import subprocess
import logging

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

if not IS_WINDOWS:
    import pty
    import struct
    import fcntl
    import termios


class ShellInstance:
    def __init__(self, shell_id: str, send_callback):
        self.shell_id = shell_id
        self.send = send_callback
        self.master_fd = None
        self.pid = None
        self._reader_task = None
        self._process = None

    async def start(self, cols=120, rows=30):
        if IS_WINDOWS:
            await self._start_windows(cols, rows)
        else:
            await self._start_linux(cols, rows)

    async def _start_linux(self, cols, rows):
        if self.pid is not None:
            return

        master_fd, slave_fd = pty.openpty()
        child_pid = os.fork()

        if child_pid == 0:
            os.close(master_fd)
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLUMNS"] = str(cols)
            env["LINES"] = str(rows)
            shell = os.environ.get("SHELL", "/bin/bash")
            os.execvpe(shell, [shell, "--login"], env)
        else:
            os.close(slave_fd)
            self.master_fd = master_fd
            self.pid = child_pid
            self.resize(cols, rows)

            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self._reader_task = asyncio.create_task(self._read_loop_linux())
            logger.info(f"Shell {self.shell_id} started (pid={child_pid})")

    async def _start_windows(self, cols, rows):
        if self._process is not None:
            return

        shell_cmd = "powershell.exe"
        try:
            subprocess.run(["powershell.exe", "-Command", "echo ok"],
                          capture_output=True, timeout=3)
        except Exception:
            shell_cmd = "cmd.exe"

        self._process = await asyncio.create_subprocess_exec(
            shell_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        self.pid = self._process.pid
        self._reader_task = asyncio.create_task(self._read_loop_windows())
        logger.info(f"Shell {self.shell_id} started (pid={self.pid}, cmd={shell_cmd})")

    async def _read_loop_linux(self):
        loop = asyncio.get_event_loop()
        try:
            while True:
                future = loop.create_future()

                def _on_readable():
                    if not future.done():
                        future.set_result(True)

                loop.add_reader(self.master_fd, _on_readable)
                try:
                    await future
                finally:
                    loop.remove_reader(self.master_fd)

                try:
                    data = os.read(self.master_fd, 16384)
                    if not data:
                        break
                    await self.send({
                        "type": "shell_output",
                        "payload": {"data": data.decode("utf-8", errors="replace")}
                    })
                except OSError:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Shell {self.shell_id} read error: {e}")
        finally:
            logger.info(f"Shell {self.shell_id} read loop ended")
            self._cleanup()
            await self.send({
                "type": "shell_output",
                "payload": {"data": "\r\n[Shell exited. Press Enter to restart.]\r\n"}
            })

    async def _read_loop_windows(self):
        try:
            while True:
                data = await self._process.stdout.read(16384)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                text = text.replace("\n", "\r\n")
                await self.send({
                    "type": "shell_output",
                    "payload": {"data": text}
                })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Shell {self.shell_id} read error: {e}")
        finally:
            logger.info(f"Shell {self.shell_id} read loop ended")
            self._cleanup()
            await self.send({
                "type": "shell_output",
                "payload": {"data": "\r\n[Shell exited. Press Enter to restart.]\r\n"}
            })

    async def write(self, data: str):
        if IS_WINDOWS:
            if self._process and self._process.stdin:
                try:
                    win_data = data.replace("\r", "\r\n") if data == "\r" else data
                    self._process.stdin.write(win_data.encode("utf-8"))
                    await self._process.stdin.drain()
                except (OSError, BrokenPipeError) as e:
                    logger.error(f"Shell {self.shell_id} write error: {e}")
                    self._cleanup()
        else:
            if self.master_fd is not None:
                try:
                    os.write(self.master_fd, data.encode("utf-8"))
                except OSError as e:
                    logger.error(f"Shell {self.shell_id} write error: {e}")
                    self._cleanup()

    def resize(self, cols: int, rows: int):
        if IS_WINDOWS:
            return
        if self.master_fd is not None:
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

    def _cleanup(self):
        if IS_WINDOWS:
            if self._process:
                try:
                    self._process.terminate()
                except Exception:
                    pass
                self._process = None
                self.pid = None
        else:
            if self.pid:
                try:
                    os.kill(self.pid, signal.SIGTERM)
                    os.waitpid(self.pid, os.WNOHANG)
                except (OSError, ChildProcessError):
                    pass
                self.pid = None
            if self.master_fd is not None:
                try:
                    os.close(self.master_fd)
                except OSError:
                    pass
                self.master_fd = None

    def stop(self):
        if self._reader_task:
            self._reader_task.cancel()
        self._cleanup()


class ShellManager:
    def __init__(self, send_callback):
        self._send_raw = send_callback
        self.shells: dict[str, ShellInstance] = {}

    def _make_send(self, shell_id: str):
        async def send(msg: dict):
            if "payload" in msg:
                msg["payload"]["shell_id"] = shell_id
            await self._send_raw(msg)
        return send

    async def create(self, shell_id: str, cols: int = 120, rows: int = 30):
        if shell_id in self.shells:
            return
        instance = ShellInstance(shell_id, self._make_send(shell_id))
        self.shells[shell_id] = instance
        await instance.start(cols, rows)

    async def write(self, shell_id: str, data: str, cols: int = 120, rows: int = 30):
        if shell_id not in self.shells:
            await self.create(shell_id, cols, rows)
        instance = self.shells[shell_id]
        if instance.pid is None:
            await instance.start(cols, rows)
        await instance.write(data)

    def resize(self, shell_id: str, cols: int, rows: int):
        instance = self.shells.get(shell_id)
        if instance:
            instance.resize(cols, rows)

    async def close(self, shell_id: str):
        instance = self.shells.pop(shell_id, None)
        if instance:
            instance.stop()

    def list_shells(self) -> list:
        return [{"id": sid, "alive": inst.pid is not None} for sid, inst in self.shells.items()]

    def stop_all(self):
        for instance in self.shells.values():
            instance.stop()
        self.shells.clear()
