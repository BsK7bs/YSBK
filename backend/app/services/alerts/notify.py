"""Notification dispatcher: in-app (WebSocket), Email (SMTP), Slack (webhook).

All channels are best-effort and non-blocking; if credentials are missing or
the remote service errors, we log a warning and never crash the request.
Org-level channel configuration is stored in the ``notification_channels``
collection with shape:

    {
        org_id,
        email: {enabled, smtp_host, smtp_port, smtp_user, smtp_password,
                from_addr, to_addrs: [..], use_tls},
        slack: {enabled, webhook_url, mention: str|None},
        min_severity: "critical|high|medium|low|info",
    }

Credentials are stored as-is (encryption at rest is a separate DB-level
concern). We never log secrets.
"""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from .contracts import SEVERITY_ORDER, AlertSeverity
from .policies import DEFAULT_NOTIFY_MIN_SEVERITY

log = logging.getLogger("alerts.notify")


def _should_notify(severity: AlertSeverity, min_sev: str) -> bool:
    return SEVERITY_ORDER.get(severity, -1) >= SEVERITY_ORDER.get(min_sev, 0)


async def get_channels(db, org_id: str) -> dict[str, Any]:
    doc = await db.notification_channels.find_one({"org_id": org_id}, {"_id": 0})
    return doc or {"org_id": org_id, "email": {"enabled": False}, "slack": {"enabled": False},
                   "min_severity": DEFAULT_NOTIFY_MIN_SEVERITY}


async def upsert_channels(db, org_id: str, payload: dict) -> dict:
    payload = dict(payload)
    payload["org_id"] = org_id
    await db.notification_channels.update_one(
        {"org_id": org_id}, {"$set": payload}, upsert=True
    )
    return payload


async def dispatch_alert(db, alert: dict, manager) -> None:
    """Send an alert through configured channels.

    ``manager`` is the app-level WebSocket ConnectionManager used for the
    in-app notification broadcast. Email/Slack are best-effort and never
    raise.
    """
    org_id = alert.get("org_id")
    severity: AlertSeverity = alert.get("severity", "info")
    channels = await get_channels(db, org_id)
    min_sev = channels.get("min_severity") or DEFAULT_NOTIFY_MIN_SEVERITY

    delivered: list[str] = []

    # 1. In-app is always broadcast via WS (frontend decides how loud to be).
    try:
        await manager.broadcast_to_org(org_id, {
            "type": "alert.opened" if alert.get("occurrence_count", 1) == 1 else "alert.updated",
            "alert": alert,
        })
        delivered.append("in_app")
    except Exception as exc:
        log.warning("in-app alert broadcast failed: %s", exc)

    # 2. Email + Slack only for severities >= min threshold.
    if _should_notify(severity, min_sev):
        email_cfg = channels.get("email") or {}
        if email_cfg.get("enabled") and email_cfg.get("smtp_host"):
            try:
                _send_email(email_cfg, alert)
                delivered.append("email")
            except Exception as exc:
                log.warning("email notification failed: %s", exc)
        slack_cfg = channels.get("slack") or {}
        if slack_cfg.get("enabled") and slack_cfg.get("webhook_url"):
            try:
                await _post_slack(slack_cfg, alert)
                delivered.append("slack")
            except Exception as exc:
                log.warning("slack notification failed: %s", exc)

    if delivered:
        await db.alerts.update_one({"id": alert["id"]}, {
            "$set": {"last_notified_severity": severity},
            "$addToSet": {"notified_channels": {"$each": delivered}},
        })


def _send_email(cfg: dict[str, Any], alert: dict) -> None:
    to_addrs = cfg.get("to_addrs") or []
    if not to_addrs:
        return
    subject = f"[{alert.get('severity','?').upper()}] {alert.get('title','Alert')}"
    body_lines = [
        f"Severity: {alert.get('severity')}",
        f"Device:   {(alert.get('context') or {}).get('device_name') or alert.get('device_id')}",
        f"Rule:     {alert.get('rule_key')}",
        f"Current:  {alert.get('current_value')}",
        f"Threshold: {alert.get('threshold')}",
        f"When:     {alert.get('last_seen_at')}",
        "",
        alert.get("recommendation") or "",
    ]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_addr") or cfg.get("smtp_user") or "alerts@digitaltwin"
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText("\n".join(body_lines), "plain"))

    host = cfg["smtp_host"]
    port = int(cfg.get("smtp_port") or 587)
    with smtplib.SMTP(host, port, timeout=10) as s:
        if cfg.get("use_tls", True):
            s.starttls()
        if cfg.get("smtp_user") and cfg.get("smtp_password"):
            s.login(cfg["smtp_user"], cfg["smtp_password"])
        s.sendmail(msg["From"], to_addrs, msg.as_string())


async def _post_slack(cfg: dict[str, Any], alert: dict) -> None:
    webhook = cfg["webhook_url"]
    severity = alert.get("severity", "info")
    color = {"critical": "#dc2626", "high": "#f97316", "medium": "#f59e0b",
             "low": "#3b82f6", "info": "#64748b"}.get(severity, "#64748b")
    mention = cfg.get("mention") or ""
    payload = {
        "text": f"{mention} *{severity.upper()}* — {alert.get('title')}".strip(),
        "attachments": [
            {
                "color": color,
                "fields": [
                    {"title": "Device", "value": (alert.get("context") or {}).get("device_name") or alert.get("device_id"), "short": True},
                    {"title": "Rule", "value": alert.get("rule_key"), "short": True},
                    {"title": "Current", "value": str(alert.get("current_value")), "short": True},
                    {"title": "Threshold", "value": str(alert.get("threshold")), "short": True},
                    {"title": "Recommendation", "value": alert.get("recommendation") or "—", "short": False},
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(webhook, content=json.dumps(payload),
                              headers={"Content-Type": "application/json"})
        r.raise_for_status()


async def broadcast_lifecycle(manager, alert: dict, kind: str) -> None:
    """Broadcast lifecycle events (resolved/acknowledged/closed) via WS only."""
    try:
        await manager.broadcast_to_org(alert["org_id"], {"type": kind, "alert": alert})
    except Exception as exc:
        log.warning("lifecycle broadcast failed: %s", exc)
