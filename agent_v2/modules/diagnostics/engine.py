from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from ...common.paths import diagnostics_path
from ...common.system_info import get_hostname, get_ip_address, get_mac_address, get_os_info
from ...common.version import AGENT_VERSION, INSTALLER_VERSION, USER_AGENT

log = logging.getLogger("dta.diagnostics")


class DiagnosticsEngine:
    def __init__(self, backend_url: str, credentials, ws, telemetry, watchdog=None,
                 interval: float = 300.0):
        self.backend_url = backend_url.rstrip("/")
        self.credentials = credentials
        self.ws = ws
        self.telemetry = telemetry
        self.watchdog = watchdog
        self.interval = interval
        self.last_error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        os_name, _ = get_os_info()
        snap = {
            "device_id": self.credentials.device_id,
            "device_api_key": self.credentials.device_api_key,
            "installer_version": INSTALLER_VERSION,
            "agent_version": AGENT_VERSION,
            "service_status": "RUNNING",
            "ws_state": self.ws.state,
            "last_heartbeat": None,  # heartbeat lives inside watchdog
            "last_telemetry": self.telemetry.last_sent_iso,
            "last_error": self.ws.last_error or self.last_error,
            "ip_address": get_ip_address(),
            "mac_address": get_mac_address(),
            "os_name": os_name,
            "hostname": get_hostname(),
            "extra": {
                "emitted_at": datetime.now(timezone.utc).isoformat(),
                "frames_sent": getattr(self.telemetry, "frames_sent", None),
                "frames_queued": getattr(self.telemetry, "frames_queued", None),
                "watchdog": self.watchdog.status() if self.watchdog else None,
            },
        }
        return snap

    async def run(self, stop_event: asyncio.Event) -> None:
        first_delay = 10.0
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=first_delay)
                return
            except asyncio.TimeoutError:
                pass
            first_delay = self.interval
            snap = self.snapshot()
            try:
                diagnostics_path().parent.mkdir(parents=True, exist_ok=True)
                sanitised = {k: v for k, v in snap.items() if k != "device_api_key"}
                with diagnostics_path().open("w", encoding="utf-8") as fp:
                    json.dump(sanitised, fp, indent=2)
            except OSError as exc:
                log.warning("diag local write failed: %s", exc)
            try:
                async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as c:
                    r = await c.post(self.backend_url + "/api/agents/diagnostics", json=snap)
                    if r.status_code >= 400:
                        self.last_error = f"diagnostics {r.status_code}: {r.text[:200]}"
                        log.warning(self.last_error)
            except httpx.RequestError as exc:
                self.last_error = str(exc)
                log.warning("diag upload failed: %s", exc)
