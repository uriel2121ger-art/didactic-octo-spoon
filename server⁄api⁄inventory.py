from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pos_core import POSCore
from server import sync_engine
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["inventory"])


@router.post("/stock/update")
def update_stock(payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor"]))):
    sku = payload.get("sku")
    delta = float(payload.get("delta") or 0)
    reason = payload.get("reason") or "API ajuste"
    branch_id = int(payload.get("branch_id") or core.get_active_branch())
    product = core.get_product_by_sku_or_barcode(sku)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    core.add_stock(product["id"], delta, branch_id=branch_id, reason=reason)
    sync_engine.record_inventory_event(core, "adjust", {"product_id": product["id"], "delta": delta, "branch": branch_id})
    return {"status": "ok"}


@router.post("/inventory/adjust")
def adjust_inventory(payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor"]))):
    sku = payload.get("sku")
    delta = float(payload.get("delta") or 0)
    branch_id = int(payload.get("branch_id") or core.get_active_branch())
    reason = payload.get("reason") or "API ajuste"
    product = core.get_product_by_sku_or_barcode(sku)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    core.add_stock(product["id"], delta, branch_id=branch_id, reason=reason)
    sync_engine.record_inventory_event(
        core, "adjust", {"product_id": product["id"], "delta": delta, "branch": branch_id, "reason": reason}
    )
    return {"status": "ok"}


@router.post("/inventory/apply_sale")
def apply_sale(payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier"]))):
    items = payload.get("items") or []
    branch_id = int(payload.get("branch_id") or core.get_active_branch())
    for item in items:
        product_id = item.get("product_id")
        qty = float(item.get("qty") or 0)
        if not product_id or qty <= 0:
            continue
        product = core.get_product(product_id)
        if not product:
            continue
        sale_type = (product.get("sale_type") or "unit").lower()
        if sale_type == "kit":
            for comp in core.get_kit_items(product_id):
                comp_qty = qty * float(comp.get("qty", 1))
                core.update_stock(int(comp.get("product_id")), -comp_qty, branch_id=branch_id)
                core._log_inventory(core.connect(), int(comp.get("product_id")), branch_id, -comp_qty, "sale_kit", f"kit:{product_id}")
        else:
            core.update_stock(product_id, -qty, branch_id=branch_id)
            core._log_inventory(core.connect(), product_id, branch_id, -qty, "sale", "sale")
    sync_engine.record_inventory_event(core, "sale", {"items": items, "branch": branch_id})
    return {"status": "ok"}
