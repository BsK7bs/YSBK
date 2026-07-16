"""Engine orchestrator: runs rules, applies dwell/escalation, opens/updates
alerts, applies auto-resolution based on differentiated severity policy,
and dispatches notifications.

Entry points:
    * ``evaluate_and_apply(db, device, metrics, manager)`` — called from the
      WebSocket telemetry ingest.
    * ``evaluate_and_apply_inventory(db, device, inventory, previous, manager)``
      — called when the agent uploads a fresh inventory snapshot.

Both entry points share ``_evaluate(ctx, policies)`` which returns the set of
rule triggers, then ``_apply(...)`` persists changes and notifies.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .dwell import observe as observe_dwell, seconds_since, clear as clear_dwell
from .notify import broadcast_lifecycle, dispatch_alert
from .policies import DEFAULT_POLICIES, RESOLUTION_GRACE_BY_SEVERITY, merge_policy
from .rules import MULTI_RULES, SINGLE_RULES, RuleTrigger
from .software_policy import evaluate_software_policy_triggers
from .store import find_active, mark_condition_cleared, open_alert

log = logging.getLogger("alerts.engine")


async def _load_org_policies(db, org_id: str) -> dict[str, dict[str, Any]]:
    doc = await db.alert_policies.find_one({"org_id": org_id}, {"_id": 0, "policies": 1})
    return (doc or {}).get("policies") or {}


async def _resolve_or_park(db, alert: dict, *, manager) -> None:
    """Apply the differentiated auto-resolution policy.

    * Info / Low / Medium — auto-close after healthy grace window
    * High / Critical — move to resolved_awaiting_ack (require human ack)
    """
    sev = alert.get("severity") or "info"
    grace = RESOLUTION_GRACE_BY_SEVERITY.get(sev, None)
    # Compute how long the underlying condition has been healthy via dwell.
    dwell_doc = await db.alert_dwell.find_one({
        "key": f"{alert['device_id']}|{alert['rule_key']}|{alert.get('dimension_key','')}"
    })
    healthy_seconds = seconds_since(dwell_doc.get("healthy_since") if dwell_doc else None)

    if grace is None:
        # High/Critical — park awaiting ack (once, don't spam).
        if alert.get("status") not in ("resolved_awaiting_ack", "closed"):
            updated = await mark_condition_cleared(db, alert, auto_close=False)
            await broadcast_lifecycle(manager, updated, "alert.awaiting_ack")
        return

    # Info/Low/Medium — close after grace window.
    if healthy_seconds >= grace and alert.get("status") != "closed":
        updated = await mark_condition_cleared(db, alert, auto_close=True)
        await broadcast_lifecycle(manager, updated, "alert.resolved")
        # Clear dwell state entirely.
        await clear_dwell(db, alert["device_id"], alert["rule_key"], alert.get("dimension_key", ""))


async def _apply_trigger(db, org_id: str, device: dict, trig: RuleTrigger, manager) -> None:
    if not trig.rule_key:
        return
    device_id = device["id"]
    device_name = device.get("display_name") or device.get("hostname")

    if trig.triggered:
        # 1. Update dwell tracker.
        dwell = await observe_dwell(db, org_id, device_id, trig.rule_key, True,
                                    value=trig.current_value, dimension_key=trig.dimension_key)
        elapsed = seconds_since(dwell.get("started_at"))
        # 2. Enforce dwell threshold before firing.
        if elapsed < trig.dwell_seconds:
            trig.duration_seconds = int(elapsed)
            return  # not yet
        # 3. Fire (open or bump).
        alert, is_new = await open_alert(
            db,
            org_id=org_id,
            device_id=device_id,
            device_name=device_name,
            rule_key=trig.rule_key,
            dimension_key=trig.dimension_key,
            title=trig.title,
            category=trig.category,
            severity=trig.severity or "info",
            current_value=trig.current_value,
            threshold=trig.threshold,
            unit=trig.unit,
            duration_seconds=int(elapsed),
            recommendation=trig.recommendation,
            context=trig.context or {},
        )
        # 4. Notify (in-app always; email/slack on escalated or new).
        # Debounce: notify only when new OR severity escalated (last_notified_severity < current)
        last_notified = alert.get("last_notified_severity")
        should_notify = is_new or (last_notified != alert.get("severity"))
        if should_notify:
            await dispatch_alert(db, alert, manager)
    elif trig.clear:
        # Condition currently healthy — track dwell + attempt auto-resolve.
        await observe_dwell(db, org_id, device_id, trig.rule_key, False,
                            value=trig.current_value, dimension_key=trig.dimension_key)
        existing = await find_active(db, org_id, device_id, trig.rule_key, trig.dimension_key)
        if existing:
            await _resolve_or_park(db, existing, manager=manager)


async def _evaluate(ctx: dict, policies: dict) -> list[RuleTrigger]:
    triggers: list[RuleTrigger] = []
    for r in SINGLE_RULES:
        try:
            triggers.append(r(ctx, policies))
        except Exception as exc:
            log.warning("rule %s failed: %s", getattr(r, "__name__", "?"), exc)
    for r in MULTI_RULES:
        try:
            triggers.extend(r(ctx, policies) or [])
        except Exception as exc:
            log.warning("multi rule %s failed: %s", getattr(r, "__name__", "?"), exc)
    return triggers


async def evaluate_and_apply(db, device: dict, metrics: dict, manager,
                             inventory: dict | None = None,
                             previous_inventory: dict | None = None) -> None:
    """Called from telemetry ingest. Evaluates metric-driven rules only."""
    if not device:
        return
    # Skip alert evaluation entirely when device is in maintenance mode with suppress flag.
    if device.get("maintenance_mode") and device.get("maintenance_suppress_alerts", True):
        return
    org_id = device["org_id"]
    policies = await _load_org_policies(db, org_id)
    ctx = {
        "device": device,
        "metrics": metrics or {},
        "inventory": inventory or device.get("inventory") or {},
        "previous_inventory": previous_inventory or {},
    }
    triggers = await _evaluate(ctx, policies)
    # Optional: software policy triggers when inventory is available.
    if inventory or device.get("inventory"):
        triggers.extend(await evaluate_software_policy_triggers(
            db, org_id, ctx["inventory"], device))
    for t in triggers:
        await _apply_trigger(db, org_id, device, t, manager)


async def evaluate_and_apply_inventory(db, device: dict, inventory: dict,
                                       previous_inventory: dict | None,
                                       manager) -> None:
    """Called when a fresh inventory snapshot lands."""
    if device.get("maintenance_mode") and device.get("maintenance_suppress_alerts", True):
        return
    org_id = device["org_id"]
    policies = await _load_org_policies(db, org_id)
    ctx = {
        "device": device,
        "metrics": device.get("latest_metrics") or {},
        "inventory": inventory,
        "previous_inventory": previous_inventory or {},
    }
    triggers = await _evaluate(ctx, policies)
    triggers.extend(await evaluate_software_policy_triggers(db, org_id, inventory, device))
    for t in triggers:
        await _apply_trigger(db, org_id, device, t, manager)
