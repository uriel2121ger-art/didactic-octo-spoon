from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pos_core import POSCore
from server import auth as auth_utils

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: dict):
    username = payload.get("username")
    password = payload.get("password")
    user = core.authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = auth_utils.issue_token_for_user(user)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user["id"], "username": username, "role": user["role"]}}


@router.get("/auth/me")
def me(current_user: dict = Depends(auth_utils.get_current_user_from_token)):
    return current_user
