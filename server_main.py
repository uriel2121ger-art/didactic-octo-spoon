"""FastAPI entrypoint for MultiCaja server mode with sync endpoints."""
from __future__ import annotations

import logging
import threading
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from pos_core import POSCore
from server import auth as auth_utils
from server.api import auth as auth_routes, cash, config, customers, dashboard, inventory, layaways, products, reports, sales
from server.sync_engine import get_incremental_payload
from server.websocket_server import broadcast_event, start_websocket_server

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="POS Ultra Pro Max API", version="0.3.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
core = POSCore()
core.ensure_schema()
cfg = core.get_app_config()
origins_cfg = str(cfg.get("allowed_origins", "*")).split(",")
allowed = [o.strip() for o in origins_cfg if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in allowed else allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth_routes.router,
    products.router,
    customers.router,
    sales.router,
    inventory.router,
    layaways.router,
    reports.router,
    cash.router,
    config.router,
    dashboard.router,
):
    app.include_router(router, prefix="/api")


@app.get("/api/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def get_config(current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor", "dashboard"]))) -> dict:
    return core.get_app_config()


@app.get("/api/product/{sku}")
def get_product(sku: str, current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor", "cashier", "dashboard"]))) -> dict:
    prod = core.get_product_by_sku_or_barcode(sku)
    return prod or {}


@app.get("/api/branch/{branch_id}/inventory")
def branch_inventory(branch_id: int, current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor", "dashboard"]))) -> dict:
    rows = core.list_inventory(branch_id)
    return {"items": [dict(r) for r in rows]}


@app.post("/api/sale")
def api_sale(payload: dict, current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor", "cashier"]))) -> dict:
    sale_id = core.create_sale(
        payload.get("items", []),
        payload.get("payment", {}),
        branch_id=payload.get("branch_id", 1),
        user_id=payload.get("user_id") or current_user.get("id"),
    )
    threading.Thread(
        target=lambda: broadcast_event({"event": "sale_created", "sale_id": sale_id}),
        daemon=True,
    ).start()
    return {"sale_id": sale_id}


@app.post("/api/layaway")
def api_layaway(payload: dict, current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor", "cashier"]))) -> dict:
    layaway_id = core.create_layaway(
        payload.get("items", []),
        deposit=payload.get("deposit", 0),
        due_date=payload.get("due_date"),
        customer_id=payload.get("customer_id"),
        branch_id=payload.get("branch_id", 1),
        notes=payload.get("notes"),
        user_id=payload.get("user_id") or current_user.get("id"),
    )
    threading.Thread(
        target=lambda: broadcast_event({"event": "layaway_updated", "layaway_id": layaway_id}),
        daemon=True,
    ).start()
    return {"layaway_id": layaway_id}


@app.post("/api/layaway_payment")
def api_layaway_payment(payload: dict, current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor", "cashier"]))) -> dict:
    payment_id = core.add_layaway_payment(
        payload.get("layaway_id"), payload.get("amount", 0), payload.get("notes"), payload.get("user_id") or current_user.get("id")
    )
    threading.Thread(
        target=lambda: broadcast_event({"event": "layaway_updated", "layaway_id": payload.get("layaway_id")}),
        daemon=True,
    ).start()
    return {"payment_id": payment_id}


@app.post("/api/inventory/update")
def api_inventory_update(payload: dict, current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor"]))) -> dict:
    updates = payload.get("changes", [])
    branch_id = payload.get("branch_id", 1)
    for change in updates:
        core.add_stock(change.get("sku"), change.get("delta", 0), branch_id, reason=change.get("reason", "api"))
    threading.Thread(target=lambda: broadcast_event({"event": "inventory_changed"}), daemon=True).start()
    return {"status": "ok", "applied": len(updates)}


@app.get("/api/sync")
def api_sync(since: Optional[str] = Query(None), current_user: dict = Depends(auth_utils.require_roles(["admin", "supervisor", "cashier", "dashboard"]))) -> dict:
    return get_incremental_payload(core, since)


def run_websocket_server() -> None:
    threading.Thread(target=start_websocket_server, daemon=True).start()


def run_api(host: str = "0.0.0.0", port: int = 8000) -> None:
    run_websocket_server()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_api()
