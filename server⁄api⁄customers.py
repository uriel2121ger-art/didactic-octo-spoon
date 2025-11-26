from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from pos_core import POSCore
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["customers"])


@router.get("/customers")
def list_customers(
    q: str | None = Query(default=None),
    limit: int = 100,
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier", "dashboard"])),
):
    if q:
        rows = core.search_customers(q, limit=limit)
    else:
        rows = core.list_customers(limit=limit)
    return {
        "items": [
            {
                "id": r["id"],
                "name": f"{r['first_name']} {r.get('last_name') or ''}".strip(),
                "phone": r["phone"],
                "email": r["email"],
                "credit_limit": r["credit_limit"],
                "credit_balance": r["credit_balance"],
            }
            for r in rows
        ]
    }
