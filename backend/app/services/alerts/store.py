"""MongoDB helpers for alert persistence + lifecycle transitions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .contracts import Alert, AlertEvent, AlertSeverity, SEVERITY_ORDER


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(kind: str, **kw) -> dict:
    return {
        "ts": _now_iso(),
        "kind": kind,
        **{k: v for k, v in kw.items() if v is not None},
    }


OPEN_STATES = {"open", "investigating", "acknowledged", "resolved_awaiting_ack"}


async def find_active(db, org_id: str, device_id: str, rule_key: str,
                     dimension_key: str = "") -> dict | None:
    return await db.alerts.find_one({
        "org_id": org_id,
        "device_id": device_id,
        "rule_key": rule_key,
        "dimension_key": dimension_key,
        "status": {"$in": list(OPEN_STATES)},
    }, {"_id": 0})


async def open_alert(db, *, org_id: str, device_id: str, device_name: str | None,
                     rule_key: str, dimension_key: str, title: str, category: str,
                     severity: AlertSeverity, current_value: Any, threshold: Any,
                     unit: str | None, duration_seconds: int, recommendation: str | None,
                     context: dict) -> tuple[dict, bool]:
    """Open a new alert or bump the existing one for the same key.

    Returns ``(alert_doc, is_new)``.
    """
    now = _now_iso()
    existing = await find_active(db, org_id, device_id, rule_key, dimension_key)
    if existing:
        prev_sev = existing.get("severity")
        events = existing.get("events") or []
        upd: dict[str, Any] = {
            "last_seen_at": now,
            "current_value": current_value,
            "threshold": threshold,
            "unit": unit,
            "duration_seconds": duration_seconds,
            "context": context,
        }
        # Re-open if the condition returned after being cleared.
        if existing.get("status") in ("resolved_awaiting_ack",):
            events.append(_event("updated", from_status=existing.get("status"),
                                 to_status="open", message="Condition returned before ack."))
            upd["status"] = "open"
            upd["condition_cleared_at"] = None
        # Severity change tracking.
        if severity and severity != prev_sev:
            if SEVERITY_ORDER.get(severity, 0) > SEVERITY_ORDER.get(prev_sev or "info", -1):
                events.append(_event("escalated", from_severity=prev_sev, to_severity=severity,
                                     message=f"Escalated to {severity}", value=current_value))
            else:
                events.append(_event("de_escalated", from_severity=prev_sev, to_severity=severity,
                                     message=f"De-escalated to {severity}", value=current_value))
            upd["severity"] = severity
        upd["events"] = events
        upd["occurrence_count"] = int(existing.get("occurrence_count") or 1) + 1
        await db.alerts.update_one({"id": existing["id"]}, {"$set": upd})
        existing.update(upd)
        return existing, False

    # New alert.
    doc = Alert(
        id=str(uuid.uuid4()),
        org_id=org_id,
        device_id=device_id,
        rule_key=rule_key,
        dimension_key=dimension_key,
        title=title,
        category=category,
        severity=severity,
        status="open",
        current_value=current_value,
        threshold=threshold,
        unit=unit,
        duration_seconds=duration_seconds,
        recommendation=recommendation,
        created_at=now,
        first_detected_at=now,
        last_seen_at=now,
        context=dict(context or {}, device_name=device_name),
        events=[AlertEvent(kind="created", message=f"Opened at {severity}", to_severity=severity,
                           to_status="open", value=current_value)],
    ).model_dump()
    # Serialize events datetime -> iso
    for e in doc["events"]:
        if isinstance(e.get("ts"), datetime):
            e["ts"] = e["ts"].astimezone(timezone.utc).isoformat()
    await db.alerts.insert_one(doc)
    return doc, True


async def mark_condition_cleared(db, alert: dict, *,
                                 auto_close: bool) -> dict:
    """Called when the underlying condition has been healthy for the grace window.

    If ``auto_close`` → close the alert immediately (Info/Low/Medium behavior).
    Otherwise → move to ``resolved_awaiting_ack`` (High/Critical behavior).
    """
    now = _now_iso()
    events = alert.get("events") or []
    events.append(_event("condition_cleared", from_status=alert.get("status"),
                         message="Underlying condition returned to normal."))
    updates: dict[str, Any] = {
        "condition_cleared_at": now,
        "events": events,
    }
    if auto_close:
        events.append(_event("closed", from_status=alert.get("status"),
                             to_status="closed",
                             message="Auto-closed after healthy grace window."))
        updates.update({
            "status": "closed",
            "closed_at": now,
            "resolution_method": "auto",
        })
    else:
        updates.update({
            "status": "resolved_awaiting_ack",
            "resolution_method": "auto",
        })
    await db.alerts.update_one({"id": alert["id"]}, {"$set": updates})
    alert.update(updates)
    return alert


async def acknowledge_alert(db, org_id: str, alert_id: str, actor: dict,
                            note: str | None = None) -> dict | None:
    now = _now_iso()
    alert = await db.alerts.find_one({"id": alert_id, "org_id": org_id}, {"_id": 0})
    if not alert:
        return None
    events = alert.get("events") or []
    events.append(_event("acknowledged", actor_id=actor.get("id"),
                         actor_email=actor.get("email"),
                         from_status=alert.get("status"),
                         to_status="acknowledged",
                         message=note or "Acknowledged by user."))
    updates: dict[str, Any] = {
        "acknowledged_by": actor.get("id"),
        "acknowledged_by_email": actor.get("email"),
        "acknowledged_at": now,
        "ack_note": note,
        "events": events,
    }
    # If the alert was awaiting ack, close it now (manual resolution).
    if alert.get("status") == "resolved_awaiting_ack":
        events.append(_event("closed", from_status="resolved_awaiting_ack",
                             to_status="closed",
                             message="Closed after acknowledgement."))
        updates.update({
            "status": "closed",
            "closed_at": now,
            "resolution_method": "manual",
        })
    else:
        updates["status"] = "acknowledged"
    await db.alerts.update_one({"id": alert_id, "org_id": org_id}, {"$set": updates})
    alert.update(updates)
    return alert


async def force_resolve_alert(db, org_id: str, alert_id: str, actor: dict,
                              note: str | None = None) -> dict | None:
    """Manually mark an alert as resolved & closed."""
    now = _now_iso()
    alert = await db.alerts.find_one({"id": alert_id, "org_id": org_id}, {"_id": 0})
    if not alert:
        return None
    events = alert.get("events") or []
    events.append(_event("resolved", actor_id=actor.get("id"),
                         actor_email=actor.get("email"),
                         from_status=alert.get("status"),
                         to_status="closed",
                         message=note or "Manually resolved."))
    updates = {
        "status": "closed",
        "resolution_method": "manual",
        "condition_cleared_at": alert.get("condition_cleared_at") or now,
        "closed_at": now,
        "events": events,
    }
    await db.alerts.update_one({"id": alert_id, "org_id": org_id}, {"$set": updates})
    alert.update(updates)
    return alert


async def close_alert(db, org_id: str, alert_id: str, actor: dict) -> dict | None:
    return await force_resolve_alert(db, org_id, alert_id, actor, note="Closed by user.")


async def add_alert_note(db, org_id: str, alert_id: str, actor: dict, note: str) -> dict | None:
    alert = await db.alerts.find_one({"id": alert_id, "org_id": org_id}, {"_id": 0})
    if not alert:
        return None
    events = alert.get("events") or []
    events.append(_event("note", actor_id=actor.get("id"), actor_email=actor.get("email"), message=note))
    await db.alerts.update_one({"id": alert_id, "org_id": org_id}, {"$set": {"events": events}})
    alert["events"] = events
    return alert


async def get_active_summary(db, org_id: str) -> dict:
    pipeline = [
        {"$match": {"org_id": org_id, "status": {"$in": list(OPEN_STATES)}}},
        {"$group": {"_id": {"severity": "$severity", "status": "$status"}, "n": {"$sum": 1}}},
    ]
    counts_by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    counts_by_status: dict[str, int] = {}
    total = 0
    async for row in db.alerts.aggregate(pipeline):
        sev = row["_id"]["severity"]
        st = row["_id"]["status"]
        n = int(row["n"])
        counts_by_severity[sev] = counts_by_severity.get(sev, 0) + n
        counts_by_status[st] = counts_by_status.get(st, 0) + n
        total += n
    unacked = await db.alerts.count_documents({
        "org_id": org_id,
        "status": {"$in": ["open", "resolved_awaiting_ack"]},
    })
    return {
        "total_active": total,
        "unacknowledged": unacked,
        "by_severity": counts_by_severity,
        "by_status": counts_by_status,
    }
