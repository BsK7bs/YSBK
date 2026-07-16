"""Best-effort system snapshot used during pairing.

Purely additive — the backend accepts every field as optional so failures on
any individual probe never block enrollment.
"""
from __future__ import annotations

import logging
import platform
import socket
import subprocess
import uuid
from typing import Any

log = logging.getLogger("digital_twin.sysinfo")


def _safe(func, default=None):  # noqa: ANN001
    try:
        return func()
    except Exception as exc:  # noqa: BLE001
        log.debug("probe %s failed: %s", func.__name__, exc)
        return default


def get_hostname() -> str:
    return _safe(socket.gethostname, default="unknown-host") or "unknown-host"


def get_ip_address() -> str | None:
    def _probe():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    return _safe(_probe)


def get_mac_address() -> str | None:
    def _probe():
        mac = uuid.getnode()
        return ":".join(f"{(mac >> ele) & 0xff:02x}" for ele in range(40, -1, -8))
    return _safe(_probe)


def get_hardware_id() -> str:
    """Return a stable per-machine identifier used for idempotent re-enroll.

    On Windows we prefer the UUID from ``wmic csproduct get uuid``. On other
    platforms we fall back to ``uuid.getnode()``.
    """
    if platform.system().lower() == "windows":
        def _probe():
            out = subprocess.check_output(
                ["wmic", "csproduct", "get", "uuid"], stderr=subprocess.DEVNULL, timeout=5,
            ).decode(errors="ignore")
            for line in out.splitlines():
                s = line.strip()
                if s and s.lower() != "uuid" and "invalid" not in s.lower():
                    return s
            return None
        v = _safe(_probe)
        if v:
            return v
    return f"node-{uuid.getnode():012x}"


def get_os_info() -> tuple[str, str]:
    system = platform.system()
    if system == "Windows":
        return "Windows", platform.release() + " " + platform.version()
    return system, platform.release()


def collect_pair_snapshot() -> dict[str, Any]:
    os_name, os_version = get_os_info()
    snap: dict[str, Any] = {
        "hostname": get_hostname(),
        "os_name": os_name,
        "os_version": os_version,
        "hardware_id": get_hardware_id(),
        "ip_address": get_ip_address(),
        "mac_address": get_mac_address(),
    }
    try:
        import psutil
        vm = psutil.virtual_memory()
        snap["ram_gb"] = round(vm.total / (1024 ** 3), 2)
        cores = psutil.cpu_count(logical=True) or 0
        snap["cpu"] = f"{platform.processor() or 'unknown'} ({cores} logical)"
        try:
            disk_total = 0
            for p in psutil.disk_partitions(all=False):
                try:
                    disk_total += psutil.disk_usage(p.mountpoint).total
                except Exception:
                    continue
            snap["disk_gb"] = round(disk_total / (1024 ** 3), 2)
        except Exception:
            pass
    except ImportError:
        pass  # psutil optional at pairing time
    return snap
