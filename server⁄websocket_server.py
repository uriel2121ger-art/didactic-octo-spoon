"""Lightweight websocket broadcaster for MultiCaja sync."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List

import websockets

logger = logging.getLogger(__name__)


class WebsocketHub:
    def __init__(self):
        self.clients: List[websockets.WebSocketServerProtocol] = []

    async def register(self, websocket: websockets.WebSocketServerProtocol) -> None:
        self.clients.append(websocket)
        logger.info("Websocket client connected (%s total)", len(self.clients))

    async def unregister(self, websocket: websockets.WebSocketServerProtocol) -> None:
        if websocket in self.clients:
            self.clients.remove(websocket)
        logger.info("Websocket client disconnected (%s total)", len(self.clients))

    async def broadcast(self, payload: Dict) -> None:
        if not self.clients:
            return
        message = json.dumps(payload)
        await asyncio.gather(*[client.send(message) for client in self.clients])


hub = WebsocketHub()


def broadcast_event(payload: Dict) -> None:
    """Fire-and-forget broadcast helper for threads outside the event loop."""
    if not hub.clients:
        return
    try:
        asyncio.get_event_loop().create_task(hub.broadcast(payload))
    except RuntimeError:
        # If no loop is running (e.g., different thread) spin up a temp loop
        loop = asyncio.new_event_loop()
        loop.run_until_complete(hub.broadcast(payload))


async def handler(websocket: websockets.WebSocketServerProtocol) -> None:
    await hub.register(websocket)
    try:
        async for _ in websocket:  # pragma: no cover - interactive loop
            pass
    finally:
        await hub.unregister(websocket)


def start_websocket_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = websockets.serve(handler, host, port)
    loop.run_until_complete(server)
    logger.info("Websocket server running on ws://%s:%s", host, port)
    loop.run_forever()
