"""Native pywin32 Windows Service registration — SCM APIs only, no NSSM."""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from ...common.paths import SERVICE_DESCRIPTION, SERVICE_DISPLAY_NAME, SERVICE_NAME

log = logging.getLogger("dta.service.registrar")


class ServiceError(Exception):
    pass


def _win32():
    try:
        import win32service           # type: ignore
        import win32serviceutil       # type: ignore
        import pywintypes             # type: ignore
        return win32service, win32serviceutil, pywintypes
    except ImportError as exc:  # noqa: BLE001
        raise ServiceError(
            f"pywin32 not available (Windows only): {exc}"
        ) from exc


def _sc(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sc.exe", *args], capture_output=True, text=True, check=False)


def install(agent_exe: Path, start_type: str = "auto") -> None:
    if not agent_exe.exists():
        raise ServiceError(f"Agent executable not found: {agent_exe}")
    win32service, win32serviceutil, pywintypes = _win32()
    try:
        remove(force=True)
    except ServiceError as exc:
        log.debug("pre-install cleanup: %s", exc)
    try:
        win32serviceutil.InstallService(
            pythonClassString="agent_v2.modules.service.framework.DigitalTwinAgentService",
            serviceName=SERVICE_NAME,
            displayName=SERVICE_DISPLAY_NAME,
            description=SERVICE_DESCRIPTION,
            startType=win32service.SERVICE_AUTO_START,
            exeName=str(agent_exe),
            exeArgs="--run-service",
        )
    except pywintypes.error as exc:
        raise ServiceError(f"Service registration failed: {exc}") from exc
    r = _sc("failure", SERVICE_NAME, "reset=", "86400",
            "actions=", "restart/5000/restart/15000/restart/60000")
    if r.returncode != 0:
        log.warning("sc failure rc=%s stderr=%s", r.returncode, r.stderr)
    if start_type == "delayed-auto":
        _sc("config", SERVICE_NAME, "start=", "delayed-auto")


def start() -> None:
    _, win32serviceutil, pywintypes = _win32()
    try:
        win32serviceutil.StartService(SERVICE_NAME)
    except pywintypes.error as exc:
        raise ServiceError(f"Service start failed: {exc}") from exc


def stop(timeout: float = 30.0) -> None:
    _, win32serviceutil, pywintypes = _win32()
    try:
        win32serviceutil.StopService(SERVICE_NAME)
    except pywintypes.error as exc:
        if getattr(exc, "winerror", None) not in (1062, 1060):
            raise ServiceError(f"Service stop failed: {exc}") from exc


def remove(force: bool = False) -> None:
    _, win32serviceutil, pywintypes = _win32()
    try:
        stop()
    except ServiceError as exc:
        if not force:
            raise
    try:
        win32serviceutil.RemoveService(SERVICE_NAME)
    except pywintypes.error as exc:
        if getattr(exc, "winerror", None) == 1060 and force:
            return
        raise ServiceError(f"Service remove failed: {exc}") from exc


def query_status() -> str:
    try:
        win32service, win32serviceutil, pywintypes = _win32()
    except ServiceError:
        return "UNKNOWN"
    try:
        state = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
    except Exception:
        return "UNKNOWN"
    return {
        win32service.SERVICE_STOPPED: "STOPPED",
        win32service.SERVICE_START_PENDING: "STARTING",
        win32service.SERVICE_STOP_PENDING: "STOPPING",
        win32service.SERVICE_RUNNING: "RUNNING",
        win32service.SERVICE_PAUSED: "PAUSED",
    }.get(state, "UNKNOWN")


def wait_until_running(timeout: float = 30.0, poll_interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if query_status() == "RUNNING":
            return True
        time.sleep(poll_interval)
    return False
