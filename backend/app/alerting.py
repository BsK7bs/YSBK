"""Alert evaluation from telemetry metrics."""
import uuid
from datetime import datetime, timezone
from typing import Any

DEFAULT_THRESHOLDS = {
    "cpu_percent": {"warning": 80.0, "critical": 95.0},
    "ram_percent": {"warning": 85.0, "critical": 95.0},
    "disk_percent": {"warning": 85.0, "critical": 95.0},
    "cpu_temp_c": {"warning": 80.0, "critical": 90.0},
}


def compute_health_score(metrics: dict[str, Any]) -> tuple[int, str]:
    """Return (score 0-100, risk_level)."""
    score = 100.0
    cpu = float(metrics.get("cpu_percent", 0) or 0)
    ram = float(metrics.get("ram_percent", 0) or 0)
    disk = float(metrics.get("disk_percent", 0) or 0)
    temp = float(metrics.get("cpu_temp_c", 0) or 0)

    score -= max(0.0, cpu - 60) * 0.6
    score -= max(0.0, ram - 60) * 0.6
    score -= max(0.0, disk - 70) * 0.8
    if temp:
        score -= max(0.0, temp - 70) * 0.7
    score = max(0.0, min(100.0, score))
    if score >= 85:
        risk = "healthy"
    elif score >= 65:
        risk = "warning"
    elif score >= 45:
        risk = "high_risk"
    else:
        risk = "critical"
    return int(round(score)), risk


def evaluate_alerts(device: dict, metrics: dict[str, Any]) -> list[dict]:
    """Return list of alert docs to insert based on thresholds."""
    now = datetime.now(timezone.utc).isoformat()
    org_id = device["org_id"]
    device_id = device["id"]
    alerts: list[dict] = []

    def add(kind: str, severity: str, value: float, threshold: float, message: str):
        alerts.append({
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "device_id": device_id,
            "kind": kind,
            "severity": severity,
            "message": message,
            "value": float(value),
            "threshold": float(threshold),
            "ts": now,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_at": None,
        })

    for key, thresholds in DEFAULT_THRESHOLDS.items():
        val = metrics.get(key)
        if val is None:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v >= thresholds["critical"]:
            add(f"{key}_critical", "critical", v, thresholds["critical"], f"{key} at {v:.1f} (critical)")
        elif v >= thresholds["warning"]:
            add(f"{key}_high", "warning", v, thresholds["warning"], f"{key} at {v:.1f} (warning)")
    return alerts
