"""End-to-end enrollment / telemetry pipeline debug router.

Every step of the pipeline emits a structured log line prefixed with
``[enroll-step]`` / ``[ws-step]`` / ``[telemetry-step]``. This router exposes
a snapshot of that pipeline state so operators can answer the question
"my agent installed but nothing shows up on the dashboard — WHERE did the
pipeline break?" without shell access to the backend host.

Endpoints:
  GET /api/debug/enrollment-status                  -> global org overview
  GET /api/debug/enrollment-status?code=XXX         -> per-code drill-down
  GET /api/debug/enrollment-status?hostname=my-pc   -> per-device drill-down
  GET /api/debug/enrollment-status?device_id=xxxxxx -> per-device drill-down
  GET /api/debug/pipeline/logs                      -> in-memory ring buffer
                                                       (last ~500 pipeline log lines)
"""
from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..deps import require_role
from ..utils import serialize, utcnow

logger = logging.getLogger("dta.debug")
router = APIRouter(prefix="/debug", tags=["debug"])


# ---------------------------------------------------------------------------
# In-memory ring buffer of the last ~500 pipeline log lines. Filled by
# ``PipelineTraceHandler`` (attached to the "dta" logger tree by main.py at
# startup) so the debug endpoint can return it verbatim to the operator.
# ---------------------------------------------------------------------------
_TRACE_BUFFER: Deque[dict[str, Any]] = deque(maxlen=500)


def record_trace(step: str, level: str, message: str, **fields: Any) -> None:
    """Append a structured trace record for later retrieval via /debug/pipeline/logs.

    Callers should also emit a normal ``logger.info/warning/error`` line;
    this ring buffer is only for the /debug endpoint (grepping supervisor
    logs is possible for the platform team but useless for a self-service
    operator).
    """
    _TRACE_BUFFER.append({
        "ts": utcnow().isoformat(),
        "step": step,
        "level": level.upper(),
        "message": message,
        **fields,
    })


class PipelineTraceHandler(logging.Handler):
    """Logging handler that pushes ``[enroll-step]`` / ``[ws-step]`` /
    ``[telemetry-step]`` lines into the ring buffer so the /debug endpoint
    can serve them.

    Attached to the root "dta" logger tree (dta.enroll, dta.ws, dta.telemetry)
    at backend startup.
    """
    _INTERESTING_PREFIXES = ("[enroll-step]", "[ws-step]", "[telemetry-step]")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        # Only capture the structured pipeline steps -- avoid flooding the
        # buffer with every incidental log line the app emits.
        if not any(msg.startswith(p) for p in self._INTERESTING_PREFIXES):
            return
        step = msg.split(" ", 1)[0].strip("[]")
        record_trace(step, record.levelname, msg,
                     logger_name=record.name,
                     module=record.module,
                     line=record.lineno)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _dt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _describe_code(code: dict) -> dict:
    """Turn a raw enrollment_code doc into a step-by-step verdict."""
    now = utcnow()
    exp = code.get("expires_at")
    exp_dt: datetime | None = None
    if exp:
        try:
            exp_dt = datetime.fromisoformat(exp)
        except Exception:  # noqa: BLE001
            exp_dt = None
    is_expired = bool(exp_dt and exp_dt < now)
    used = bool(code.get("used"))
    verdict = "unused" if not used else "used"
    if is_expired and not used:
        verdict = "expired"
    return {
        "code": code.get("code"),
        "id": code.get("id"),
        "label": code.get("label"),
        "created_at": _dt(code.get("created_at")),
        "expires_at": _dt(code.get("expires_at")),
        "is_expired": is_expired,
        "used": used,
        "used_at": _dt(code.get("used_at")),
        "used_by_device_id": code.get("used_by_device_id"),
        "verdict": verdict,
    }


def _seconds_ago(v: Any) -> float | None:
    if not v:
        return None
    try:
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return (utcnow() - v).total_seconds()
    except Exception:  # noqa: BLE001
        return None


async def _describe_device(db, device: dict) -> dict:
    """Build a per-step verdict for a device."""
    device_id = device.get("id")
    org_id = device.get("org_id")
    last_seen = device.get("last_seen")
    last_seen_sec = _seconds_ago(last_seen)

    telemetry_count = await db.telemetry.count_documents({"device_id": device_id, "org_id": org_id})
    latest_telemetry = await db.telemetry.find_one(
        {"device_id": device_id, "org_id": org_id},
        {"_id": 0, "ts": 1},
        sort=[("ts", -1)],
    )
    health_count = await db.health_timeline.count_documents({"device_id": device_id, "org_id": org_id})
    alert_count = await db.alerts.count_documents({"device_id": device_id, "org_id": org_id})

    return {
        "device_id": device_id,
        "hostname": device.get("hostname"),
        "org_id": org_id,
        "is_online": device.get("is_online"),
        "last_seen": _dt(last_seen),
        "last_seen_seconds_ago": last_seen_sec,
        "enrolled_at": _dt(device.get("enrolled_at")),
        "health_score": device.get("health_score"),
        "risk_level": device.get("risk_level"),
        "os_name": device.get("os_name"),
        "os_version": device.get("os_version"),
        "agent_version": device.get("agent_version"),
        "telemetry_count": telemetry_count,
        "latest_telemetry_ts": _dt(latest_telemetry.get("ts")) if latest_telemetry else None,
        "health_timeline_count": health_count,
        "alert_count": alert_count,
        "pipeline_step_9_agent_sending_telemetry": telemetry_count > 0,
        "pipeline_step_10_dashboard_visible": (
            telemetry_count > 0 or last_seen_sec is not None
        ),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/enrollment-status")
async def enrollment_status(
    code: str | None = Query(default=None, description="Enrollment code (e.g. AAF-K22N-EM7T)"),
    hostname: str | None = Query(default=None),
    device_id: str | None = Query(default=None),
    actor: dict = Depends(require_role("technician")),
):
    """Return a step-by-step verdict for the enrollment pipeline.

    Steps reported (matches the flow the operator sees in the docs):
      1.  Enrollment code exists in DB
      2.  Enrollment code not yet used
      3.  Enrollment code not expired
      4.  Backend received an /api/enrollment/enroll POST for that code
      5.  Backend created a Device record
      6.  Agent stored credentials (indirect: subsequent WS auth succeeds)
      7.  Agent connected to /api/ws/agent at least once (device.last_seen set)
      8.  Agent is currently connected (is_online=true)
      9.  Agent is sending telemetry (telemetry rows exist for the device)
      10. Dashboard sees the device (device row + last_seen within 5 min)
    """
    db = get_db()
    org_id = actor["org_id"]
    now = utcnow()

    result: dict[str, Any] = {
        "org_id": org_id,
        "server_time": now.isoformat(),
        "filters": {"code": code, "hostname": hostname, "device_id": device_id},
    }

    # ---- 1-3: enrollment code checks --------------------------------------
    code_doc = None
    if code:
        code_doc = await db.enrollment_codes.find_one(
            {"code": code.strip().upper(), "org_id": org_id}, {"_id": 0}
        )
        step_1 = code_doc is not None
        step_2 = bool(code_doc) and not code_doc.get("used")
        step_3 = True
        if code_doc and code_doc.get("expires_at"):
            try:
                step_3 = datetime.fromisoformat(code_doc["expires_at"]) >= now
            except Exception:  # noqa: BLE001
                step_3 = False
        result["step_1_code_exists"] = step_1
        result["step_2_code_unused"] = step_2
        result["step_3_code_not_expired"] = step_3
        if code_doc:
            result["enrollment_code"] = _describe_code(code_doc)

    # ---- 4-10: device + telemetry checks ---------------------------------
    device_query: dict[str, Any] = {"org_id": org_id}
    if device_id:
        device_query["id"] = device_id
    if hostname:
        import re as _re
        device_query["hostname"] = {"$regex": f"^{_re.escape(hostname)}$", "$options": "i"}
    if code and code_doc and code_doc.get("used_by_device_id"):
        device_query["id"] = code_doc["used_by_device_id"]

    devices_cur = db.devices.find(device_query, {"_id": 0}).sort("enrolled_at", -1).limit(20)
    devices = [serialize(d) async for d in devices_cur]
    result["step_4_backend_received_enroll_post"] = len(devices) > 0
    result["step_5_device_record_created"] = len(devices) > 0
    result["devices"] = [await _describe_device(db, d) for d in devices]

    if devices:
        primary = devices[0]
        primary_last_seen_sec = _seconds_ago(primary.get("last_seen"))
        result["step_6_agent_stored_credentials"] = bool(primary.get("last_seen"))
        result["step_7_ws_connection_established"] = bool(primary.get("last_seen"))
        result["step_8_ws_currently_connected"] = bool(primary.get("is_online"))
        # Consider agent "sending telemetry" if any telemetry row was inserted.
        primary_telemetry_ct = await db.telemetry.count_documents(
            {"device_id": primary["id"], "org_id": org_id}
        )
        result["step_9_agent_sending_telemetry"] = primary_telemetry_ct > 0
        # "Dashboard visible" = device has a heartbeat within the offline threshold.
        threshold_s = int(os.environ.get("DEVICE_OFFLINE_THRESHOLD_SECONDS", "180"))
        result["step_10_dashboard_visible"] = (
            primary_last_seen_sec is not None and primary_last_seen_sec <= threshold_s
        )

    # ---- Global org overview (always shown for context) -------------------
    result["org_summary"] = {
        "total_devices": await db.devices.count_documents({"org_id": org_id}),
        "online_devices": await db.devices.count_documents({"org_id": org_id, "is_online": True}),
        "total_enrollment_codes": await db.enrollment_codes.count_documents({"org_id": org_id}),
        "unused_codes": await db.enrollment_codes.count_documents(
            {"org_id": org_id, "used": False}
        ),
        "used_codes": await db.enrollment_codes.count_documents(
            {"org_id": org_id, "used": True}
        ),
        "total_telemetry_points": await db.telemetry.count_documents({"org_id": org_id}),
    }

    # Recent pipeline log lines (helps operators spot the FIRST failing step).
    result["recent_pipeline_events"] = list(_TRACE_BUFFER)[-50:]

    logger.info(
        "[enroll-step] debug.enrollment_status org=%s code=%s hostname=%s device_id=%s "
        "devices_found=%d",
        org_id, code, hostname, device_id, len(devices),
    )
    return result


@router.get("/pipeline/logs")
async def pipeline_logs(
    limit: int = Query(default=200, ge=1, le=500),
    step: str | None = Query(default=None, description="Filter: enroll-step / ws-step / telemetry-step"),
    actor: dict = Depends(require_role("technician")),
):
    """Return the in-memory pipeline trace buffer (last ~500 events)."""
    items = list(_TRACE_BUFFER)
    if step:
        items = [i for i in items if i.get("step") == step]
    return {"count": len(items[-limit:]), "events": items[-limit:]}


@router.post("/pipeline/trace")
async def push_trace(
    payload: dict,
    actor: dict = Depends(require_role("technician")),
):
    """Allow the frontend to push a client-side pipeline note into the trace buffer.

    Useful when the operator wants to bookmark 'here is when I clicked
    Install' in the timeline.
    """
    record_trace(
        step=str(payload.get("step") or "client"),
        level=str(payload.get("level") or "INFO"),
        message=str(payload.get("message") or "(no message)"),
        source="frontend",
        user_id=actor.get("id"),
    )
    return {"ok": True}
