"""Health Score APIs.

Endpoints (stable contract; engine internals may evolve without breaking):

* ``GET /api/devices/{device_id}/health`` \u2014 current full assessment
* ``GET /api/devices/{device_id}/health/timeline`` \u2014 historical snapshots

Both endpoints are org-scoped and require an authenticated user.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..deps import get_current_user
from ..services.health import assess_device
from ..utils import serialize

router = APIRouter(prefix="/devices", tags=["health"])


RANGE_MINUTES: dict[str, int] = {
    "1h": 60,
    "24h": 24 * 60,
    "7d": 7 * 24 * 60,
    "30d": 30 * 24 * 60,
}


async def _load_context(db, device_id: str, org_id: str) -> dict:
    device = await db.devices.find_one({"id": device_id, "org_id": org_id}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Recent alerts (last 24h)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent_alerts = await db.alerts.find(
        {"device_id": device_id, "org_id": org_id, "ts": {"$gte": since}},
        {"_id": 0},
    ).sort("ts", -1).limit(200).to_list(200)

    # Recent telemetry (last 30 min) \u2014 used by future engines
    telemetry_since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    recent_telemetry = await db.telemetry.find(
        {"device_id": device_id, "org_id": org_id, "ts": {"$gte": telemetry_since}},
        {"_id": 0},
    ).sort("ts", 1).limit(200).to_list(200)

    # Timeline (last 60 points) \u2014 used for trend detection
    timeline = await db.health_timeline.find(
        {"device_id": device_id, "org_id": org_id},
        {"_id": 0, "score": 1, "ts": 1, "tier": 1},
    ).sort("ts", -1).limit(60).to_list(60)
    timeline.reverse()  # ascending order for trend fit

    return {
        "device": device,
        "metrics": device.get("latest_metrics") or {},
        "inventory": device.get("inventory") or {},
        "recent_alerts": recent_alerts,
        "recent_telemetry": recent_telemetry,
        "timeline": timeline,
    }


@router.get("/{device_id}/health")
async def get_device_health(device_id: str, user: dict = Depends(get_current_user)):
    """Compute the current health assessment for a device.

    This is a live recomputation from the latest stored signals so that the
    UI always reflects the latest engine logic (even for cached devices).
    """
    db = get_db()
    ctx = await _load_context(db, device_id, user["org_id"])
    assessment = assess_device(ctx)

    # Snapshot: the freshest stored assessment (if any) for parity checks.
    latest_stored = await db.health_timeline.find_one(
        {"device_id": device_id, "org_id": user["org_id"]},
        {"_id": 0},
        sort=[("ts", -1)],
    )

    payload = assessment.to_public_dict()
    payload["device_id"] = device_id
    payload["is_online"] = bool(ctx["device"].get("is_online"))
    payload["last_seen"] = ctx["device"].get("last_seen")
    payload["latest_stored_ts"] = (latest_stored or {}).get("ts")
    return payload


@router.get("/{device_id}/health/timeline")
async def get_device_health_timeline(
    device_id: str,
    range: Literal["1h", "24h", "7d", "30d"] = Query(default="24h"),
    limit: int = Query(default=500, ge=10, le=5000),
    user: dict = Depends(get_current_user),
):
    """Return stored health snapshots for a time range."""
    db = get_db()
    device = await db.devices.find_one(
        {"id": device_id, "org_id": user["org_id"]}, {"_id": 0, "id": 1}
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    minutes = RANGE_MINUTES[range]
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    cursor = db.health_timeline.find(
        {"device_id": device_id, "org_id": user["org_id"], "ts": {"$gte": since}},
        {
            "_id": 0,
            "ts": 1,
            "score": 1,
            "tier": 1,
            "trend": 1,
            "failure_risk_percent": 1,
            "confidence_percent": 1,
            "data_completeness_percent": 1,
            "engine_version": 1,
        },
    ).sort("ts", 1).limit(limit)
    items = await cursor.to_list(limit)
    return {
        "range": range,
        "since": since,
        "count": len(items),
        "items": [serialize(x) for x in items],
    }
