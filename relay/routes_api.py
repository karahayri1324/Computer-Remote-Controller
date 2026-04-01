from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import create_access_token, check_rate_limit
from connection_manager import manager
from users import register_user, authenticate_user

router = APIRouter(prefix="/api")
class LoginRequest(BaseModel):
    username: str
    password: str
class RegisterRequest(BaseModel):
    username: str
    password: str
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
@router.get("/health")
async def health():
    return {"status": "ok"}
