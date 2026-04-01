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


class ShellManager:
    def __init__(self, send_callback):
        self.send = send_callback
        self.master_fd = None
        self.pid = None
        self._reader_task = None
        # Windows
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
            logger.info(f"Shell started (pid={child_pid})")

    async def _start_windows(self, cols, rows):
        if self._process is not None:
            return

        # Use powershell if available, fallback to cmd
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
        logger.info(f"Shell started (pid={self.pid}, cmd={shell_cmd})")

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
            logger.error(f"Shell read error: {e}")
        finally:
            logger.info("Shell read loop ended")
            self._cleanup()
            await self.send({
                "type": "shell_output",
                "payload": {"data": "\r\n[Shell exited. Will restart on next input.]\r\n"}
            })

    async def _read_loop_windows(self):
        try:
            while True:
                data = await self._process.stdout.read(16384)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                # Normalize line endings for xterm
                text = text.replace("\r\n", "\r\n").replace("\n", "\r\n")
                await self.send({
                    "type": "shell_output",
                    "payload": {"data": text}
                })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Shell read error: {e}")
        finally:
            logger.info("Shell read loop ended")
            self._cleanup()
            await self.send({
                "type": "shell_output",
                "payload": {"data": "\r\n[Shell exited. Will restart on next input.]\r\n"}
            })

    async def write(self, data: str):
        if IS_WINDOWS:
            if self._process and self._process.stdin:
                try:
                    # Convert \r to \r\n for Windows
                    win_data = data.replace("\r", "\r\n") if data == "\r" else data
                    self._process.stdin.write(win_data.encode("utf-8"))
                    await self._process.stdin.drain()
                except (OSError, BrokenPipeError) as e:
                    logger.error(f"Shell write error: {e}")
                    self._cleanup()
        else:
            if self.master_fd is not None:
                try:
                    os.write(self.master_fd, data.encode("utf-8"))
                except OSError as e:
                    logger.error(f"Shell write error: {e}")
                    self._cleanup()

    def resize(self, cols: int, rows: int):
        if IS_WINDOWS:
            return  # Windows subprocess doesn't support resize
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
