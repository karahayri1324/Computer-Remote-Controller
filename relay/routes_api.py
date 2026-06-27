from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import (
    create_access_token,
    check_rate_limit, get_current_user,
)
from connection_manager import manager
from users import (
    register_user, authenticate_user, change_password,
    get_2fa_status, setup_totp, enable_totp, disable_totp,
)

router = APIRouter(prefix="/api")


# ─── Models ─────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class Enable2FARequest(BaseModel):
    code: str

class Disable2FARequest(BaseModel):
    password: str


# ─── Auth ───────────────────────────────────────────────────────────

@router.post("/register")
async def register(req: RegisterRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"reg:{client_ip}"):
        return JSONResponse(status_code=429, content={"error": "Too many attempts. Try again later."})

    result = register_user(req.username, req.password)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"error": result["error"]})
    return {"ok": True, "agent_token": result["agent_token"]}


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"login:{client_ip}"):
        return JSONResponse(status_code=429, content={"error": "Too many login attempts. Try again later."})

    username = req.username.strip().lower()

    if not authenticate_user(username, req.password):
        return JSONResponse(status_code=401, content={"error": "Invalid username or password"})

    token = create_access_token(username)
    return {"access_token": token, "token_type": "bearer", "username": username}


# ─── Settings (require auth) ───────────────────────────────────────

@router.post("/change-password")
async def api_change_password(req: ChangePasswordRequest, username: str = Depends(get_current_user)):
    result = change_password(username, req.old_password, req.new_password)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"error": result["error"]})
    return {"ok": True}


@router.get("/2fa/status")
async def api_2fa_status(username: str = Depends(get_current_user)):
    return {"enabled": get_2fa_status(username)}


@router.post("/2fa/setup")
async def api_2fa_setup(username: str = Depends(get_current_user)):
    result = setup_totp(username)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"error": result["error"]})
    return {"secret": result["secret"], "qr_svg": result["qr_svg"]}


@router.post("/2fa/enable")
async def api_2fa_enable(req: Enable2FARequest, username: str = Depends(get_current_user)):
    result = enable_totp(username, req.code)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"error": result["error"]})
    return {"ok": True}


@router.post("/2fa/disable")
async def api_2fa_disable(req: Disable2FARequest, username: str = Depends(get_current_user)):
    result = disable_totp(username, req.password)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"error": result["error"]})
    return {"ok": True}


@router.get("/health")
async def health():
    return {"status": "ok"}
