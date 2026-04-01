import time
import platform
import subprocess
import shutil

import psutil


class SystemInfo:
    def __init__(self, cache_ttl: int = 2):
        self._cache = None
        self._cache_time = 0
        self.cache_ttl = cache_ttl

    def collect(self) -> dict:
        now = time.time()
        if self._cache and (now - self._cache_time) < self.cache_ttl:
            return self._cache

        mem = psutil.virtual_memory()

        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                })
            except PermissionError:
                pass

        net = psutil.net_io_counters()
        boot = psutil.boot_time()

        battery = None
        try:
            bat = psutil.sensors_battery()
            if bat:
                battery = {
                    "percent": bat.percent,
                    "plugged": bat.power_plugged,
                    "secs_left": bat.secsleft if bat.secsleft != psutil.POWER_TIME_UNLIMITED else None,
                }
        except AttributeError:
            pass

        gpu = self._collect_gpu()

        self._cache = {
            "hostname": platform.node(),
            "platform": f"{platform.system()} {platform.release()}",
            "cpu_percent": psutil.cpu_percent(interval=0, percpu=True),
            "cpu_count": psutil.cpu_count(),
            "mem": {
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "percent": mem.percent,
            },
            "disk": disks,
            "net": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            },
            "uptime": int(now - boot),
            "battery": battery,
            "gpu": gpu,
        }
        self._cache_time = now
        return self._cache

    def _collect_gpu(self) -> list[dict] | None:
        if not shutil.which("nvidia-smi"):
            return None
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,fan.speed,power.draw,power.limit",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None
            gpus = []
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 9:
                    gpus.append({
                        "index": int(parts[0]),
                        "name": parts[1],
                        "gpu_util": self._safe_float(parts[2]),
                        "mem_used": self._safe_float(parts[3]),
                        "mem_total": self._safe_float(parts[4]),
                        "mem_percent": round(self._safe_float(parts[3]) / max(self._safe_float(parts[4]), 1) * 100, 1),
                        "temp": self._safe_float(parts[5]),
                        "fan_speed": self._safe_float(parts[6]),
                        "power_draw": self._safe_float(parts[7]),
                        "power_limit": self._safe_float(parts[8]),
                    })
            return gpus if gpus else None
        except Exception:
            return None

    @staticmethod
    def _safe_float(val: str) -> float:
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0
