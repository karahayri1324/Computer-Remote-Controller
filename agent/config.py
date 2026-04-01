import os
import yaml
from dataclasses import dataclass, field
@dataclass
class Config:
    relay_url: str = "ws://localhost:3131/ws/agent"
    username: str = ""
    agent_token: str = ""
    heartbeat_interval: int = 15
    reconnect_base_delay: int = 1
    reconnect_max_delay: int = 60
    shell_default_cols: int = 120
    shell_default_rows: int = 30
    allowed_paths: list[str] = field(default_factory=list)
    max_chunk_size: int = 524288
    sysinfo_cache_seconds: int = 2
def load_config(path: str | None = None) -> Config:
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "config.yaml")

    data = {}
    if os.path.exists(path):
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    return Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})
