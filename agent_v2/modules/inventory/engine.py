from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from ..collectors_bridge import gather_inventory
from ..ws_client import WSClient

log = logging.getLogger("dta.inventory")


class InventoryEngine:
    def __init__(self, ws: WSClient, interval: float = 3600.0):
        self.ws = ws
        self.interval = interval
        self.last_sent_iso: str | None = None

    async def run(self, stop_event: asyncio.Event) -> None:
        first = True
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5.0 if first else self.interval)
                return
            except asyncio.TimeoutError:
                pass
            first = False
            try:
                inventory = await asyncio.get_event_loop().run_in_executor(None, gather_inventory)
            except Exception as exc:  # noqa: BLE001
                log.exception("inventory collectors failed: %s", exc)
                inventory = {}
            if not inventory:
                continue
            if self.ws.connected:
                ok = await self.ws.send_json({
                    "type": "inventory",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "inventory": inventory,
                })
                if ok:
                    self.last_sent_iso = datetime.now(timezone.utc).isoformat()
                    log.info("inventory sent (%d keys)", len(inventory))
