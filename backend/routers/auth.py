"""Authentication endpoints."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import create_access_token, get_current_user, hash_password, verify_password
from backend.config_store import to_dict
from backend.db import create_user, get_user_by_username, init_db, set_user_config

# ensure tables exist on import
init_db()

router = APIRouter()


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@router.post("/register", response_model=AuthResponse)
def register(req: AuthRequest):
    if len(req.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="username too short")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="password too short")
    if get_user_by_username(req.username):
        raise HTTPException(status_code=400, detail="username already exists")
    from backend.db import count_users

    role = "admin" if count_users() == 0 else "user"
    uid = create_user(req.username.strip(), hash_password(req.password), role=role)
    # seed a default config for the new user
    try:
        from backend.config_store import load

        default_cfg = to_dict(load())
    except Exception:
        default_cfg = {}
    set_user_config(uid, default_cfg)
    token = create_access_token(str(uid))
    return AuthResponse(access_token=token, username=req.username.strip())


@router.post("/login", response_model=AuthResponse)
def login(req: AuthRequest):
    user = get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_access_token(str(user["id"]))
    return AuthResponse(access_token=token, username=user["username"])


@router.get("/me")
def me(current_user=Depends(get_current_user)):
    return {"id": current_user["id"], "username": current_user["username"], "role": current_user["role"]}