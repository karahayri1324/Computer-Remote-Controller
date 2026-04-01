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
def create_access_token(username: str, expires_minutes: int | None = None) -> str:
    cfg = load_config()
    if expires_minutes is None:
        expires_minutes = cfg.token_expiry_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
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
_attempts: dict[str, list[float]] = {}
def check_rate_limit(key: str) -> bool:
    cfg = load_config()
    now = time.time()
    window = 60.0

    if key not in _attempts:
        _attempts[key] = []

    _attempts[key] = [t for t in _attempts[key] if now - t < window]

    if len(_attempts[key]) >= cfg.rate_limit_login:
        return False

    _attempts[key].append(now)
    return True
