from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from pos_core import POSCore
from server import auth
from server.sync_engine import record_catalog_event
from server.websocket_server import broadcast_event

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["products"])


@router.get("/products")
def list_products(
    q: str | None = Query(default=None),
    limit: int = Query(default=500, le=2000),
    branch_id: int | None = Query(default=None),
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier", "dashboard"])),
):
    """Return full catalog snapshot or filtered search."""

    branch = branch_id or core.get_active_branch()
    items = core.search_products(q or "", limit=limit, branch_id=branch)
    return [
        {
            "id": row["id"],
            "sku": row["sku"],
            "barcode": row.get("barcode"),
            "name": row["name"],
            "price": row["price"],
            "price_wholesale": row.get("price_wholesale"),
            "sale_type": row.get("sale_type"),
            "department": row.get("department"),
            "supplier": row.get("supplier"),
            "inventory_flag": bool(row.get("inventory_flag", 0)),
            "stock": row.get("stock"),
            "reserved": row.get("reserved"),
            "min_stock": row.get("min_stock"),
            "max_stock": row.get("max_stock"),
            "favorite": bool(row.get("is_favorite", row.get("favorite", 0))),
            "updated_at": row.get("updated_at"),
        }
        for row in items
    ]


@router.post("/stock_update")
def stock_update(payload: dict, current_user: dict = Depends(auth.require_roles(["admin", "supervisor"]))):
    sku = payload.get("sku")
    delta = float(payload.get("delta") or 0)
    reason = payload.get("reason") or "API"
    branch_id = int(payload.get("branch_id") or core.get_active_branch())
    product = core.get_product_by_sku_or_barcode(sku)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    core.add_stock(product["id"], delta, branch_id=branch_id, reason=reason)
    return {"status": "ok"}


@router.post("/product/create")
def create_product(
    payload: dict[str, Any],
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor"])),
):
    product_id = core.create_product(payload)
    record_catalog_event(core, "product_created", product_id, payload)
    broadcast_event({"event": "product_created", "product_id": product_id})
    return {"status": "ok", "product_id": product_id}


@router.post("/product/update")
def update_product(
    payload: dict[str, Any],
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor"])),
):
    product_id = payload.get("id")
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id requerido")
    core.update_product(product_id, payload)
    record_catalog_event(core, "product_updated", product_id, payload)
    broadcast_event({"event": "product_updated", "product_id": product_id})
    return {"status": "ok", "product_id": product_id}


@router.post("/product/delete")
def delete_product(
    payload: dict[str, Any],
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor"])),
):
    product_id = payload.get("product_id")
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id requerido")
    try:
        core.delete_product(product_id)
    except Exception:
        core.deactivate_product(product_id)
    record_catalog_event(core, "product_deleted", product_id)
    broadcast_event({"event": "product_deleted", "product_id": product_id})
    return {"status": "ok"}


@router.post("/product/event")
def product_event(
    payload: dict[str, Any],
    current_user: dict = Depends(auth.require_roles(["admin", "supervisor", "cashier"])),
):
    event = payload.get("event")
    product_id = payload.get("product_id")
    if not event or not product_id:
        raise HTTPException(status_code=400, detail="event y product_id requeridos")
    record_catalog_event(core, event, product_id, payload.get("product"))
    broadcast_event({"event": event, "product_id": product_id})
    return {"status": "ok"}
