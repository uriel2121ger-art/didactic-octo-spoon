from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pos_core import POSCore

core = POSCore()
core.ensure_schema()

security_scheme = HTTPBearer(auto_error=False)


class TokenSettings:
    def __init__(self) -> None:
        cfg = core.get_app_config()
        self.secret_key = os.getenv("POS_SECRET_KEY") or cfg.get("secret_key") or "change-me"
        self.algorithm = "HS256"
        self.expires_minutes = int(cfg.get("token_expires_minutes", 240))


token_settings = TokenSettings()


def create_access_token(payload: dict[str, Any], expires_minutes: int | None = None) -> str:
    expire_minutes = expires_minutes or token_settings.expires_minutes
    to_encode = payload.copy()
    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, token_settings.secret_key, algorithm=token_settings.algorithm)


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, token_settings.secret_key, algorithms=[token_settings.algorithm])
        return payload
    except jwt.PyJWTError:
        return None


def get_current_user_from_token(credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = core.get_user(int(user_id))
    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return {"id": user["id"], "username": user["username"], "role": user["role"], "branch_id": payload.get("branch_id")}


def require_roles(roles: list[str]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    async def dependency(current_user: dict[str, Any] = Depends(get_current_user_from_token)) -> dict[str, Any]:
        if current_user.get("role") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency


def get_current_dashboard_user(current_user: dict[str, Any] = Depends(get_current_user_from_token)) -> dict[str, Any]:
    if current_user.get("role") not in {"dashboard", "admin", "supervisor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes")
    return current_user


def issue_token_for_user(user_row: Any) -> str:
    payload = {
        "sub": user_row["id"],
        "username": user_row["username"],
        "role": user_row["role"],
        "branch_id": core.get_active_branch(),
    }
    return create_access_token(payload)
