import hmac
import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from config import load_config

_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def create_access_token(expires_minutes: int | None = None) -> str:
    cfg = load_config()
    if expires_minutes is None:
        expires_minutes = cfg.token_expiry_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "web_user",
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, cfg.secret_key, algorithm="HS256")


def verify_access_token(token: str) -> dict | None:
    cfg = load_config()
    try:
        return jwt.decode(token, cfg.secret_key, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def verify_agent_token(token: str) -> bool:
    cfg = load_config()
    return hmac.compare_digest(token, cfg.agent_token)


# Simple in-memory rate limiter
_login_attempts: dict[str, list[float]] = {}


def check_rate_limit(ip: str) -> bool:
    cfg = load_config()
    now = time.time()
    window = 60.0

    if ip not in _login_attempts:
        _login_attempts[ip] = []

    # Prune old entries
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < window]

    if len(_login_attempts[ip]) >= cfg.rate_limit_login:
        return False

    _login_attempts[ip].append(now)
    return True
