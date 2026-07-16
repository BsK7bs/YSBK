from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from .. import offline_queue
from ..collectors_bridge import gather_metrics
from ..ws_client import WSClient

log = logging.getLogger("dta.telemetry")


class TelemetryEngine:
    def __init__(self, ws: WSClient, interval: float = 15.0,
                 alert_engine=None, health_engine=None):
        self.ws = ws
        self.interval = interval
        self.alert_engine = alert_engine
        self.health_engine = health_engine
        self.last_sent: float | None = None
        self.last_sent_iso: str | None = None
        self.frames_sent = 0
        self.frames_queued = 0

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                metrics = await asyncio.get_event_loop().run_in_executor(None, gather_metrics)
            except Exception as exc:  # noqa: BLE001
                log.exception("collectors failed: %s", exc)
                metrics = {}

            # Enrich with client-side health snapshot and alert hints (belt-and-braces).
            enrichment: dict[str, Any] = {}
            if self.health_engine:
                try:
                    enrichment["client_health"] = self.health_engine.score(metrics).__dict__
                except Exception as exc:
                    log.debug("client health scoring failed: %s", exc)
            if self.alert_engine:
                try:
                    hints = self.alert_engine.evaluate(metrics)
                    if hints:
                        enrichment["client_alert_hints"] = [h.__dict__ for h in hints]
                except Exception as exc:
                    log.debug("client alert eval failed: %s", exc)

            frame: dict[str, Any] = {
                "type": "metrics",
                "ts": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics,
            }
            if enrichment:
                frame["enrichment"] = enrichment

            await self._send_or_queue(frame)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def _send_or_queue(self, frame: dict[str, Any]) -> None:
        if self.ws.connected:
            if await self.ws.send_json(frame):
                self.frames_sent += 1
                self.last_sent = time.monotonic()
                self.last_sent_iso = datetime.now(timezone.utc).isoformat()
                await self._drain_backlog()
                return
        offline_queue.enqueue(frame)
        self.frames_queued += 1
        log.info("queued frame offline (depth=%d)", offline_queue.depth())

    async def _drain_backlog(self) -> None:
        drained = 0
        for path, frame in offline_queue.drain():
            if not self.ws.connected:
                break
            if not await self.ws.send_json(frame):
                break
            try:
                path.unlink()
            except OSError:
                pass
            drained += 1
            if drained % 50 == 0:
                await asyncio.sleep(0.05)
        if drained:
            log.info("drained %d queued frames", drained)
