from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pos_core import POSCore
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["sales"])


@router.post("/sales")
def create_sale(payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier"]))):
    items = payload.get("items") or []
    payment = payload.get("payment") or {}
    branch_id = int(payload.get("branch_id") or core.get_active_branch())
    discount = float(payload.get("discount") or 0.0)
    customer_id = payload.get("customer_id")
    user_id = payload.get("user_id") or current_user.get("id")
    try:
        sale_id = core.create_sale(
            items,
            payment,
            branch_id=branch_id,
            discount=discount,
            customer_id=customer_id,
            user_id=user_id,
        )
    except Exception as exc:  # pragma: no cover - network path
        raise HTTPException(status_code=400, detail=str(exc))
    return {"sale_id": sale_id}
