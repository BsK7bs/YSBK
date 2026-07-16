"""Pairing + verification calls against the Digital Twin backend.

Matches the current backend contract:

    POST /api/agent/pair       -> AgentPairResponse
    GET  /api/devices/{id}     -> device document (used to confirm the
                                  device shows up in the fleet immediately
                                  after pairing).

Legacy ``bootstrap_token`` flow is intentionally NOT supported — the only
credential the installer accepts is a DT-XXXX-YYYY pairing code, either
supplied via ``--code`` or auto-extracted from the installer's own filename.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx

from ...common.system_info import collect_pair_snapshot, get_hostname
from ...common.version import AGENT_VERSION, INSTALLER_VERSION, USER_AGENT

log = logging.getLogger("dta.enrollment.pair")


class PairError(RuntimeError):
    """User-facing failure — the message is shown verbatim in the installer error dialog."""


@dataclass
class DeviceCredentials:
    device_id: str
    access_token: str
    refresh_token: str
    org_id: str
    ws_url: str
    api_url: str
    hostname: str
    heartbeat_interval_sec: int
    telemetry_interval_sec: int

    def save(self, program_data_dir: Path) -> None:
        """Persist device.json + credentials.json under ProgramData/DigitalTwin.

        The running Windows Service picks these up automatically on its next
        heartbeat tick (~10 seconds).
        """
        program_data_dir.mkdir(parents=True, exist_ok=True)
        (program_data_dir / "device.json").write_text(
            json.dumps({
                "device_id": self.device_id,
                "org_id": self.org_id,
                "hostname": self.hostname,
                "api_url": self.api_url,
                "ws_url": self.ws_url,
                "heartbeat_interval_sec": self.heartbeat_interval_sec,
                "telemetry_interval_sec": self.telemetry_interval_sec,
                "installer_version": INSTALLER_VERSION,
                "agent_version": AGENT_VERSION,
            }, indent=2),
            encoding="utf-8",
        )
        # credentials.json — access + refresh tokens. Restricted ACLs come
        # from the ``ensure_data_dirs()`` step in the installer.
        (program_data_dir / "credentials.json").write_text(
            json.dumps({
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
            }, indent=2),
            encoding="utf-8",
        )


def _detail(r: httpx.Response) -> str:
    try:
        j = r.json()
        if isinstance(j, dict) and "detail" in j:
            return str(j["detail"])
    except ValueError:
        pass
    return r.text[:400]


def pair(backend_url: str, pairing_code: str, timeout: float = 20.0) -> DeviceCredentials:
    """Exchange the pairing code for permanent device credentials.

    Raises :class:`PairError` on any failure with a message suitable for
    direct display in the installer error dialog.
    """
    backend_url = backend_url.rstrip("/")
    if not backend_url:
        raise PairError("Backend URL is empty — the installer was built without a target.")

    snap = collect_pair_snapshot()
    hostname = snap.get("hostname") or get_hostname()
    body: dict[str, Any] = {
        "pairing_code": pairing_code,
        "hostname": hostname,
        "os_name": snap.get("os_name"),
        "os_version": snap.get("os_version"),
        "agent_version": AGENT_VERSION,
        "installer_version": INSTALLER_VERSION,
        "hardware_fingerprint": snap.get("hardware_id"),
        "ip_address": snap.get("ip_address"),
        "mac_address": snap.get("mac_address"),
        "cpu": snap.get("cpu"),
        "ram_gb": snap.get("ram_gb"),
        "disk_gb": snap.get("disk_gb"),
    }

    url = f"{backend_url}/api/agent/pair"
    log.info("POST %s hostname=%s code=%s", url, hostname, pairing_code)
    try:
        r = httpx.post(url, json=body, timeout=timeout, headers={"User-Agent": USER_AGENT})
    except httpx.RequestError as exc:
        raise PairError(
            f"Cannot reach backend at {url}. Check the target machine's internet "
            f"connectivity, proxy, and firewall settings.\n\nDetail: {exc}"
        ) from exc

    if r.status_code == 404:
        raise PairError("The pairing code was not recognised by the backend. "
                        "Please download a fresh copy of the installer from the dashboard.")
    if r.status_code == 410:
        raise PairError("This pairing code has already been used or has expired. "
                        "Please download a fresh copy of the installer.")
    if r.status_code >= 400:
        raise PairError(f"Backend rejected pairing ({r.status_code}): {_detail(r)}")

    data = r.json()
    missing = [f for f in ("device_id", "access_token", "refresh_token", "org_id") if not data.get(f)]
    if missing:
        raise PairError(f"Backend response is missing required field(s): {', '.join(missing)}")

    log.info("pair OK device_id=%s org_id=%s", data["device_id"], data["org_id"])
    return DeviceCredentials(
        device_id=data["device_id"],
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        org_id=data["org_id"],
        ws_url=data.get("ws_url", ""),
        api_url=data.get("api_url", backend_url),
        hostname=hostname,
        heartbeat_interval_sec=int(data.get("heartbeat_interval_sec", 30)),
        telemetry_interval_sec=int(data.get("telemetry_interval_sec", 10)),
    )


def verify_online(backend_url: str, device_id: str, access_token: str, timeout: float = 10.0) -> dict:
    """Ask the backend whether the paired device has reported telemetry yet.

    Returns the device snapshot (``id``, ``hostname``, ``status``, ``online``,
    ``last_seen``, ...). Raises :class:`PairError` if the device cannot be
    fetched at all; the caller retries for a limited window before declaring
    the installation failed.
    """
    if not access_token:
        # The installer polls with just the device id via the pair endpoint
        # since we may not have a JWT yet; fall back to public verify.
        return _verify_public(backend_url, device_id, timeout)
    url = f"{backend_url.rstrip('/')}/api/devices/{device_id}"
    r = httpx.get(url, timeout=timeout, headers={
        "Authorization": f"Bearer {access_token}",
        "User-Agent": USER_AGENT,
    })
    if r.status_code == 404:
        raise PairError("Device disappeared from the backend right after pairing "
                        "(possible race with a rapid revoke). Try downloading a fresh installer.")
    if r.status_code >= 400:
        raise PairError(f"Cannot verify device online status ({r.status_code}): {_detail(r)}")
    return r.json()


def _verify_public(backend_url: str, device_id: str, timeout: float) -> dict:
    # Same-shape fallback for callers without a JWT. The dashboard's poll
    # endpoint (``/api/agent/installer/verify?code=...``) is preferred; this
    # is used only when the installer needs a self-contained probe.
    url = f"{backend_url.rstrip('/')}/api/agent/device/{device_id}/status"
    r = httpx.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    if r.status_code >= 400:
        raise PairError(f"Cannot verify device online status ({r.status_code}): {_detail(r)}")
    return r.json()
