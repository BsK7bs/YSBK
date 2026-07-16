"""Bridge to legacy collectors.

The modular collectors already live under ``agent/digital_twin_agent/collectors``
and cover CPU, memory, disks, GPU, network, temps, software, USB, printers,
monitors, processes, services, and Windows events. This bridge is imported by
the Telemetry Engine and the Inventory Engine.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("dta.collectors")

_METRICS_CLS: list = []
_INVENTORY_CLS: list = []
_RUN_ALL = None


def _try_import():
    global _METRICS_CLS, _INVENTORY_CLS, _RUN_ALL
    if _METRICS_CLS or _INVENTORY_CLS:
        return True
    for root in ("agent.digital_twin_agent.collectors", "digital_twin_agent.collectors"):
        try:
            module = __import__(root, fromlist=["*"])
            _METRICS_CLS = list(getattr(module, "METRICS_COLLECTORS", []))
            _INVENTORY_CLS = list(getattr(module, "INVENTORY_COLLECTORS", []))
            _RUN_ALL = getattr(module, "run_all", None)
            log.info("loaded collectors from %s (%d metrics + %d inventory)",
                     root, len(_METRICS_CLS), len(_INVENTORY_CLS))
            return True
        except ImportError as exc:
            log.debug("collectors probe %s: %s", root, exc)
    log.warning("legacy collectors unavailable — metrics/inventory will be empty")
    return False


def gather_metrics() -> dict[str, Any]:
    if not _try_import() or not _RUN_ALL:
        return {}
    try:
        return _RUN_ALL([cls() for cls in _METRICS_CLS])
    except Exception as exc:  # noqa: BLE001
        log.exception("metrics collection: %s", exc)
        return {}


def gather_inventory() -> dict[str, Any]:
    if not _try_import() or not _RUN_ALL:
        return {}
    try:
        return _RUN_ALL([cls() for cls in _INVENTORY_CLS])
    except Exception as exc:  # noqa: BLE001
        log.exception("inventory collection: %s", exc)
        return {}
