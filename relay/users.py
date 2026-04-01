import os
import json
import secrets
import logging
import threading

from auth import hash_password, verify_password

logger = logging.getLogger(__name__)

_USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
_lock = threading.Lock()
def _load() -> dict:
    if not os.path.exists(_USERS_FILE):
        return {}
    with open(_USERS_FILE) as f:
        return json.load(f)
def _save(data: dict):
    with open(_USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)
def register_user(username: str, password: str) -> dict:
    """Register a new user. Returns {"ok": True, "agent_token": "..."} or {"ok": False, "error": "..."}."""
    username = username.strip().lower()

    if not username or len(username) < 3:
        return {"ok": False, "error": "Username must be at least 3 characters"}
    if not username.isalnum():
        return {"ok": False, "error": "Username must be alphanumeric"}
    if len(password) < 4:
        return {"ok": False, "error": "Password must be at least 4 characters"}

    with _lock:
        users = _load()
        if username in users:
            return {"ok": False, "error": "Username already exists"}

        agent_token = secrets.token_hex(32)
        users[username] = {
            "password_hash": hash_password(password),
            "agent_token": agent_token,
        }
        _save(users)

    logger.info(f"User registered: {username}")
    return {"ok": True, "agent_token": agent_token}
def authenticate_user(username: str, password: str) -> bool:
    """Verify username + password."""
    username = username.strip().lower()
    with _lock:
        users = _load()
    user = users.get(username)
    if not user:
        return False
    return verify_password(password, user["password_hash"])
def verify_agent_token(username: str, token: str) -> bool:
    """Verify an agent's token for a given username."""
    username = username.strip().lower()
    with _lock:
        users = _load()
    user = users.get(username)
    if not user:
        return False
    import hmac
    return hmac.compare_digest(token, user["agent_token"])
def user_exists(username: str) -> bool:
    username = username.strip().lower()
    with _lock:
        users = _load()
    return username in users
