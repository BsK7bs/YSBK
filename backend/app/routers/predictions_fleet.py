"""Fleet-level AI Prediction endpoints.

These endpoints aggregate predictions across every device in the caller's
organisation. They are optimised for the Dashboard widget:

* We deliberately skip the per-device `recent_telemetry` query and pass only
  the device's cached `latest_metrics` / `inventory` to the engine — the
  worst-case sklearn call is ~1 ms so 500 devices × 6 failure types stays
  comfortably under a second.
* We return a slim payload (only what the widget needs) so we do not blow up
  websocket / SSR page-loads.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..deps import get_current_user
from ..services.prediction import FAILURE_TYPES, predict_device
from ..services.prediction.engine import FAILURE_LABELS

router = APIRouter(prefix="/predictions", tags=["predictions"])


def _slim_device(dev: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": dev.get("id"),
        "hostname": dev.get("hostname"),
        "display_name": dev.get("display_name"),
        "is_online": dev.get("is_online", False),
        "last_seen": dev.get("last_seen"),
        "health_score": (dev.get("health") or {}).get("score"),
    }


@router.get("/fleet/top-risk")
async def fleet_top_risk(
    limit: int = Query(default=8, ge=1, le=50),
    min_probability: float = Query(default=0.0, ge=0.0, le=100.0),
    failure_type: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Return the top-N devices ranked by highest predicted failure probability.

    Params:
        * ``limit``            max devices to return (default 8)
        * ``min_probability``  drop devices whose worst prediction is below this
        * ``failure_type``     restrict ranking to one specific failure type

    Each entry includes the *worst* prediction (probability, confidence,
    severity, reason, recommendation, failure_type, label) so the widget can
    render without a follow-up request.
    """
    if failure_type is not None and failure_type not in FAILURE_TYPES:
        raise HTTPException(status_code=400, detail="Unknown failure_type")

    db = get_db()
    cursor = db.devices.find({"org_id": user["org_id"]}, {"_id": 0})
    devices = await cursor.to_list(2000)

    items: list[dict[str, Any]] = []
    for dev in devices:
        ctx = {
            "device": dev,
            "metrics": dev.get("latest_metrics") or {},
            "inventory": dev.get("inventory") or {},
            "recent_telemetry": [],
        }
        report = predict_device(ctx)
        preds = report.predictions
        if failure_type:
            preds = [p for p in preds if p.failure_type == failure_type]
        if not preds:
            continue
        worst = max(preds, key=lambda p: p.probability_percent)
        if worst.probability_percent < min_probability:
            continue
        items.append({
            **_slim_device(dev),
            "worst": {
                "failure_type": worst.failure_type,
                "label": FAILURE_LABELS.get(worst.failure_type, worst.failure_type),
                "probability_percent": round(worst.probability_percent, 1),
                "confidence_percent": round(worst.confidence_percent, 1),
                "severity": worst.severity,
                "reason": worst.reason,
                "recommendation": worst.recommendation,
            },
            "top_types": [
                {"failure_type": p.failure_type,
                 "label": FAILURE_LABELS.get(p.failure_type, p.failure_type),
                 "probability_percent": round(p.probability_percent, 1),
                 "severity": p.severity}
                for p in sorted(report.predictions, key=lambda x: -x.probability_percent)[:3]
            ],
        })

    items.sort(key=lambda x: -x["worst"]["probability_percent"])
    items = items[:limit]
    return {
        "count": len(items),
        "total_devices": len(devices),
        "ts": datetime.now(timezone.utc).isoformat(),
        "engine_version": "prediction-v1-hybrid",
        "items": items,
    }
