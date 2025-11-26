"""Basic websocket listener to receive broadcast events from server mode."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Callable, Dict, Optional

import websockets

logger = logging.getLogger(__name__)


class WebsocketClient:
    def __init__(self, url: str, on_event: Optional[Callable[[Dict], None]] = None):
        self.url = url
        self.on_event = on_event
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()

    def _run(self) -> None:
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                async with websockets.connect(self.url) as ws:  # pragma: no cover - network
                    async for message in ws:
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            logger.debug("Ignoring non-JSON message: %s", message)
                            continue
                        if self.on_event:
                            self.on_event(payload)
            except Exception as exc:  # pragma: no cover - network
                logger.warning("Websocket reconnect after error: %s", exc)
                await asyncio.sleep(3)
