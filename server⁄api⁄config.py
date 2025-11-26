from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pos_core import POSCore
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["config"])


@router.get("/config")
def get_config(current_user: dict = Depends(auth.require_roles(["admin", "supervisor"]))):
    return core.get_app_config()
