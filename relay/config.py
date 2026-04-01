import os
import yaml
from dataclasses import dataclass, field


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 3131
    secret_key: str = ""
    password_hash: str = ""
    agent_token: str = ""
    token_expiry_minutes: int = 1440
    web_root: str = "../web"
    heartbeat_interval: int = 15
    heartbeat_timeout: int = 45
    rate_limit_login: int = 5


_config: Config | None = None


def load_config(path: str | None = None) -> Config:
    global _config
    if _config is not None:
        return _config

    if path is None:
        path = os.path.join(os.path.dirname(__file__), "config.yaml")

    data = {}
    if os.path.exists(path):
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    _config = Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})
    return _config


def save_password_hash(hash_value: str, path: str | None = None):
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "config.yaml")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    data["password_hash"] = hash_value

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
