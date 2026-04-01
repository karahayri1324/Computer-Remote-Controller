import os
import pty
import signal
import struct
import fcntl
import termios
import asyncio
import logging

logger = logging.getLogger(__name__)


class ShellManager:
    def __init__(self, send_callback):
        self.send = send_callback
        self.master_fd = None
        self.pid = None
        self._reader_task = None

    async def start(self, cols=120, rows=30):
        if self.pid is not None:
            return

        master_fd, slave_fd = pty.openpty()
        child_pid = os.fork()

        if child_pid == 0:
            # Child process
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
            os.execvpe("/bin/bash", ["/bin/bash", "--login"], env)
        else:
            # Parent process
            os.close(slave_fd)
            self.master_fd = master_fd
            self.pid = child_pid
            self.resize(cols, rows)

            # Set non-blocking
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self._reader_task = asyncio.create_task(self._read_loop())
            logger.info(f"Shell started (pid={child_pid})")

    async def _read_loop(self):
        loop = asyncio.get_event_loop()
        try:
            while True:
                # Wait for fd to be readable using asyncio
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

    async def write(self, data: str):
        if self.master_fd is not None:
            try:
                os.write(self.master_fd, data.encode("utf-8"))
            except OSError as e:
                logger.error(f"Shell write error: {e}")
                self._cleanup()

    def resize(self, cols: int, rows: int):
        if self.master_fd is not None:
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

    def _cleanup(self):
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
