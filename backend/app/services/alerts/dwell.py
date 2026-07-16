"""Dwell tracker: remembers when a condition first became true per
(device, rule_key, dimension_key). Used to enforce sustained-condition
rules and prevent spike-based false alarms.

Backed by the ``alert_dwell`` MongoDB collection so state survives restarts.
Each doc:
    {
      _id: implicit,
      key: "<device_id>|<rule_key>|<dimension_key>",
      device_id, org_id, rule_key, dimension_key,
      started_at: iso,          # first time the condition was seen True
      last_true_at: iso,        # most recent time condition was True
      healthy_since: iso|None,  # first time condition flipped back to False
      last_value: any,
    }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _key(device_id: str, rule_key: str, dimension_key: str = "") -> str:
    return f"{device_id}|{rule_key}|{dimension_key}"


async def observe(
    db,
    org_id: str,
    device_id: str,
    rule_key: str,
    condition_true: bool,
    value: Any = None,
    dimension_key: str = "",
    now_iso: str | None = None,
) -> dict:
    """Observe a single condition sample. Returns the current dwell doc."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    key = _key(device_id, rule_key, dimension_key)
    existing = await db.alert_dwell.find_one({"key": key})

    if condition_true:
        if not existing:
            doc = {
                "key": key,
                "org_id": org_id,
                "device_id": device_id,
                "rule_key": rule_key,
                "dimension_key": dimension_key,
                "started_at": now_iso,
                "last_true_at": now_iso,
                "healthy_since": None,
                "last_value": value,
            }
            await db.alert_dwell.insert_one(doc)
            return doc
        update = {"last_true_at": now_iso, "healthy_since": None, "last_value": value}
        await db.alert_dwell.update_one({"key": key}, {"$set": update})
        existing.update(update)
        return existing

    # Condition is False.
    if not existing:
        # Nothing to track.
        return {
            "key": key,
            "org_id": org_id,
            "device_id": device_id,
            "rule_key": rule_key,
            "dimension_key": dimension_key,
            "started_at": None,
            "last_true_at": None,
            "healthy_since": now_iso,
            "last_value": value,
        }
    if not existing.get("healthy_since"):
        await db.alert_dwell.update_one({"key": key}, {"$set": {"healthy_since": now_iso, "last_value": value}})
        existing["healthy_since"] = now_iso
        existing["last_value"] = value
    return existing


async def clear(db, device_id: str, rule_key: str, dimension_key: str = "") -> None:
    await db.alert_dwell.delete_one({"key": _key(device_id, rule_key, dimension_key)})


def seconds_since(iso: str | None, now: datetime | None = None) -> float:
    if not iso:
        return 0.0
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt).total_seconds())
    except ValueError:
        return 0.0
