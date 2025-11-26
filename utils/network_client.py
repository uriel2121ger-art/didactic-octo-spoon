"""Lightweight HTTP client for remote server mode with offline awareness.

This module now contains two helpers:

``NetworkClient``
    Minimal REST wrapper used by the GUI in both server and client modes.

``MultiCajaClient``
    Higher-level helper with offline queues, incremental sync, and cache
    management to satisfy the MultiCaja PRO requirements.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if TYPE_CHECKING:
    from pos_core import POSCore

logger = logging.getLogger(__name__)


class OfflineQueue:
    """Simple JSON-backed queue for offline sales/inventory events."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def append(self, payload: dict[str, Any]) -> None:
        data = self.read_all()
        data.append(payload)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def read_all(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def clear(self) -> None:
        self.path.write_text("[]", encoding="utf-8")


class NetworkClient:
    """Simple REST helper with retry/flags for client mode."""

    def __init__(self, server_url: str, token: str | None = None, cache_dir: Path | str = "data/cache"):
        self.server_url = server_url.rstrip("/")
        self.token = token or "dev-token"
        self.offline_mode = False
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.2))
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {"X-Token": self.token}

    def ping(self) -> bool:
        try:
            resp = self.session.get(f"{self.server_url}/api/ping", timeout=3)
            ok = resp.status_code == 200
            self.offline_mode = not ok
            return ok
        except requests.RequestException:
            self.offline_mode = True
            return False

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.server_url}{path}"
        resp = self.session.get(url, params=params or {}, headers=self._headers(), timeout=5)
        resp.raise_for_status()
        self.offline_mode = False
        return resp.json()

    def post(self, path: str, data: Dict[str, Any]) -> Any:
        url = f"{self.server_url}{path}"
        resp = self.session.post(url, json=data, headers=self._headers(), timeout=5)
        resp.raise_for_status()
        self.offline_mode = False
        return resp.json()

    # ------------------------------------------------------------------
    # Caching helpers
    def cache_write(self, name: str, payload: Any) -> None:
        path = self.cache_dir / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def cache_read(self, name: str, default: Any = None) -> Any:
        path = self.cache_dir / f"{name}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return default
        return default

    # Convenience wrappers ------------------------------------------------
    def fetch_product(self, identifier: str) -> Optional[dict[str, Any]]:
        try:
            data = self.get("/api/products", params={"q": identifier, "limit": 1})
            items = data.get("items", data) if isinstance(data, dict) else data
            if items:
                return items[0]
        except Exception:  # pragma: no cover - offline fallback
            cached = self.cache_read("products", [])
            for item in cached:
                if item.get("sku") == identifier or item.get("barcode") == identifier:
                    return item
        return None

    def fetch_catalog(self) -> list[dict[str, Any]]:
        """Fetch full catalog and persist to cache for offline usage."""

        try:
            data = self.get("/api/products", params={"limit": 2000})
            items = data.get("items", data) if isinstance(data, dict) else data
            self.cache_write("products", items)
            return items
        except Exception:  # pragma: no cover
            logger.warning("Falling back to cached catalog in offline mode")
            return self.cache_read("products", []) or []

    def fetch_products_snapshot(self) -> list[dict[str, Any]]:
        try:
            data = self.get("/api/products", params={"limit": 200})
            items = data.get("items", data) if isinstance(data, dict) else data
            self.cache_write("products", items)
            return items
        except Exception:  # pragma: no cover - offline fallback
            return self.cache_read("products", []) or []


class MultiCajaClient(NetworkClient):
    """High-level client with offline queues and incremental sync."""

    def __init__(
        self,
        server_url: str,
        *,
        token: str | None = None,
        cache_dir: Path | str = "data/cache",
        sales_queue: Path | str = "data/offline_sales_queue.json",
        inventory_queue: Path | str = "data/offline_inventory_queue.json",
    ):
        super().__init__(server_url, token=token, cache_dir=cache_dir)
        self.sales_queue = OfflineQueue(sales_queue)
        self.inventory_queue = OfflineQueue(inventory_queue)

    # High-level helpers -------------------------------------------------
    def ping_server(self) -> bool:
        return self.ping()

    def fetch_inventory(self, branch_id: int) -> list[dict[str, Any]]:
        try:
            data = self.get("/api/branch/{}/inventory".format(branch_id))
            items = data.get("items", data) if isinstance(data, dict) else data
            self.cache_write(f"inventory_{branch_id}", items)
            return items
        except Exception:  # pragma: no cover - offline fallback
            return self.cache_read(f"inventory_{branch_id}", [])

    def post_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.post("/api/sale", payload)
        except Exception:  # pragma: no cover - offline queue
            logger.warning("Queueing sale offline")
            self.sales_queue.append(payload)
            self.offline_mode = True
            return {"queued": True}

    def post_inventory_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.post("/api/inventory/update", payload)
        except Exception:  # pragma: no cover - offline queue
            logger.warning("Queueing inventory change offline")
            self.inventory_queue.append(payload)
            self.offline_mode = True
            return {"queued": True}

    # Catalog sync -------------------------------------------------------
    def send_product_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/api/product/create", payload)

    def send_product_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/api/product/update", payload)

    def send_product_delete(self, product_id: int) -> dict[str, Any]:
        return self.post("/api/product/delete", {"product_id": product_id})

    # Inventory sync -------------------------------------------------
    def send_inventory_adjust(self, sku: str, delta: float, branch_id: int | None = None, reason: str | None = None) -> dict:
        payload = {"sku": sku, "delta": delta}
        if branch_id:
            payload["branch_id"] = branch_id
        if reason:
            payload["reason"] = reason
        return self.post("/api/inventory/adjust", payload)

    def apply_inventory_events(self, events: list[dict[str, Any]], core: "POSCore | None" = None) -> None:
        try:
            from server.sync_engine import apply_remote_inventory_event  # type: ignore
        except Exception:  # pragma: no cover
            apply_remote_inventory_event = None
        if core is None or not apply_remote_inventory_event:
            return
        for ev in events:
            try:
                apply_remote_inventory_event(core, ev)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed applying inventory event: %s", exc)

    def sync_inventory_incremental(self, payload: dict[str, Any], core: "POSCore | None" = None) -> None:
        events = payload.get("inventory_events") if isinstance(payload, dict) else None
        if events:
            self.apply_inventory_events(events, core)

    def apply_catalog_events(self, events: list[dict[str, Any]], core: "POSCore | None" = None) -> None:
        """Apply catalog events to local cache (and DB if core is provided)."""

        try:
            from server.sync_engine import apply_remote_product_update  # type: ignore
        except Exception:  # pragma: no cover
            apply_remote_product_update = None

        cached = self.cache_read("products", []) or []
        by_id = {p.get("id"): p for p in cached if p.get("id")}

        for ev in events:
            etype = ev.get("type")
            pid = ev.get("product_id")
            product = ev.get("product")
            if etype in {"product_created", "product_updated"} and product:
                by_id[pid] = product
            elif etype == "product_deleted" and pid in by_id:
                by_id.pop(pid, None)

            if core is not None and apply_remote_product_update:
                try:
                    apply_remote_product_update(core, ev)
                except Exception as exc:  # pragma: no cover
                    logger.warning("Failed applying catalog event locally: %s", exc)

        self.cache_write("products", list(by_id.values()))

    def sync_catalog_incremental(self, since: str | None = None, core: "POSCore | None" = None) -> dict[str, Any]:
        payload = self.sync_incremental(since)
        events = payload.get("catalog_events", []) if isinstance(payload, dict) else []
        if events:
            self.apply_catalog_events(events, core)
        self.sync_inventory_incremental(payload, core)
        return payload

    def sync_incremental(self, since: str | None = None) -> dict[str, Any]:
        try:
            last_payload = self.cache_read("last_sync", {})
            effective_since = since or last_payload.get("timestamp") or last_payload.get("ts")
            params = {"since": effective_since} if effective_since else {}
            payload = self.get("/api/sync", params=params)
            self.cache_write("last_sync", payload)
            self.offline_mode = False
            return payload
        except Exception:  # pragma: no cover - offline fallback
            self.offline_mode = True
            return {}

    def flush_queue_when_online(self) -> None:
        if self.offline_mode:
            if not self.ping_server():
                return
        # flush sales
        for sale in list(self.sales_queue.read_all()):
            try:
                self.post("/api/sale", sale)
            except Exception:
                logger.warning("Still offline for sale queue")
                return
        self.sales_queue.clear()
        # flush inventory
        for change in list(self.inventory_queue.read_all()):
            try:
                self.post("/api/inventory/update", change)
            except Exception:
                logger.warning("Still offline for inventory queue")
                return
        self.inventory_queue.clear()
