import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Header, HTTPException

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
def create_2fa_pending_token(username: str) -> str:
    """Short-lived token proving password was correct, but 2FA still needed."""
    cfg = load_config()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "purpose": "2fa_pending",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, cfg.secret_key, algorithm="HS256")
def verify_2fa_pending_token(token: str) -> str | None:
    """Returns username if valid 2FA pending token, else None."""
    cfg = load_config()
    try:
        claims = jwt.decode(token, cfg.secret_key, algorithms=["HS256"])
        if claims.get("purpose") != "2fa_pending":
            return None
        return claims.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
def verify_access_token(token: str) -> dict | None:
    cfg = load_config()
    try:
        return jwt.decode(token, cfg.secret_key, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
async def get_current_user(authorization: str = Header(...)) -> str:
    """FastAPI dependency: extract and verify JWT from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    claims = verify_access_token(authorization[7:])
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return claims["sub"]
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
