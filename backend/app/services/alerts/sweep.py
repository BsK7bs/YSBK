"""Periodic sweep task: catches conditions that only become visible via time.

Runs every ~30s.

1. Offline detection — for each device that hasn't checked in past the
   configured thresholds, evaluate the ``offline`` rule.
2. Lifecycle progression — for each parked alert (Info/Low/Medium) whose
   dwell tracker shows enough healthy time, close it.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .dwell import seconds_since
from .engine import _apply_trigger, _load_org_policies
from .rules import rule_offline
from .store import find_active, mark_condition_cleared
from .policies import RESOLUTION_GRACE_BY_SEVERITY
from .notify import broadcast_lifecycle

log = logging.getLogger("alerts.sweep")


async def sweep_offline_and_lifecycle(db, manager) -> None:
    """One iteration of the sweep. Safe to call frequently."""
    now = datetime.now(timezone.utc)

    # 1) Offline evaluation: check every device whose last_seen is older than 5 minutes.
    cutoff = (now - timedelta(minutes=5)).isoformat()
    async for device in db.devices.find(
        {"$or": [{"is_online": False}, {"last_seen": {"$lt": cutoff}}]},
        {"_id": 0},
    ):
        try:
            policies = await _load_org_policies(db, device["org_id"])
            trig = rule_offline({"device": device}, policies)
            await _apply_trigger(db, device["org_id"], device, trig, manager)
        except Exception as exc:
            log.warning("offline sweep failed for %s: %s", device.get("id"), exc)

    # 2) Lifecycle progression: parked alerts whose healthy_since exceeds grace.
    async for alert in db.alerts.find({"status": "open"}, {"_id": 0}):
        sev = alert.get("severity") or "info"
        grace = RESOLUTION_GRACE_BY_SEVERITY.get(sev)
        if grace is None:
            continue
        dwell = await db.alert_dwell.find_one({
            "key": f"{alert['device_id']}|{alert['rule_key']}|{alert.get('dimension_key','')}"
        })
        if not dwell or not dwell.get("healthy_since"):
            continue
        healthy = seconds_since(dwell.get("healthy_since"), now=now)
        if healthy >= grace:
            try:
                updated = await mark_condition_cleared(db, alert, auto_close=True)
                await broadcast_lifecycle(manager, updated, "alert.resolved")
            except Exception as exc:
                log.warning("lifecycle close failed for %s: %s", alert.get("id"), exc)
