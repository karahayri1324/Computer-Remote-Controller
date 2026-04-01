from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import (
    verify_password, create_access_token, hash_password,
    check_rate_limit
)
from config import load_config, save_password_hash
from connection_manager import manager

router = APIRouter(prefix="/api")


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"

    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many login attempts. Try again later."}
        )

    cfg = load_config()

    # First-time setup: if no password hash, set it
    if not cfg.password_hash:
        cfg.password_hash = hash_password(req.password)
        save_password_hash(cfg.password_hash)
        token = create_access_token()
        return {"access_token": token, "token_type": "bearer"}

    if not verify_password(req.password, cfg.password_hash):
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid password"}
        )

    token = create_access_token()
    return {"access_token": token, "token_type": "bearer"}


@router.get("/health")
async def health():
    return {"status": "ok", "agent_online": manager.agent_alive}
