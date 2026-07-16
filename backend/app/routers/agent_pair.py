"""Modern agent-pairing endpoint (Phase 8).

    POST /api/agent/pair       -- exchange a DT-XXXX-XXXX pairing code for
                                  a device_id + JWT access + JWT refresh +
                                  connection URLs + operational intervals +
                                  policy configuration.

    POST /api/agent/refresh    -- exchange a device refresh token for a
                                  fresh access token (call when the agent
                                  detects HTTP 401 or before the current
                                  token expires).

Design goals
------------
* **Pairing code = one-time secret.** Consumed atomically on first successful
  pair; a second attempt with the same code returns HTTP 410.
* **Zero admin secrets on the device.** After pairing succeeds, the agent
  only ever holds `device_id`, `access_token`, `refresh_token`, `org_id`
  and the connection URLs. The pairing code is discarded immediately.
* **Server-controlled intervals & policy.** The response ships the exact
  heartbeat/telemetry cadence and policy config the agent must honour; the
  agent never hard-codes these. That means an operator can throttle a
  noisy machine or turn off remote-command execution without a redeploy.
* **Comprehensive audit log.** Every step of the pair emits a structured
  `[agent-pair]` log line that the /api/debug/pipeline/logs endpoint can
  surface to admins for troubleshooting.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import settings
from ..database import get_db
from ..deps import audit_log
from ..security import (
    create_device_access_token,
    create_device_refresh_token,
    decode_token,
    generate_device_api_key,
    hash_api_key,
)
from ..utils import utcnow

logger = logging.getLogger("dta.agent_pair")

# Public-facing (no JWT dependency — the pairing code IS the credential).
router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class AgentPairPayload(BaseModel):
    """Payload the desktop agent sends the first time it starts on a machine."""

    pairing_code: str = Field(min_length=1, description="The DT-XXXX-XXXX code entered by the operator or read from the installer bootstrap file.")
    hostname: str = Field(min_length=1, description="OS-reported hostname.")
    machine_guid: Optional[str] = Field(default=None, description="Windows: HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid. Linux: /etc/machine-id.")
    os_name: Optional[str] = Field(default=None, description='e.g. "Windows 11 Pro" or "Ubuntu 24.04".')
    os_version: Optional[str] = None
    agent_version: str = Field(default="unknown", description="Semver of the agent binary.")
    device_name: Optional[str] = Field(default=None, description="Friendly display name — falls back to hostname if omitted.")
    hardware_fingerprint: Optional[str] = Field(default=None, description="Stable-per-machine identifier the operator can use to detect chassis swaps. Recommended: SHA-256 of (machine_guid + serial + primary MAC).")
    # Optional inventory hints (all best-effort).
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    cpu: Optional[str] = None
    ram_gb: Optional[float] = None
    disk_gb: Optional[float] = None
    installer_version: Optional[str] = None


class PolicyConfig(BaseModel):
    """Server-side policy the agent must obey."""

    remote_actions_enabled: bool = True
    software_inventory_enabled: bool = True
    speedtest_enabled: bool = True
    max_log_size_mb: int = 25
    log_retention_days: int = 7
    # Backoff schedule (seconds) for auto-reconnect after network drops.
    reconnect_backoff_sec: list[int] = [5, 10, 20, 40, 60]


class AgentPairResponse(BaseModel):
    device_id: str
    device_api_key: str = Field(
        default="",
        description=(
            "Raw WebSocket auth key (also written to DPAPI by install.cmd's "
            "PowerShell bridge — DO NOT log). This is emitted exactly once "
            "in the pair response; the backend only ever stores hash(key) "
            "in devices.api_key_hash and cannot regenerate it."
        ),
    )
    access_token: str
    refresh_token: str
    org_id: str
    ws_url: str
    api_url: str
    heartbeat_interval_sec: int
    telemetry_interval_sec: int
    policy: PolicyConfig
    issued_at: datetime
    access_token_expires_at: datetime


class AgentRefreshPayload(BaseModel):
    refresh_token: str = Field(min_length=1)


class AgentRefreshResponse(BaseModel):
    access_token: str
    access_token_expires_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_backend_url(request: Request) -> str:
    """Reconstruct the backend URL from the request (so multi-tenant ingress
    Just Works)."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("host") or request.url.hostname
    return f"{proto}://{host}".rstrip("/")


def _ws_url(backend_url: str) -> str:
    scheme = "wss" if backend_url.startswith("https") else "ws"
    return f"{scheme}://{backend_url.split('://', 1)[1]}/api/ws/agent"


# ---------------------------------------------------------------------------
# POST /api/agent/pair
# ---------------------------------------------------------------------------
@router.post("/pair", response_model=AgentPairResponse)
async def agent_pair(payload: AgentPairPayload, request: Request):
    client_ip = request.client.host if request.client else "?"
    normalised = payload.pairing_code.strip().upper().replace(" ", "").replace("_", "-")

    logger.info(
        "[agent-pair] step=1_received hostname=%s code_prefix=%s client_ip=%s agent_version=%s",
        payload.hostname, normalised[:7], client_ip, payload.agent_version,
    )
    db = get_db()

    # Step 2: atomic one-time-use lookup. We flip `used=true` in the same
    # update to guarantee that even two concurrent pair attempts with the
    # same code can never both succeed.
    now = utcnow()
    tok = await db.enrollment_codes.find_one_and_update(
        {"code": normalised, "used": False, "expires_at": {"$gte": now.isoformat()}},
        {"$set": {"used": True, "used_at": now.isoformat()}},
        return_document=False,  # return the *pre-update* doc so we can inspect it
        projection={"_id": 0},
    )
    if not tok:
        # Give a specific reason (unknown / expired / already-used).
        stale = await db.enrollment_codes.find_one({"code": normalised}, {"_id": 0})
        if not stale:
            logger.warning("[agent-pair] step=2_lookup verdict=FAIL reason=unknown code=%s client_ip=%s", normalised, client_ip)
            raise HTTPException(status_code=404, detail="Unknown pairing code")
        if stale.get("used"):
            logger.warning("[agent-pair] step=2_lookup verdict=FAIL reason=already_used code=%s", normalised)
            raise HTTPException(status_code=410, detail="Pairing code has already been used")
        if stale.get("expires_at", "") < now.isoformat():
            logger.warning("[agent-pair] step=2_lookup verdict=FAIL reason=expired code=%s", normalised)
            raise HTTPException(status_code=410, detail="Pairing code has expired")
        # Shouldn't reach here, but be defensive.
        raise HTTPException(status_code=410, detail="Pairing code cannot be used")
    logger.info("[agent-pair] step=2_lookup verdict=OK code_id=%s org_id=%s", tok["id"], tok["org_id"])

    # Step 3: org still exists.
    org = await db.organizations.find_one({"id": tok["org_id"]}, {"_id": 0})
    if not org:
        # Roll back the one-time-use flip so a future retry after the org is
        # restored can succeed.
        await db.enrollment_codes.update_one({"id": tok["id"]}, {"$set": {"used": False, "used_at": None}})
        logger.error("[agent-pair] step=3_org verdict=FAIL org_id=%s", tok["org_id"])
        raise HTTPException(status_code=400, detail="Organization no longer exists")

    # Step 4: idempotent re-pair. If a device with the same hardware_fingerprint
    # already exists in this org we replace it rather than accumulate duplicates.
    replace_query: dict[str, Any] = {"org_id": tok["org_id"]}
    fingerprint = payload.hardware_fingerprint or payload.machine_guid
    if fingerprint:
        replace_query["hardware_id"] = fingerprint
    else:
        import re as _re
        replace_query["hostname"] = {
            "$regex": f"^{_re.escape(payload.hostname.strip())}$",
            "$options": "i",
        }
    stale = await db.devices.find_one(replace_query, {"id": 1, "_id": 0})
    if stale:
        stale_id = stale["id"]
        await db.devices.delete_one({"id": stale_id, "org_id": tok["org_id"]})
        await db.telemetry.delete_many({"device_id": stale_id, "org_id": tok["org_id"]})
        await db.alerts.delete_many({"device_id": stale_id, "org_id": tok["org_id"]})
        logger.info("[agent-pair] step=4_reenroll replaced_device=%s", stale_id)
    else:
        logger.info("[agent-pair] step=4_reenroll verdict=NEW_DEVICE")

    # Step 5: create the device record and JWT credentials.
    device_id = uuid.uuid4().hex
    device_display = (payload.device_name or payload.hostname).strip()
    api_key = generate_device_api_key()   # kept for legacy WS auth path
    device_doc = {
        "id": device_id,
        "org_id": tok["org_id"],
        "hostname": payload.hostname.strip(),
        "display_name": device_display,
        "machine_guid": payload.machine_guid,
        "os_name": payload.os_name,
        "os_version": payload.os_version,
        "agent_version": payload.agent_version,
        "hardware_id": fingerprint,
        "hardware_fingerprint": payload.hardware_fingerprint,
        "ip_address": payload.ip_address,
        "mac_address": payload.mac_address,
        "serial_number": payload.serial_number,
        "cpu": payload.cpu,
        "ram_gb": payload.ram_gb,
        "disk_gb": payload.disk_gb,
        "notes": None,
        "tags": [],
        "group_ids": [],
        "managed": True,
        "has_agent": True,
        "created_via": "agent_pair_v3",
        "enrolled_via_pairing_code_id": tok["id"],
        "installer_version": payload.installer_version,
        "api_key_hash": hash_api_key(api_key),
        "is_online": False,
        "last_seen": None,
        "enrolled_at": now.isoformat(),
        "enrolled_by": tok.get("created_by"),
        "latest_metrics": {},
        "inventory": {},
        "health_score": None,
        "risk_level": None,
    }
    await db.devices.insert_one(device_doc)
    logger.info("[agent-pair] step=5_device_created verdict=OK device_id=%s", device_id)

    # Step 6: issue JWTs.
    access_token, access_exp = create_device_access_token(device_id, tok["org_id"])
    refresh_token, refresh_jti, refresh_exp = create_device_refresh_token(device_id, tok["org_id"])
    await db.device_refresh_tokens.insert_one({
        "jti": refresh_jti,
        "device_id": device_id,
        "org_id": tok["org_id"],
        "issued_at": now.isoformat(),
        "expires_at": refresh_exp.isoformat(),
        "revoked": False,
    })
    logger.info("[agent-pair] step=6_jwt_issued verdict=OK jti=%s access_exp=%s", refresh_jti, access_exp.isoformat())

    # Step 7: link consumed pairing code to the device (for audit history).
    await db.enrollment_codes.update_one(
        {"id": tok["id"]},
        {"$set": {"used_by_device_id": device_id}},
    )

    await audit_log(
        db, tok["org_id"], None, "device.paired_via_agent_pair",
        target=device_id,
        metadata={
            "hostname": device_doc["hostname"],
            "device_name": device_display,
            "machine_guid": payload.machine_guid,
            "hardware_fingerprint": payload.hardware_fingerprint,
            "agent_version": payload.agent_version,
            "pairing_code_id": tok["id"],
            "pairing_code_label": tok.get("label"),
        },
    )

    # Step 8: assemble the response.
    backend_url = _resolve_backend_url(request)
    api_url = f"{backend_url}/api"
    ws_url = _ws_url(backend_url)

    response = AgentPairResponse(
        device_id=device_id,
        device_api_key=api_key,  # raw key, only emitted this once
        access_token=access_token,
        refresh_token=refresh_token,
        org_id=tok["org_id"],
        ws_url=ws_url,
        api_url=api_url,
        heartbeat_interval_sec=settings.AGENT_HEARTBEAT_INTERVAL_SEC,
        telemetry_interval_sec=settings.AGENT_TELEMETRY_INTERVAL_SEC,
        policy=PolicyConfig(),
        issued_at=now,
        access_token_expires_at=access_exp,
    )
    logger.info(
        "[agent-pair] step=8_response verdict=OK device_id=%s ws_url=%s api_url=%s",
        device_id, ws_url, api_url,
    )
    return response


# ---------------------------------------------------------------------------
# POST /api/agent/refresh
# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=AgentRefreshResponse)
async def agent_refresh(payload: AgentRefreshPayload):
    """Exchange a device refresh token for a fresh access token.

    The agent should call this proactively when its access token is within
    ~5 minutes of expiry, and reactively whenever the server returns HTTP
    401 with body `{"detail": "token_expired"}`.
    """
    try:
        claims = decode_token(payload.refresh_token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[agent-refresh] verdict=FAIL reason=decode_error exc=%s", exc)
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if claims.get("type") != "device_refresh" or claims.get("kind") != "device":
        raise HTTPException(status_code=401, detail="Wrong token type")

    device_id = claims.get("sub")
    org_id = claims.get("org_id")
    jti = claims.get("jti")
    if not (device_id and org_id and jti):
        raise HTTPException(status_code=401, detail="Malformed refresh token")

    db = get_db()
    row = await db.device_refresh_tokens.find_one({"jti": jti}, {"_id": 0})
    if not row or row.get("revoked"):
        logger.warning("[agent-refresh] verdict=FAIL device_id=%s reason=revoked_or_unknown", device_id)
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    device = await db.devices.find_one({"id": device_id, "org_id": org_id}, {"_id": 0, "id": 1})
    if not device:
        raise HTTPException(status_code=404, detail="Device no longer exists")

    access_token, access_exp = create_device_access_token(device_id, org_id)
    logger.info("[agent-refresh] verdict=OK device_id=%s exp=%s", device_id, access_exp.isoformat())
    return AgentRefreshResponse(
        access_token=access_token,
        access_token_expires_at=access_exp,
    )



# ---------------------------------------------------------------------------
# GET /api/agent/device/{device_id}/status
#
# Public, no-auth device-status probe used by the installer's
# ``_step_verify_online`` fallback path when it doesn't have an access
# token to hand to ``/api/devices/{id}``. Returns just enough info for the
# installer to confirm the device made it into the fleet DB — no secrets,
# no telemetry contents.
#
# Historically this endpoint didn't exist and the installer's polling loop
# would hammer the backend with 404s for ~90 s before failing verify_online
# with a confusing "device never reported telemetry" toast. Adding it as a
# small no-auth probe is safe: the device_id is a random uuid4 hex which
# an attacker cannot guess, and the response contains only status flags.
# ---------------------------------------------------------------------------
@router.get("/device/{device_id}/status")
async def agent_device_status(device_id: str):
    """Return the paired-device visibility snapshot used by the installer."""
    db = get_db()
    device = await db.devices.find_one(
        {"id": device_id},
        {
            "_id": 0,
            "id": 1,
            "org_id": 1,
            "hostname": 1,
            "display_name": 1,
            "is_online": 1,
            "last_seen": 1,
            "agent_version": 1,
            "enrolled_at": 1,
        },
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not paired yet")
    return {
        "id": device["id"],
        "hostname": device.get("hostname"),
        "display_name": device.get("display_name"),
        "online": bool(device.get("is_online")),
        "last_seen": device.get("last_seen"),
        "agent_version": device.get("agent_version"),
        "enrolled_at": device.get("enrolled_at"),
        "status": "online" if device.get("is_online") else "offline",
    }
