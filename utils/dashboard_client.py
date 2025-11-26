from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class DashboardClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get_summary(self) -> dict[str, Any]:
        return self._get("/api/dashboard/summary")

    def get_sales_graph(self) -> dict[str, Any]:
        return self._get("/api/dashboard/graph/sales")

    def get_alerts(self) -> dict[str, Any]:
        return self._get("/api/dashboard/alerts")

    def _get(self, path: str) -> dict[str, Any]:
        try:
            resp = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=8)
            resp.raise_for_status()
            return resp.json()
        except Exception:  # noqa: BLE001
            logger.exception("Dashboard request failed for %s", path)
            return {}
