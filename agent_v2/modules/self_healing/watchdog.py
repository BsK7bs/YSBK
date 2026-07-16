from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger("dta.watchdog")


class Watchdog:
    """Supervises registered loops via a heartbeat table.

    * Each engine calls ``watchdog.beat("name")`` on every iteration.
    * The watchdog polls the table and logs (severity based on silence).
    * On sustained silence > ``kill_after`` seconds it invokes ``on_stall``.
    """

    def __init__(self, max_silence: float = 120.0, kill_after: float = 300.0,
                 on_stall=None):
        self.max_silence = max_silence
        self.kill_after = kill_after
        self.on_stall = on_stall  # callable(name)
        self._beats: dict[str, float] = {}
        self._killed: set[str] = set()

    def register(self, name: str) -> None:
        self._beats[name] = time.monotonic()

    def beat(self, name: str) -> None:
        self._beats[name] = time.monotonic()
        if name in self._killed:
            self._killed.discard(name)

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            name: {"silent_for": round(now - ts, 1), "stalled": (now - ts) > self.max_silence}
            for name, ts in self._beats.items()
        }

    async def run(self, stop_event: asyncio.Event, poll: float = 15.0) -> None:
        while not stop_event.is_set():
            now = time.monotonic()
            for name, ts in list(self._beats.items()):
                silence = now - ts
                if silence > self.kill_after and name not in self._killed:
                    log.error("loop '%s' silent for %.0fs (>%s) — invoking on_stall",
                              name, silence, self.kill_after)
                    self._killed.add(name)
                    if self.on_stall:
                        try:
                            await self.on_stall(name)
                        except Exception as exc:  # noqa: BLE001
                            log.exception("on_stall(%s) failed: %s", name, exc)
                elif silence > self.max_silence:
                    log.warning("loop '%s' silent for %.0fs", name, silence)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll)
            except asyncio.TimeoutError:
                pass
