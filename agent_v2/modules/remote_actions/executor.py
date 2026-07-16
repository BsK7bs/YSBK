from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from ..ws_client import WSClient

log = logging.getLogger("dta.actions")


class RemoteActionExecutor:
    def __init__(self, ws: WSClient):
        self.ws = ws

    async def handle(self, msg: dict[str, Any]) -> None:
        action_id = msg.get("action_id") or msg.get("id")
        kind = msg.get("kind") or msg.get("action")
        params = msg.get("params") or {}
        log.info("received action id=%s kind=%s", action_id, kind)
        result: dict[str, Any] = {"kind": kind}
        status = "succeeded"
        error: str | None = None
        try:
            handler = self._HANDLERS.get(kind)
            if not handler:
                raise NotImplementedError(f"unsupported action kind '{kind}'")
            out = await handler(self, params)
            result.update(out or {})
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            log.exception("action %s failed", action_id)

        if self.ws.connected:
            await self.ws.send_json({
                "type": "action_result",
                "action_id": action_id,
                "status": status,
                "result": result,
                "error": error,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })

    # ---- Handlers -------------------------------------------------------
    async def _refresh_inventory(self, params: dict) -> dict:
        from ..collectors_bridge import gather_inventory
        inv = await asyncio.get_event_loop().run_in_executor(None, gather_inventory)
        if self.ws.connected:
            await self.ws.send_json({
                "type": "inventory",
                "ts": datetime.now(timezone.utc).isoformat(),
                "inventory": inv,
            })
        return {"keys": len(inv)}

    async def _collect_diagnostic(self, params: dict) -> dict:
        from ...common.system_info import collect_pair_snapshot
        return {"snapshot": collect_pair_snapshot()}

    async def _restart_agent(self, params: dict) -> dict:
        """Exit the current process; Windows Service Control Manager auto-restarts us."""
        log.warning("restart_agent requested — exiting so SCM restarts us")
        loop = asyncio.get_event_loop()
        loop.call_later(1.0, lambda: os._exit(0))  # noqa: SLF001 — intentional immediate exit
        return {"note": "exiting; SCM will restart"}

    _HANDLERS: dict[str, Any] = {}


RemoteActionExecutor._HANDLERS = {
    "refresh_inventory":  RemoteActionExecutor._refresh_inventory,
    "collect_diagnostic": RemoteActionExecutor._collect_diagnostic,
    "restart_agent":      RemoteActionExecutor._restart_agent,
}
