"""AI Prediction API.

Endpoints (all org-scoped, JWT-authenticated):

* ``GET /api/devices/{device_id}/predictions``
    Return the current predictions for all six failure types.

* ``GET /api/devices/{device_id}/predictions/{failure_type}``
    Return a single prediction with the full explainability payload.

* ``GET /api/devices/{device_id}/predictions/timeline``
    Historical predictions (default range=24h) — used to plot the trend.

Recomputation is triggered live on each request so the UI always reflects
the freshest signals. Every request also appends a timeline entry so the
history grows organically as users open the page.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..deps import get_current_user
from ..services.prediction import FAILURE_TYPES, predict_device
from ..utils import serialize

router = APIRouter(prefix="/devices", tags=["predictions"])

RANGE_MINUTES: dict[str, int] = {
    "1h": 60,
    "24h": 24 * 60,
    "7d": 7 * 24 * 60,
    "30d": 30 * 24 * 60,
}


async def _load_ctx(db, device_id: str, org_id: str) -> dict:
    device = await db.devices.find_one({"id": device_id, "org_id": org_id}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    telemetry_since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    recent_telemetry = await db.telemetry.find(
        {"device_id": device_id, "org_id": org_id, "ts": {"$gte": telemetry_since}},
        {"_id": 0},
    ).sort("ts", 1).limit(200).to_list(200)
    return {
        "device": device,
        "metrics": device.get("latest_metrics") or {},
        "inventory": device.get("inventory") or {},
        "recent_telemetry": recent_telemetry,
    }


async def _persist_snapshot(db, report_dict: dict, org_id: str) -> None:
    doc = {
        "org_id": org_id,
        "device_id": report_dict["device_id"],
        "ts": report_dict["ts"],
        "engine_version": report_dict["engine_version"],
        "predictions": [
            {
                "failure_type": p["failure_type"],
                "probability_percent": p["probability_percent"],
                "confidence_percent": p["confidence_percent"],
                "severity": p["severity"],
            }
            for p in report_dict["predictions"]
        ],
    }
    await db.predictions_timeline.insert_one(doc)


@router.get("/{device_id}/predictions")
async def get_predictions(device_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    ctx = await _load_ctx(db, device_id, user["org_id"])
    report = predict_device(ctx)
    payload = report.to_public_dict()
    await _persist_snapshot(db, payload, user["org_id"])
    return payload


@router.get("/{device_id}/predictions/timeline")
async def get_predictions_timeline(
    device_id: str,
    range: Literal["1h", "24h", "7d", "30d"] = Query(default="24h"),
    failure_type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=10, le=5000),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    device = await db.devices.find_one(
        {"id": device_id, "org_id": user["org_id"]}, {"_id": 0, "id": 1}
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if failure_type is not None and failure_type not in FAILURE_TYPES:
        raise HTTPException(status_code=400, detail="Unknown failure_type")

    minutes = RANGE_MINUTES[range]
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    docs = await db.predictions_timeline.find(
        {"device_id": device_id, "org_id": user["org_id"], "ts": {"$gte": since}},
        {"_id": 0},
    ).sort("ts", 1).limit(limit).to_list(limit)

    if failure_type:
        items = []
        for d in docs:
            entry = next(
                (p for p in d.get("predictions") or [] if p.get("failure_type") == failure_type),
                None,
            )
            if entry:
                items.append({"ts": d["ts"], **entry})
        return {"range": range, "failure_type": failure_type, "count": len(items),
                "items": [serialize(x) for x in items]}
    return {"range": range, "count": len(docs), "items": [serialize(x) for x in docs]}


@router.get("/{device_id}/predictions/{failure_type}")
async def get_prediction_detail(
    device_id: str,
    failure_type: str,
    user: dict = Depends(get_current_user),
):
    if failure_type not in FAILURE_TYPES:
        raise HTTPException(status_code=400, detail="Unknown failure_type")
    db = get_db()
    ctx = await _load_ctx(db, device_id, user["org_id"])
    report = predict_device(ctx)
    payload = report.to_public_dict()
    entry = next(
        (p for p in payload["predictions"] if p["failure_type"] == failure_type),
        None,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return {"device_id": device_id, "ts": payload["ts"],
            "engine_version": payload["engine_version"], **entry}
