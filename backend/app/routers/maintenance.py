"""Device Maintenance Mode routes.

Maintenance mode temporarily suppresses alerts on a device (or a group of
devices) and marks them with a badge in the UI. It automatically exits
after ``duration_minutes`` elapses, tracked by a background sweep in
``server.py``.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..models import MaintenanceEnableRequest
from ..utils import serialize, utcnow

router = APIRouter(prefix="/devices", tags=["maintenance"])


@router.post("/{device_id}/maintenance/enable")
async def enable_maintenance(
    device_id: str,
    payload: MaintenanceEnableRequest,
    user: dict = Depends(require_role("technician")),
):
    db = get_db()
    device = await db.devices.find_one({"id": device_id, "org_id": user["org_id"]}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    now = utcnow()
    ends = now + timedelta(minutes=payload.duration_minutes)
    await db.devices.update_one(
        {"id": device_id},
        {"$set": {
            "maintenance_mode": True,
            "maintenance_started_at": now.isoformat(),
            "maintenance_ends_at": ends.isoformat(),
            "maintenance_reason": (payload.reason or "").strip() or None,
            "maintenance_suppress_alerts": bool(payload.suppress_alerts),
            "maintenance_started_by": user["id"],
            "maintenance_started_by_email": user.get("email"),
        }},
    )
    # If suppressing alerts, mute open alerts on this device
    if payload.suppress_alerts:
        await db.alerts.update_many(
            {"device_id": device_id, "org_id": user["org_id"], "status": {"$in": ["open", "acknowledged"]}},
            {"$set": {"muted_until": ends.isoformat(), "muted_reason": "maintenance mode"}},
        )
    await audit_log(db, user["org_id"], user, "maintenance.enabled",
                    target=device_id,
                    metadata={"duration_minutes": payload.duration_minutes,
                              "reason": payload.reason,
                              "suppress_alerts": payload.suppress_alerts})
    return {
        "ok": True,
        "device_id": device_id,
        "started_at": now.isoformat(),
        "ends_at": ends.isoformat(),
        "reason": payload.reason,
        "suppress_alerts": payload.suppress_alerts,
    }


@router.post("/{device_id}/maintenance/disable")
async def disable_maintenance(
    device_id: str,
    user: dict = Depends(require_role("technician")),
):
    db = get_db()
    device = await db.devices.find_one({"id": device_id, "org_id": user["org_id"]}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.devices.update_one(
        {"id": device_id},
        {"$set": {
            "maintenance_mode": False,
            "maintenance_ended_at": utcnow().isoformat(),
        }},
    )
    await db.alerts.update_many(
        {"device_id": device_id, "org_id": user["org_id"], "muted_reason": "maintenance mode"},
        {"$unset": {"muted_until": "", "muted_reason": ""}},
    )
    await audit_log(db, user["org_id"], user, "maintenance.disabled",
                    target=device_id, metadata={})
    return {"ok": True, "device_id": device_id}


@router.get("/{device_id}/maintenance")
async def get_maintenance(
    device_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    d = await db.devices.find_one(
        {"id": device_id, "org_id": user["org_id"]},
        {"_id": 0,
         "maintenance_mode": 1, "maintenance_started_at": 1, "maintenance_ends_at": 1,
         "maintenance_reason": 1, "maintenance_suppress_alerts": 1,
         "maintenance_started_by_email": 1},
    )
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    return serialize(d)
