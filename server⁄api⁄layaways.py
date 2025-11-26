from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pos_core import POSCore
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["layaways"])


@router.get("/layaways")
def list_layaways(
    branch_id: int | None = None,
    status: str | None = None,
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier", "dashboard"])),
):
    branch = branch_id or core.get_active_branch()
    rows = core.list_layaways(branch_id=branch, status=status)
    return {"items": [dict(row) for row in rows]}


@router.post("/layaways/{layaway_id}/payment")
def add_payment(layaway_id: int, payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier"]))):
    amount = float(payload.get("amount") or 0)
    notes = payload.get("notes")
    user_id = payload.get("user_id")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Monto inválido")
    core.add_layaway_payment(layaway_id, amount, notes=notes, user_id=user_id)
    return {"status": "ok"}
