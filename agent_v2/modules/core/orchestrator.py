"""Agent Core — orchestrator with unpaired-idle mode.

The service boots even when no DPAPI credentials exist. It sits in idle mode
and polls the credential store every 30 seconds. Once ``installer.exe`` has
completed pairing (``POST /api/agent/pair``) and written the credential
blob, the orchestrator transparently builds the engines and enters the full
runtime loop.

This matches the product-owner spec: single ``DigitalTwinAgentSetup.exe``
that installs, pairs, and self-verifies before showing the success screen.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Any

from ...common.version import AGENT_VERSION
from ..alerts import AlertEngine
from ..auth import load as load_credentials
from ..diagnostics import DiagnosticsEngine
from ..health import HealthEngine
from ..inventory import InventoryEngine
from ..logmod import configure_agent_logging
from ..prediction import PredictionEngine
from ..remote_actions import RemoteActionExecutor
from ..self_healing import Watchdog
from ..telemetry import TelemetryEngine
from ..ws_client import WSClient
from .config import load_config

log = logging.getLogger("dta.core")


class Orchestrator:
    def __init__(self):
        self.cfg: dict[str, Any] = {}
        self.creds = None
        self.ws: WSClient | None = None
        self.watchdog: Watchdog | None = None
        self.telemetry: TelemetryEngine | None = None
        self.inventory: InventoryEngine | None = None
        self.diagnostics: DiagnosticsEngine | None = None
        self.alerts: AlertEngine | None = None
        self.health: HealthEngine | None = None
        self.prediction: PredictionEngine | None = None
        self.actions: RemoteActionExecutor | None = None
        self._tasks: list[asyncio.Task] = []

    def build(self) -> None:
        self.cfg = load_config()
        self.creds = load_credentials()
        if not self.creds:
            raise RuntimeError("no credentials")
        log.info("agent %s starting (device_id=%s)", AGENT_VERSION, self.creds.device_id)
        self.health = HealthEngine()
        self.prediction = PredictionEngine(window=20)
        self.alerts = AlertEngine()
        self.ws = WSClient(self.creds.ws_url, self.creds.device_api_key, self._on_ws_message)
        self.actions = RemoteActionExecutor(self.ws)
        self.telemetry = TelemetryEngine(
            self.ws, interval=float(self.cfg.get("telemetry_interval", 15)),
            alert_engine=self.alerts, health_engine=self.health,
        )
        self.inventory = InventoryEngine(self.ws, interval=float(self.cfg.get("inventory_interval", 3600)))
        self.watchdog = Watchdog(
            max_silence=float(self.cfg.get("watchdog_max_silence", 120)),
            kill_after=float(self.cfg.get("watchdog_kill_after", 300)),
            on_stall=self._on_stall,
        )
        self.diagnostics = DiagnosticsEngine(
            self.creds.backend_url, self.creds, self.ws, self.telemetry,
            watchdog=self.watchdog,
            interval=float(self.cfg.get("diagnostics_interval", 300)),
        )

    async def run(self, stop_event: asyncio.Event) -> int:
        # ---- Unpaired-idle mode --------------------------------------------
        while load_credentials() is None:
            log.info("agent unpaired — waiting for installer to store credentials (poll every 30s)")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30.0)
                return 0  # stop requested during idle
            except asyncio.TimeoutError:
                continue

        # ---- Full runtime mode ---------------------------------------------
        self.build()
        self.watchdog.register("telemetry")
        self.watchdog.register("inventory")
        self.watchdog.register("diagnostics")
        self.watchdog.register("ws")
        self._tasks = [
            asyncio.create_task(self._beat_loop("ws", self.ws.run()), name="ws"),
            asyncio.create_task(self._beat_loop("telemetry", self.telemetry.run(stop_event)), name="telemetry"),
            asyncio.create_task(self._beat_loop("inventory", self.inventory.run(stop_event)), name="inventory"),
            asyncio.create_task(self._beat_loop("diagnostics", self.diagnostics.run(stop_event)), name="diagnostics"),
            asyncio.create_task(self.watchdog.run(stop_event), name="watchdog"),
        ]
        await stop_event.wait()
        log.info("stop event — shutting down")
        self.ws.stop()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        return 0

    async def _beat_loop(self, name: str, coro):
        async def _pulses():
            while True:
                self.watchdog.beat(name)
                await asyncio.sleep(15)
        pulses = asyncio.create_task(_pulses())
        try:
            await coro
        finally:
            pulses.cancel()
            try:
                await pulses
            except asyncio.CancelledError:
                pass

    async def _on_stall(self, name: str) -> None:
        log.error("stall on '%s' — forcing exit for SCM auto-restart", name)
        import os
        os._exit(64)  # noqa: SLF001

    async def _on_ws_message(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "hello":
            log.info("server hello device_id=%s", msg.get("device_id"))
        elif kind == "action" and self.actions:
            await self.actions.handle(msg)


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent")
    parser.add_argument("--run-service", action="store_true")
    parser.add_argument("--version", action="version", version=AGENT_VERSION)
    args = parser.parse_args()
    configure_agent_logging()
    if args.run_service and sys.platform == "win32":
        from ..service.framework import launch_service
        return launch_service()
    stop = asyncio.Event()
    def _sig(_n, _f): stop.set()
    if sys.platform != "win32":
        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
    orch = Orchestrator()
    try:
        asyncio.run(orch.run(stop))
    except KeyboardInterrupt:
        pass
    return 0
