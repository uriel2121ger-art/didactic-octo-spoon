from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from pos_core import POSCore
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["reports"])


@router.get("/reports/sales_summary")
def sales_summary(
    date_from: date,
    date_to: date,
    branch_id: int | None = Query(default=None),
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "dashboard"])),
):
    branch = branch_id or core.get_active_branch()
    summary = core.sales_summary(date_from.isoformat(), date_to.isoformat(), branch)
    return summary
