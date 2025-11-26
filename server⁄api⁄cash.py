from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pos_core import POSCore
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["cash"])


@router.post("/cash/in")
def cash_in(payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier"]))):
    amount = float(payload.get("amount") or 0)
    reason = payload.get("reason") or "Entrada"
    user_id = payload.get("user_id")
    branch_id = int(payload.get("branch_id") or core.get_active_branch())
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Monto inválido")
    turn = core.get_current_turn(branch_id, user_id)
    turn_id = turn["id"] if turn else None
    core.register_cash_movement(turn_id, "in", amount, reason=reason, branch_id=branch_id, user_id=user_id)
    return {"status": "ok"}


@router.post("/cash/out")
def cash_out(payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier"]))):
    amount = float(payload.get("amount") or 0)
    reason = payload.get("reason") or "Salida"
    user_id = payload.get("user_id")
    branch_id = int(payload.get("branch_id") or core.get_active_branch())
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Monto inválido")
    turn = core.get_current_turn(branch_id, user_id)
    turn_id = turn["id"] if turn else None
    core.register_cash_movement(turn_id, "out", amount, reason=reason, branch_id=branch_id, user_id=user_id)
    return {"status": "ok"}
