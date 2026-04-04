import os
import json
import secrets
import logging
import threading
import io

import pyotp
import qrcode
import qrcode.image.svg

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
            "totp_secret": None,
            "totp_enabled": False,
        }
        _save(users)

    logger.info(f"User registered: {username}")
    return {"ok": True, "agent_token": agent_token}


def authenticate_user(username: str, password: str) -> bool:
    username = username.strip().lower()
    with _lock:
        users = _load()
    user = users.get(username)
    if not user:
        return False
    return verify_password(password, user["password_hash"])


def verify_agent_token(username: str, token: str) -> bool:
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


# ─── Password Management ───────────────────────────────────────────

def change_password(username: str, old_password: str, new_password: str) -> dict:
    username = username.strip().lower()
    if len(new_password) < 4:
        return {"ok": False, "error": "Password must be at least 4 characters"}

    with _lock:
        users = _load()
        user = users.get(username)
        if not user:
            return {"ok": False, "error": "User not found"}
        if not verify_password(old_password, user["password_hash"]):
            return {"ok": False, "error": "Current password is incorrect"}
        user["password_hash"] = hash_password(new_password)
        _save(users)

    logger.info(f"Password changed: {username}")
    return {"ok": True}


def force_change_password(username: str, new_password: str) -> dict:
    """Change password without knowing the old one (for CLI admin use)."""
    username = username.strip().lower()
    if len(new_password) < 4:
        return {"ok": False, "error": "Password must be at least 4 characters"}

    with _lock:
        users = _load()
        user = users.get(username)
        if not user:
            return {"ok": False, "error": "User not found"}
        user["password_hash"] = hash_password(new_password)
        _save(users)

    logger.info(f"Password force-changed: {username}")
    return {"ok": True}


# ─── TOTP 2FA ──────────────────────────────────────────────────────

def get_2fa_status(username: str) -> bool:
    username = username.strip().lower()
    with _lock:
        users = _load()
    user = users.get(username)
    if not user:
        return False
    return bool(user.get("totp_enabled"))


def setup_totp(username: str) -> dict:
    """Generate a new TOTP secret. Returns secret + QR code SVG."""
    username = username.strip().lower()
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name="RemoteController")

    # Generate QR code as SVG
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(uri, image_factory=factory)
    buf = io.BytesIO()
    img.save(buf)
    qr_svg = buf.getvalue().decode("utf-8")

    # Store secret (not yet enabled - user must verify first)
    with _lock:
        users = _load()
        user = users.get(username)
        if not user:
            return {"ok": False, "error": "User not found"}
        user["totp_secret"] = secret
        _save(users)

    return {"ok": True, "secret": secret, "uri": uri, "qr_svg": qr_svg}


def enable_totp(username: str, code: str) -> dict:
    """Verify TOTP code and enable 2FA."""
    username = username.strip().lower()
    with _lock:
        users = _load()
        user = users.get(username)
        if not user:
            return {"ok": False, "error": "User not found"}

        secret = user.get("totp_secret")
        if not secret:
            return {"ok": False, "error": "Run setup first"}

        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=12):
            return {"ok": False, "error": "Invalid code. Try again."}

        user["totp_enabled"] = True
        _save(users)

    logger.info(f"2FA enabled: {username}")
    return {"ok": True}


def disable_totp(username: str, password: str) -> dict:
    """Disable 2FA (requires password confirmation)."""
    username = username.strip().lower()
    with _lock:
        users = _load()
        user = users.get(username)
        if not user:
            return {"ok": False, "error": "User not found"}
        if not verify_password(password, user["password_hash"]):
            return {"ok": False, "error": "Incorrect password"}

        user["totp_enabled"] = False
        user["totp_secret"] = None
        _save(users)

    logger.info(f"2FA disabled: {username}")
    return {"ok": True}


def verify_totp(username: str, code: str) -> bool:
    """Verify a TOTP code for login."""
    username = username.strip().lower()
    with _lock:
        users = _load()
    user = users.get(username)
    if not user or not user.get("totp_enabled") or not user.get("totp_secret"):
        return False
    totp = pyotp.TOTP(user["totp_secret"])
    return totp.verify(code, valid_window=12)
