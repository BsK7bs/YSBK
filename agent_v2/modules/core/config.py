"""Non-sensitive runtime configuration persisted under ProgramData.

Secrets never touch this file — see ``modules.auth`` for DPAPI storage.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ...common.paths import config_path, ensure_data_dirs

log = logging.getLogger("dta.core.config")

_DEFAULTS: dict[str, Any] = {
    "schema": 1,
    "backend_url": None,
    "ws_url": None,
    "log_level": "INFO",
    "telemetry_interval": 15,
    "heartbeat_interval": 30,
    "inventory_interval": 3600,
    "diagnostics_interval": 300,
    "watchdog_max_silence": 120,
    "watchdog_kill_after": 300,
}


def load_config() -> dict[str, Any]:
    p = config_path()
    if not p.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("config unreadable (%s) — using defaults", exc)
        return dict(_DEFAULTS)
    return {**_DEFAULTS, **(data or {})}


def save_config(updates: dict[str, Any]) -> dict[str, Any]:
    ensure_data_dirs()
    cur = load_config()
    cur.update({k: v for k, v in updates.items() if v is not None})
    config_path().write_text(json.dumps(cur, indent=2), encoding="utf-8")
    log.info("config saved: keys=%s", sorted(cur.keys()))
    return cur
