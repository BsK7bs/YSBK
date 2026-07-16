"""WebSocket client implementation."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

log = logging.getLogger("dta.ws")

OnMessage = Callable[[dict[str, Any]], Awaitable[None]]


class WSClient:
    def __init__(self, ws_url: str, api_key: str, on_message: OnMessage):
        self.ws_url = ws_url
        self.api_key = api_key
        self._on_message = on_message
        self._state = "disconnected"
        self._last_error: str | None = None
        self._connected_at: float | None = None
        self._stop = asyncio.Event()
        self._ws: websockets.WebSocketClientProtocol | None = None

    @property
    def state(self) -> str: return self._state

    @property
    def last_error(self) -> str | None: return self._last_error

    @property
    def connected(self) -> bool: return self._state == "connected"

    async def send_json(self, msg: dict[str, Any]) -> bool:
        if not self._ws or self._state != "connected":
            return False
        try:
            await self._ws.send(json.dumps(msg))
            return True
        except (ConnectionClosed, OSError) as exc:
            log.warning("ws.send failed: %s", exc)
            self._last_error = str(exc)
            return False

    async def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            self._state = "connecting"
            try:
                sep = "&" if "?" in self.ws_url else "?"
                url = f"{self.ws_url}{sep}api_key={self.api_key}"
                log.info("connecting %s", self.ws_url)
                async with websockets.connect(
                    url, ping_interval=25, ping_timeout=15,
                    close_timeout=5, max_size=8 * 1024 * 1024,
                ) as ws:
                    self._ws = ws
                    self._state = "connected"
                    self._connected_at = time.monotonic()
                    self._last_error = None
                    backoff = 1.0
                    log.info("ws connected")
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except (ValueError, TypeError):
                            continue
                        try:
                            await self._on_message(msg)
                        except Exception as exc:  # noqa: BLE001
                            log.exception("on_message: %s", exc)
            except (ConnectionClosed, OSError) as exc:
                self._last_error = str(exc)
                log.warning("ws disconnected: %s (retry in %.1fs)", exc, backoff)
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                log.exception("ws error — backoff %.1fs", backoff)
            finally:
                self._ws = None
                self._state = "disconnected"
                self._connected_at = None
            if self._stop.is_set():
                break
            jitter = random.uniform(0.0, 0.5)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff + jitter)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)

    def stop(self) -> None:
        self._stop.set()
        if self._ws:
            try:
                asyncio.create_task(self._ws.close())
            except RuntimeError:
                pass
