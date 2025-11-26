"""Incremental sync helpers for MultiCaja clients."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from pos_core import POSCore

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.utcnow().isoformat()


def get_incremental_payload(core: POSCore, since: str | None = None) -> Dict[str, Any]:
    """Return a lightweight dataset with changes since timestamp.

    This is intentionally small and focuses on products, inventory, sales,
    and customers so client tills can refresh quickly when reconnecting.
    """
    conn = core.connect()
    cur = conn.cursor()
    payload: Dict[str, Any] = {"timestamp": _iso_now()}

    if since:
        cur.execute(
            "SELECT * FROM products WHERE updated_at >= ? ORDER BY updated_at DESC LIMIT 200", (since,)
        )
    else:
        cur.execute("SELECT * FROM products ORDER BY updated_at DESC LIMIT 200")
    payload["products"] = [dict(r) for r in cur.fetchall()]
    payload["catalog_events"] = get_catalog_events_since(core, since)

    if since:
        cur.execute(
            "SELECT * FROM inventory_logs WHERE created_at >= ? ORDER BY created_at DESC LIMIT 400", (since,)
        )
    else:
        cur.execute("SELECT * FROM inventory_logs ORDER BY created_at DESC LIMIT 400")
    payload["inventory_logs"] = [dict(r) for r in cur.fetchall()]
    payload["inventory_events"] = get_inventory_events_since(core, since)

    if since:
        cur.execute("SELECT * FROM sales WHERE ts >= ? ORDER BY ts DESC LIMIT 200", (since,))
    else:
        cur.execute("SELECT * FROM sales ORDER BY ts DESC LIMIT 200")
    payload["sales"] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM customers ORDER BY created_at DESC LIMIT 200")
    payload["customers"] = [dict(r) for r in cur.fetchall()]

    return payload


# ---------------------------------------------------------------------------
def _ensure_catalog_events_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            payload TEXT,
            UNIQUE(event_type, product_id, ts)
        )
        """
    )


def _ensure_inventory_events_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT,
            ts TEXT NOT NULL,
            UNIQUE(event_type, ts, payload)
        )
        """
    )


def record_catalog_event(core: POSCore, event_type: str, product_id: int, payload: dict | None = None) -> None:
    conn = core.connect()
    _ensure_catalog_events_table(conn)
    conn.execute(
        "INSERT INTO catalog_events(event_type, product_id, ts, payload) VALUES(?,?,?,?)",
        (event_type, product_id, _iso_now(), json.dumps(payload or {})),
    )
    conn.commit()


def record_inventory_event(core: POSCore, event_type: str, payload: dict | None = None) -> None:
    conn = core.connect()
    _ensure_inventory_events_table(conn)
    conn.execute(
        "INSERT INTO inventory_events(event_type, payload, ts) VALUES(?,?,?)",
        (event_type, json.dumps(payload or {}), _iso_now()),
    )
    conn.commit()


def get_catalog_events_since(core: POSCore, since: str | None) -> List[dict[str, Any]]:
    conn = core.connect()
    _ensure_catalog_events_table(conn)
    cur = conn.cursor()
    if since:
        cur.execute("SELECT * FROM catalog_events WHERE ts >= ? ORDER BY ts", (since,))
    else:
        cur.execute("SELECT * FROM catalog_events ORDER BY ts DESC LIMIT 200")
    events = []
    for row in cur.fetchall():
        data = dict(row)
        if data.get("payload"):
            try:
                data["payload"] = json.loads(data["payload"])
            except json.JSONDecodeError:
                data["payload"] = None
        events.append(
            {
                "type": data.get("event_type"),
                "product_id": data.get("product_id"),
                "timestamp": data.get("ts"),
                "product": data.get("payload"),
            }
        )
    return events


def get_inventory_events_since(core: POSCore, since: str | None) -> List[dict[str, Any]]:
    conn = core.connect()
    _ensure_inventory_events_table(conn)
    cur = conn.cursor()
    if since:
        cur.execute("SELECT * FROM inventory_events WHERE ts >= ? ORDER BY ts", (since,))
    else:
        cur.execute("SELECT * FROM inventory_events ORDER BY ts DESC LIMIT 200")
    events: list[dict[str, Any]] = []
    for row in cur.fetchall():
        data = dict(row)
        payload = None
        if data.get("payload"):
            try:
                payload = json.loads(data["payload"])
            except json.JSONDecodeError:
                payload = None
        events.append({"type": data.get("event_type"), "payload": payload, "timestamp": data.get("ts")})
    return events


def apply_remote_product_update(core: POSCore, event: dict[str, Any]) -> None:
    """Apply remote catalog events to the local datastore."""

    event_type = event.get("type")
    product_id = event.get("product_id")
    product_payload = event.get("product") or {}
    if not product_id or not event_type:
        return

    existing = core.get_product(product_id)
    if event_type == "product_created":
        if existing:
            core.update_product(product_id, product_payload)
        elif product_payload:
            core.create_product(product_payload)
    elif event_type == "product_updated":
        if existing:
            core.update_product(product_id, product_payload)
        elif product_payload:
            core.create_product(product_payload)
    elif event_type == "product_deleted":
        if existing:
            core.deactivate_product(product_id)


def apply_remote_inventory_event(core: POSCore, event: dict[str, Any]) -> None:
    etype = event.get("type")
    payload = event.get("payload") or {}
    if etype == "adjust":
        pid = payload.get("product_id")
        delta = float(payload.get("delta") or 0)
        branch = payload.get("branch")
        if pid:
            core.update_stock(int(pid), delta, branch_id=branch)
    elif etype == "sale":
        items = payload.get("items") or []
        branch = payload.get("branch")
        for item in items:
            pid = item.get("product_id")
            qty = float(item.get("qty") or 0)
            if not pid or qty <= 0:
                continue
            product = core.get_product(pid)
            sale_type = (product.get("sale_type") or "unit").lower() if product else "unit"
            if sale_type == "kit":
                for comp in core.get_kit_items(pid):
                    comp_qty = qty * float(comp.get("qty", 1))
                    core.update_stock(int(comp.get("product_id")), -comp_qty, branch_id=branch)
            else:
                core.update_stock(pid, -qty, branch_id=branch)
