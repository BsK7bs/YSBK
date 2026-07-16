"""Alerts routes (production engine).

Maintains backwards-compat with the old MVP shape for callers that filter
by ``unresolved_only`` and ``kind``, while exposing the new lifecycle
fields (status, severity, occurrence_count, events…).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..services.alerts import (
    acknowledge_alert,
    add_alert_note,
    close_alert,
    force_resolve_alert,
    get_active_summary,
)
from ..services.alerts.notify import broadcast_lifecycle, get_channels, upsert_channels
from ..utils import serialize
from ..websocket_manager import manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


OPEN_STATES = ["open", "investigating", "resolved_awaiting_ack", "acknowledged"]


RANGE_MINUTES = {"1h": 60, "24h": 24 * 60, "7d": 7 * 24 * 60, "30d": 30 * 24 * 60, "all": None}


@router.get("")
async def list_alerts(
    device_id: str | None = None,
    unresolved_only: bool = Query(default=False),
    status: str | None = Query(default=None, description="open|investigating|acknowledged|resolved_awaiting_ack|closed"),
    severity: str | None = Query(default=None, description="critical|high|medium|low|info"),
    rule_key: str | None = None,
    range: str = Query(default="7d"),
    limit: int = Query(default=200, ge=1, le=2000),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    query: dict = {"org_id": user["org_id"]}
    if device_id:
        query["device_id"] = device_id
    if severity:
        query["severity"] = severity
    if rule_key:
        query["rule_key"] = rule_key
    if unresolved_only:
        query["status"] = {"$in": OPEN_STATES}
    elif status:
        query["status"] = status
    minutes = RANGE_MINUTES.get(range)
    if minutes:
        since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        query["last_seen_at"] = {"$gte": since}
    items = await db.alerts.find(query, {"_id": 0}).sort([("last_seen_at", -1)]).limit(limit).to_list(limit)
    return [serialize(x) for x in items]


@router.get("/summary")
async def alerts_summary(user: dict = Depends(get_current_user)):
    db = get_db()
    return await get_active_summary(db, user["org_id"])


@router.get("/{alert_id}")
async def get_alert(alert_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    a = await db.alerts.find_one({"id": alert_id, "org_id": user["org_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    return serialize(a)


class AckBody(BaseModel):
    note: str | None = None


@router.post("/{alert_id}/acknowledge")
async def acknowledge(alert_id: str, body: AckBody | None = None,
                      user: dict = Depends(require_role("technician"))):
    db = get_db()
    a = await acknowledge_alert(db, user["org_id"], alert_id, user, note=(body or AckBody()).note)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    await audit_log(db, user["org_id"], user, "alert.acknowledged", target=alert_id)
    await broadcast_lifecycle(manager, a, "alert.acknowledged")
    return serialize(a)


@router.post("/{alert_id}/ack")
async def acknowledge_compat(alert_id: str, body: AckBody | None = None,
                             user: dict = Depends(require_role("technician"))):
    """Backwards-compat alias."""
    return await acknowledge(alert_id, body, user)


@router.post("/{alert_id}/resolve")
async def resolve(alert_id: str, body: AckBody | None = None,
                  user: dict = Depends(require_role("technician"))):
    db = get_db()
    a = await force_resolve_alert(db, user["org_id"], alert_id, user, note=(body or AckBody()).note)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    await audit_log(db, user["org_id"], user, "alert.resolved", target=alert_id)
    await broadcast_lifecycle(manager, a, "alert.resolved")
    return serialize(a)


@router.post("/{alert_id}/close")
async def close(alert_id: str, user: dict = Depends(require_role("technician"))):
    db = get_db()
    a = await close_alert(db, user["org_id"], alert_id, user)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    await audit_log(db, user["org_id"], user, "alert.closed", target=alert_id)
    await broadcast_lifecycle(manager, a, "alert.closed")
    return serialize(a)


class NoteBody(BaseModel):
    note: str


@router.post("/{alert_id}/note")
async def note(alert_id: str, body: NoteBody,
               user: dict = Depends(require_role("technician"))):
    db = get_db()
    a = await add_alert_note(db, user["org_id"], alert_id, user, body.note)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    return serialize(a)


# ---------------------------------------------------------------------------
# Notification channel configuration (org-level)
# ---------------------------------------------------------------------------

@router.get("/channels/config")
async def get_notification_channels(user: dict = Depends(require_role("admin"))):
    db = get_db()
    doc = await get_channels(db, user["org_id"])
    # Never leak SMTP password in responses.
    if isinstance(doc.get("email"), dict):
        email = dict(doc["email"])
        if "smtp_password" in email:
            email["smtp_password"] = "***" if email["smtp_password"] else ""
        doc["email"] = email
    return doc


class ChannelsBody(BaseModel):
    email: dict | None = None
    slack: dict | None = None
    min_severity: Literal["critical", "high", "medium", "low", "info"] | None = None


@router.put("/channels/config")
async def put_notification_channels(body: ChannelsBody,
                                    user: dict = Depends(require_role("admin"))):
    db = get_db()
    current = await get_channels(db, user["org_id"])
    # Preserve stored SMTP password if the client sent a masked placeholder.
    if body.email is not None and "smtp_password" in body.email:
        if body.email["smtp_password"] in ("***", "", None):
            body.email["smtp_password"] = (current.get("email") or {}).get("smtp_password")
    payload = {
        "email": body.email if body.email is not None else current.get("email") or {"enabled": False},
        "slack": body.slack if body.slack is not None else current.get("slack") or {"enabled": False},
        "min_severity": body.min_severity or current.get("min_severity") or "high",
    }
    doc = await upsert_channels(db, user["org_id"], payload)
    if isinstance(doc.get("email"), dict) and doc["email"].get("smtp_password"):
        doc["email"] = {**doc["email"], "smtp_password": "***"}
    return doc
