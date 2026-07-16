"""WebSocket manager for device telemetry channels."""
import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks device WebSocket connections and org-scoped subscribers.

    - device_connections: device_id -> WebSocket (agent side, at most one)
    - org_subscribers: org_id -> set[WebSocket] (dashboard viewers)
    """

    def __init__(self) -> None:
        self._device_connections: dict[str, WebSocket] = {}
        self._org_subscribers: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ---- Device (agent) side ----
    async def connect_device(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            existing = self._device_connections.get(device_id)
            if existing is not None:
                try:
                    await existing.close(code=4001)
                except Exception:
                    pass
            self._device_connections[device_id] = websocket

    async def disconnect_device(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            current = self._device_connections.get(device_id)
            if current is websocket:
                self._device_connections.pop(device_id, None)

    async def send_to_device(self, device_id: str, message: dict[str, Any]) -> bool:
        ws = self._device_connections.get(device_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            logger.exception("Failed to send message to device %s", device_id)
            return False

    def is_device_connected(self, device_id: str) -> bool:
        return device_id in self._device_connections

    # ---- Org subscribers (dashboards) ----
    async def subscribe_org(self, org_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._org_subscribers.setdefault(org_id, set()).add(websocket)

    async def unsubscribe_org(self, org_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            subs = self._org_subscribers.get(org_id)
            if subs and websocket in subs:
                subs.discard(websocket)
                if not subs:
                    self._org_subscribers.pop(org_id, None)

    async def broadcast_to_org(self, org_id: str, message: dict[str, Any]) -> None:
        subs = list(self._org_subscribers.get(org_id, set()))
        for ws in subs:
            try:
                await ws.send_json(message)
            except Exception:
                logger.debug("Broadcast failed to a subscriber, will drop")
                await self.unsubscribe_org(org_id, ws)


manager = ConnectionManager()
